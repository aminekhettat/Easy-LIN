"""Communication panel widget for the preserved PyQt frontend.

Provides the user interface for hardware connection, manual frame sending,
schedule execution, and live frame monitoring.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

import csv
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QCheckBox,
    QSplitter,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QObject, Slot
from PySide6.QtGui import QColor

from src.ldf_parser import LDFFile
from src.lin_master import LINMaster, ReceivedFrame

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommunicationSelection:
    """Selected LDF nodes used to initiate communication."""

    master: str
    slaves: tuple[str, ...]


class CommunicationBackend(Protocol):
    """Backend contract for LIN communication providers."""

    @property
    def is_connected(self) -> bool:
        """Return current connection state."""

    def list_lin_channels(self) -> list[dict]:
        """Return available LIN channels for this backend."""

    def connect(self, channel_mask: int, ldf: Optional[LDFFile]) -> None:
        """Connect to selected channel."""

    def disconnect(self) -> None:
        """Disconnect current channel."""

    def send_frame(self, frame_id: int) -> None:
        """Send master request."""

    def send_frame_data(self, frame_id: int, data: list[int]) -> None:
        """Send master-published response data."""

    def run_schedule(self, schedule) -> None:
        """Start schedule execution."""

    def stop_schedule(self) -> None:
        """Stop schedule execution."""

    def preflight(self) -> tuple[bool, str]:
        """Verify the backend driver is functional before a real connect attempt."""


class VectorBackendAdapter:
    """Vector implementation of the communication backend contract."""

    def __init__(
        self,
        on_frame_received,
        on_error,
        on_frame_changed,
    ) -> None:
        """Instantiate LIN master callbacks for Vector hardware."""
        self._master = LINMaster(
            on_frame_received=on_frame_received,
            on_error=on_error,
            on_frame_changed=on_frame_changed,
        )

    @property
    def is_connected(self) -> bool:
        """Return current Vector connection state."""
        return self._master.is_connected

    @property
    def dll_path(self) -> Optional[str]:
        """Return the loaded DLL path from the underlying LIN master."""
        return getattr(self._master, 'dll_path', None)

    def preflight(self) -> tuple[bool, str]:
        """Forward a DLL preflight check to the underlying LIN master."""
        return self._master.preflight()

    def list_lin_channels(self) -> list[dict]:
        """Return channels exposed by Vector XL."""
        return LINMaster.list_lin_channels()

    def connect(self, channel_mask: int, ldf: Optional[LDFFile]) -> None:
        """Connect through Vector LIN master."""
        self._master.connect(channel_mask=channel_mask, ldf=ldf)

    def disconnect(self) -> None:
        """Disconnect Vector LIN master."""
        self._master.disconnect()

    def send_frame(self, frame_id: int) -> None:
        """Forward master request."""
        self._master.send_frame(frame_id)

    def send_frame_data(self, frame_id: int, data: list[int]) -> None:
        """Forward master response."""
        self._master.send_frame_data(frame_id, data)

    def run_schedule(self, schedule) -> None:
        """Forward schedule execution request."""
        self._master.run_schedule(schedule)

    def stop_schedule(self) -> None:
        """Forward stop schedule request."""
        self._master.stop_schedule()


# ---------------------------------------------------------------------------
# Thread-safe signal bridge
# ---------------------------------------------------------------------------


class _Bridge(QObject):
    """Emits Qt signals from non-GUI threads so that GUI updates are safe."""

    frame_received = Signal(object)  # ReceivedFrame
    error_occurred = Signal(str)


# ---------------------------------------------------------------------------
# Live frame monitor
# ---------------------------------------------------------------------------


class _FrameMonitor(QWidget):
    """Scrolling table of received LIN frames."""

    status_message = Signal(str)

    MAX_ROWS = 500
    CSV_COLUMNS = [
        "Timestamp (ms)",
        "Direction",
        "Frame ID",
        "DLC",
        "Status",
        "Checksum",
        "Data (hex)",
    ]

    def __init__(self, parent=None):
        """Initialize the frame monitor table and clear action."""
        super().__init__(parent)
        self._logging_path: Optional[str] = None
        self._logging_file = None
        self._logging_writer: Optional[csv.writer] = None
        self._records: list[dict[str, object]] = []
        self._session_metadata: dict[str, str] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>Frame Monitor</b>"))
        hdr.addStretch()
        self._log_btn = QPushButton("Start CSV Log")
        self._log_btn.setFixedWidth(100)
        self._log_btn.setAccessibleName("Start or stop CSV logging")
        self._log_btn.clicked.connect(self._toggle_csv_logging)
        hdr.addWidget(self._log_btn)
        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setFixedWidth(90)
        self._export_btn.setAccessibleName("Export frame monitor to CSV")
        self._export_btn.clicked.connect(self._export_csv)
        hdr.addWidget(self._export_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(70)
        self._clear_btn.clicked.connect(self._clear)
        hdr.addWidget(self._clear_btn)
        layout.addLayout(hdr)

        cols = ["Timestamp (ms)", "Frame ID", "DLC", "Data (hex)", "Status"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for c in (0, 1, 2, 4):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    def add_frame(self, frame: ReceivedFrame) -> None:
        """Append one received frame to the monitor table."""
        record = self._frame_to_record(frame)

        row = self._table.rowCount()
        if row >= self.MAX_ROWS:
            self._table.removeRow(0)
            self._records.pop(0)
            row = self._table.rowCount()
        self._table.insertRow(row)
        self._records.append(record)

        def _i(txt, center=False):
            """Create one read-only table item."""
            it = QTableWidgetItem(str(txt))
            it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            if center:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return it

        self._table.setItem(row, 0, _i(record["timestamp_ms"], center=True))
        self._table.setItem(row, 1, _i(record["frame_id"], center=True))
        self._table.setItem(row, 2, _i(record["dlc"], center=True))
        self._table.setItem(row, 3, _i(record["data_hex"]))
        status_item = _i(record["status"], center=True)
        if frame.crc_error:
            status_item.setForeground(QColor("red"))
        else:
            status_item.setForeground(QColor("green"))
        self._table.setItem(row, 4, status_item)
        self._table.scrollToBottom()
        self._write_logged_frame(record)

    @property
    def is_logging(self) -> bool:
        """Return whether live CSV logging is currently active."""
        return self._logging_writer is not None

    def stop_csv_logging(self) -> None:
        """Flush and close the active CSV log, if any."""
        if self._logging_file is None:
            return
        path = self._logging_path or "CSV log"
        self._logging_file.close()
        self._logging_file = None
        self._logging_writer = None
        self._logging_path = None
        self._log_btn.setText("Start CSV Log")
        self.status_message.emit(f"CSV logging stopped: {path}")

    def set_session_metadata(self, metadata: dict[str, str]) -> None:
        """Store descriptive session metadata written at the top of CSV files."""
        self._session_metadata = {key: value for key, value in metadata.items() if value}

    def _frame_to_record(self, frame: ReceivedFrame) -> dict[str, object]:
        """Return normalized values for table display and CSV logging."""
        timestamp_ms = f"{frame.timestamp_ns / 1_000_000:.3f}"
        data_hex = " ".join(f"{byte:02X}" for byte in frame.data)
        direction = self._resolve_frame_direction(frame.frame_id)
        return {
            "timestamp_ms": timestamp_ms,
            "direction": direction,
            "frame_id": f"0x{frame.frame_id:02X}",
            "dlc": str(len(frame.data)),
            "status": "CRC ERR" if frame.crc_error else "OK",
            "checksum": f"0x{frame.checksum:02X}" if frame.checksum is not None else "",
            "data_hex": data_hex,
        }

    def _resolve_frame_direction(self, frame_id: int) -> str:
        """Describe whether the frame is expected from master or slave publisher."""
        selected_master = self._session_metadata.get("Selected Master", "")
        selected_slaves = {
            item.strip()
            for item in self._session_metadata.get("Selected Slaves", "").split(";")
            if item.strip()
        }
        declared_master = self._session_metadata.get("Declared Master", "")
        declared_slaves = {
            item.strip()
            for item in self._session_metadata.get("Declared Slaves", "").split(";")
            if item.strip()
        }
        frame_publishers = self._session_metadata.get("Frame Publishers", "")
        publisher = ""
        for mapping in frame_publishers.split("|"):
            if not mapping:
                continue
            frame_key, _, frame_publisher = mapping.partition("=")
            if frame_key == f"0x{frame_id:02X}":
                publisher = frame_publisher
                break

        master_name = selected_master or declared_master
        slave_names = selected_slaves or declared_slaves
        if publisher and master_name and publisher == master_name:
            return "Master -> Slave"
        if publisher and publisher in slave_names:
            return "Slave -> Master"
        return "Unknown"

    def _write_csv_preamble(self, writer: csv.writer) -> None:
        """Write metadata and header rows for a CSV log document."""
        if self._session_metadata:
            writer.writerow(["Session Metadata"])
            writer.writerow(["Key", "Value"])
            for key, value in self._session_metadata.items():
                writer.writerow([key, value])
            writer.writerow([])
        writer.writerow(self.CSV_COLUMNS)

    def _write_logged_frame(self, record: dict[str, object]) -> None:
        """Append one normalized frame record to the active CSV log."""
        if self._logging_writer is None:
            return
        self._logging_writer.writerow(
            [
                record["timestamp_ms"],
                record["direction"],
                record["frame_id"],
                record["dlc"],
                record["status"],
                record["checksum"],
                record["data_hex"],
            ]
        )
        assert self._logging_file is not None
        self._logging_file.flush()

    def _start_csv_logging(self, path: str) -> None:
        """Open a CSV file and start appending newly received frames."""
        file_handle = open(path, "w", newline="", encoding="utf-8")
        writer = csv.writer(file_handle)
        self._write_csv_preamble(writer)
        self._logging_path = path
        self._logging_file = file_handle
        self._logging_writer = writer
        self._log_btn.setText("Stop CSV Log")
        self.status_message.emit(f"CSV logging started: {path}")

    def _toggle_csv_logging(self) -> None:
        """Start or stop live CSV logging for received frames."""
        if self.is_logging:
            self.stop_csv_logging()
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Start Frame Logging", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            self.status_message.emit("CSV logging cancelled.")
            return
        self._start_csv_logging(path)

    def _export_csv(self) -> None:
        """Export the current monitor contents to a user-chosen CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Frame Monitor", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        self._write_csv_preamble(writer)
        for record in self._records:
            writer.writerow(
                [
                    record["timestamp_ms"],
                    record["direction"],
                    record["frame_id"],
                    record["dlc"],
                    record["status"],
                    record["checksum"],
                    record["data_hex"],
                ]
            )
        with open(path, "w", newline="", encoding="utf-8") as fh:
            fh.write(buf.getvalue())

    def _clear(self) -> None:
        """Remove all rows from the frame monitor."""
        self._table.setRowCount(0)
        self._records.clear()


# ---------------------------------------------------------------------------
# Communication Panel (public widget)
# ---------------------------------------------------------------------------


class CommunicationPanel(QWidget):
    """
    Full communication panel combining:
      - Hardware connection controls
      - Manual frame TX
      - Schedule execution
      - Live frame monitor
    """

    status_message = Signal(str)
    """Signal emitted to update the main window status bar."""

    communication_state_changed = Signal(str)
    """Signal emitted when communication connectivity state changes."""

    def __init__(self, parent=None, backend: Optional[CommunicationBackend] = None):
        """Initialize the communication panel and signal bridge."""
        super().__init__(parent)
        self._ldf: Optional[LDFFile] = None
        self._selection: Optional[CommunicationSelection] = None
        self._backend: CommunicationBackend = backend or VectorBackendAdapter(
            on_frame_received=self._on_frame_received,
            on_error=self._on_error,
            on_frame_changed=self._on_frame_changed,
        )
        self._bridge = _Bridge()
        self._bridge.frame_received.connect(self._monitor_add_frame)
        self._bridge.error_occurred.connect(self._show_error)

        self._build_ui()
        self._monitor.status_message.connect(self.status_message)
        self._refresh_channels()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    @property
    def _master(self):
        """Compatibility alias for tests still referencing ``_master``."""
        return self._backend

    @_master.setter
    def _master(self, backend):
        """Compatibility alias setter mapping legacy ``_master`` to backend."""
        self._backend = backend

    def _build_ui(self) -> None:
        """Create the vertical layout containing controls and frame monitor."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top half: controls
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout.addWidget(self._build_connection_group())
        controls_layout.addWidget(self._build_tx_group())
        controls_layout.addWidget(self._build_schedule_group())
        controls_layout.addWidget(self._build_monitor_options_group())
        controls_layout.addStretch()

        # Bottom half: monitor
        self._monitor = _FrameMonitor()

        splitter.addWidget(controls)
        splitter.addWidget(self._monitor)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    def _build_connection_group(self) -> QGroupBox:
        """Create the hardware connection controls."""
        box = QGroupBox("Hardware Connection")
        layout = QHBoxLayout(box)

        self._status_led = QLabel("â—")
        self._status_led.setStyleSheet("color: red; font-size: 18px;")
        self._status_led.setAccessibleName("Connection indicator")
        self._status_led.setAccessibleDescription("Red means disconnected, green means connected")
        layout.addWidget(self._status_led)

        self._channel_combo = QComboBox()
        self._channel_combo.setMinimumWidth(200)
        layout.addWidget(QLabel("Channel:"))
        layout.addWidget(self._channel_combo)

        self._refresh_btn = QPushButton("â†» Refresh")
        self._refresh_btn.setFixedWidth(90)
        self._refresh_btn.setAccessibleName("Refresh hardware channels")
        self._refresh_btn.clicked.connect(self._refresh_channels)
        layout.addWidget(self._refresh_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(90)
        self._connect_btn.setAccessibleName("Connect or disconnect hardware")
        self._connect_btn.setStyleSheet("QPushButton { background-color: #3A7D44; color: white; }")
        self._connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self._connect_btn)

        layout.addStretch()
        return box

    def _build_tx_group(self) -> QGroupBox:
        """Create the manual frame transmission controls."""
        box = QGroupBox("Send Frame (Manual)")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Frame:"))
        self._frame_combo = QComboBox()
        self._frame_combo.setMinimumWidth(180)
        self._frame_combo.currentIndexChanged.connect(self._on_frame_selected)
        layout.addWidget(self._frame_combo)

        layout.addWidget(QLabel("Data (hex, space-separated):"))
        self._data_edit = QLineEdit()
        self._data_edit.setPlaceholderText("e.g.  01 FF A0 00")
        self._data_edit.setMinimumWidth(160)
        layout.addWidget(self._data_edit)

        self._master_response_chk = QCheckBox("Master publishes")
        self._master_response_chk.setToolTip(
            "When checked the entered data bytes are sent as a master response.\n"
            "When unchecked a master request header is sent and the slave responds."
        )
        layout.addWidget(self._master_response_chk)

        self._send_btn = QPushButton("â–¶ Send")
        self._send_btn.setEnabled(False)
        self._send_btn.setAccessibleName("Send frame")
        self._send_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #005B9F; color: white; }"
        )
        self._send_btn.clicked.connect(self._send_frame)
        layout.addWidget(self._send_btn)

        layout.addStretch()
        return box

    def _build_schedule_group(self) -> QGroupBox:
        """Create the schedule selection and execution controls."""
        box = QGroupBox("Schedule Execution")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Schedule:"))
        self._sched_combo = QComboBox()
        self._sched_combo.setMinimumWidth(180)
        layout.addWidget(self._sched_combo)

        self._sched_start_btn = QPushButton("â–¶ Run")
        self._sched_start_btn.setEnabled(False)
        self._sched_start_btn.setAccessibleName("Run schedule")
        self._sched_start_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #005B9F; color: white; }"
        )
        self._sched_start_btn.clicked.connect(self._run_schedule)
        layout.addWidget(self._sched_start_btn)

        self._sched_stop_btn = QPushButton("â–  Stop")
        self._sched_stop_btn.setEnabled(False)
        self._sched_stop_btn.setAccessibleName("Stop schedule")
        self._sched_stop_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #8B0000; color: white; }"
        )
        self._sched_stop_btn.clicked.connect(self._stop_schedule)
        layout.addWidget(self._sched_stop_btn)

        layout.addStretch()
        return box

    def _build_monitor_options_group(self) -> QGroupBox:
        """Create options controlling which received frames are shown."""
        box = QGroupBox("Monitor Options")
        layout = QHBoxLayout(box)

        self._changed_only_chk = QCheckBox("Show only changed frames")
        self._changed_only_chk.setAccessibleName("Show only changed received frames")
        self._changed_only_chk.setToolTip(
            "When enabled, only frames whose payload changed are shown in the monitor."
        )
        self._changed_only_chk.toggled.connect(self._on_monitor_filter_toggled)
        layout.addWidget(self._changed_only_chk)
        layout.addStretch()
        return box

    def _on_monitor_filter_toggled(self, checked: bool) -> None:
        """Announce monitor filtering mode changes for accessibility and clarity."""
        if checked:
            self.status_message.emit("Monitor filter enabled: showing only changed frames.")
        else:
            self.status_message.emit("Monitor filter disabled: showing all received frames.")

    # ------------------------------------------------------------------
    # LDF propagation
    # ------------------------------------------------------------------

    def load_ldf(self, ldf: LDFFile) -> None:
        """Update the panel whenever a new LDF file is loaded."""
        self._ldf = ldf
        self._selection = None
        self._sync_monitor_metadata()

        # Frame combo
        self._frame_combo.clear()
        for frame in ldf.frames:
            self._frame_combo.addItem(
                f"0x{frame.frame_id:02X}  {frame.name}  ({frame.frame_size}B)",
                userData=frame,
            )

        # Schedule combo
        self._sched_combo.clear()
        for sched in ldf.schedule_tables:
            self._sched_combo.addItem(sched.name, userData=sched)

        self._sched_start_btn.setEnabled(
            self._backend.is_connected and self._sched_combo.count() > 0
        )

    def configure_selection(self, master: str, slaves: list[str]) -> None:
        """Store selected master and slave nodes used to gate communication start."""
        self._selection = CommunicationSelection(master=master, slaves=tuple(slaves))
        self._sync_monitor_metadata()

    def _sync_monitor_metadata(self) -> None:
        """Publish current LDF and node selection context to the frame monitor."""
        ldf = self._ldf
        selection = self._selection
        nodes = ldf.nodes if ldf is not None else None
        source_path = ldf.source_path if ldf is not None else ""
        metadata = {
            "LDF File Name": os.path.basename(source_path) if source_path else "",
            "LDF File Path": source_path,
            "LDF Channel Name": ldf.channel_name if ldf is not None and ldf.channel_name else "",
            "Protocol Version": ldf.protocol_version if ldf is not None else "",
            "Language Version": ldf.language_version if ldf is not None else "",
            "Bus Speed (kbps)": f"{ldf.speed}" if ldf is not None else "",
            "Declared Master": nodes.master.name if nodes is not None else "",
            "Declared Slaves": "; ".join(nodes.slaves) if nodes is not None else "",
            "Selected Master": selection.master if selection is not None else "",
            "Selected Slaves": "; ".join(selection.slaves) if selection is not None else "",
            "Frame Publishers": "|".join(
                f"0x{frame.frame_id:02X}={frame.publisher}" for frame in (ldf.frames if ldf is not None else [])
            ),
        }
        self._monitor.set_session_metadata(metadata)

    def focus_primary_control(self) -> None:
        """Move focus to the first interactive control in this panel."""
        self._channel_combo.setFocus(Qt.FocusReason.ShortcutFocusReason)

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def _refresh_channels(self) -> None:
        """Refresh the list of available Vector hardware channels."""
        self._channel_combo.clear()
        channels = self._backend.list_lin_channels()
        if not isinstance(channels, list):
            channels = LINMaster.list_lin_channels()
        if channels:
            for ch in channels:
                self._channel_combo.addItem(
                    f"{ch['name']} (ch {ch['channel_index']})",
                    userData=ch["channel_mask"],
                )
        else:
            self._channel_combo.addItem("No Vector hardware found", userData=None)

    def _toggle_connection(self) -> None:
        """Connect or disconnect depending on the current hardware state."""
        if self._backend.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        """Open the selected hardware channel."""
        mask = self._channel_combo.currentData()
        if mask is None:
            self.status_message.emit("No hardware channel selected.")
            self.communication_state_changed.emit("No hardware")
            return
        try:
            if self._ldf is not None and self._selection is None:
                self.status_message.emit("Select one master and at least one slave first.")
                self.communication_state_changed.emit("Disconnected")
                return
            ok, reason = self._backend.preflight()
            if not ok:
                self.status_message.emit(f"Driver preflight failed: {reason}")
                self.communication_state_changed.emit("Error")
                return
            self._backend.connect(
                channel_mask=mask,
                ldf=self._ldf,
            )
            self._status_led.setStyleSheet("color: green; font-size: 18px;")
            self._connect_btn.setText("Disconnect")
            self._connect_btn.setStyleSheet(
                "QPushButton { background-color: #8B0000; color: white; }"
            )
            self._send_btn.setEnabled(True)
            self._sched_start_btn.setEnabled(self._sched_combo.count() > 0)
            self.status_message.emit("Connected to LIN hardware.")
            self.communication_state_changed.emit("Connected")
            dll_path = getattr(self._backend, 'dll_path', None)
            if isinstance(dll_path, str):
                source = "bundled" if "third_party" in dll_path.replace("\\", "/") else "system"
                self.status_message.emit(f"Runtime: {dll_path} ({source})")
        except Exception as exc:
            self.status_message.emit(f"Connection failed: {exc}")
            self.communication_state_changed.emit("Error")
            log.exception("Connection failed")

    def _disconnect(self) -> None:
        """Disconnect the active hardware channel and reset the UI."""
        try:
            self._backend.disconnect()
        except Exception as exc:
            log.warning("Disconnect error: %s", exc)
        self._status_led.setStyleSheet("color: red; font-size: 18px;")
        self._connect_btn.setText("Connect")
        self._connect_btn.setStyleSheet("QPushButton { background-color: #3A7D44; color: white; }")
        self._send_btn.setEnabled(False)
        self._sched_start_btn.setEnabled(False)
        self._sched_stop_btn.setEnabled(False)
        self.status_message.emit("Disconnected.")
        self.communication_state_changed.emit("Disconnected")

    # ------------------------------------------------------------------
    # Frame TX
    # ------------------------------------------------------------------

    def _on_frame_selected(self, index: int) -> None:
        """Pre-fill the data field to match the selected frame size."""
        frame = self._frame_combo.currentData()
        if frame is not None:
            # Pre-fill data field with zeroes matching the frame size
            self._data_edit.setText(" ".join(["00"] * frame.frame_size))

    def _send_frame(self) -> None:
        """Send the selected frame as a request or master response."""
        frame = self._frame_combo.currentData()
        if frame is None:
            return
        if self._master_response_chk.isChecked():
            raw = self._data_edit.text().strip()
            try:
                data = [int(b, 16) for b in raw.split() if b]
            except ValueError:
                self.status_message.emit(
                    "Invalid hex data â€” use space-separated bytes, e.g. '01 FF A0'"
                )
                return
            try:
                self._backend.send_frame_data(frame.frame_id, data)
                self.status_message.emit(
                    f"Sent master response for 0x{frame.frame_id:02X} ({frame.name})."
                )
            except Exception as exc:
                self.status_message.emit(f"TX error: {exc}")
        else:
            try:
                self._backend.send_frame(frame.frame_id)
                self.status_message.emit(
                    f"Sent master request for 0x{frame.frame_id:02X} ({frame.name})."
                )
            except Exception as exc:
                self.status_message.emit(f"TX error: {exc}")

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    def _run_schedule(self) -> None:
        """Start execution of the selected schedule table."""
        sched = self._sched_combo.currentData()
        if sched is None:
            return
        try:
            self._backend.run_schedule(sched)
            self._sched_start_btn.setEnabled(False)
            self._sched_stop_btn.setEnabled(True)
            self.status_message.emit(f"Running schedule '{sched.name}'.")
        except Exception as exc:
            self.status_message.emit(f"Schedule start error: {exc}")

    def _stop_schedule(self) -> None:
        """Stop the currently running schedule table."""
        self._backend.stop_schedule()
        self._sched_start_btn.setEnabled(True)
        self._sched_stop_btn.setEnabled(False)
        self.status_message.emit("Schedule stopped.")

    # ------------------------------------------------------------------
    # Callbacks from LINMaster (called from background threads)
    # ------------------------------------------------------------------

    def _on_frame_received(self, frame: ReceivedFrame) -> None:
        """Bridge a received frame from the worker thread to the GUI thread."""
        if self._changed_only_chk.isChecked():
            return
        self._bridge.frame_received.emit(frame)

    def _on_error(self, msg: str) -> None:
        """Bridge a hardware error from the worker thread to the GUI thread."""
        self._bridge.error_occurred.emit(msg)

    def _on_frame_changed(self, frame: ReceivedFrame, _previous_data: Optional[bytes]) -> None:
        """Bridge only changed-payload frames when change-filter mode is active."""
        if not self._changed_only_chk.isChecked():
            return
        self._bridge.frame_received.emit(frame)

    @Slot(object)
    def _monitor_add_frame(self, frame: ReceivedFrame) -> None:
        """Append a received frame to the live monitor widget."""
        self._monitor.add_frame(frame)

    @Slot(str)
    def _show_error(self, msg: str) -> None:
        """Forward a hardware error message to the main window status bar."""
        self.status_message.emit(f"Hardware error: {msg}")
        self.communication_state_changed.emit("Error")

    def stop_csv_logging(self) -> None:
        """Stop live frame logging if it is active."""
        self._monitor.stop_csv_logging()


# ---------------------------------------------------------------------------
# Default backend registration
# ---------------------------------------------------------------------------

from src.communication import backend_registry as _backend_registry  # noqa: E402

_backend_registry.register("vector", VectorBackendAdapter)

