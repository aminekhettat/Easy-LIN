"""Communication panel widget for the preserved PyQt frontend.

Provides the user interface for hardware connection, manual frame sending,
schedule execution, and live frame monitoring.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

import logging
from typing import Optional

from PyQt5.QtWidgets import (
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
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QColor

from src.ldf_parser import LDFFile
from src.lin_master import LINMaster, ReceivedFrame

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread-safe signal bridge
# ---------------------------------------------------------------------------


class _Bridge(QObject):
    """Emits Qt signals from non-GUI threads so that GUI updates are safe."""

    frame_received = pyqtSignal(object)  # ReceivedFrame
    error_occurred = pyqtSignal(str)


# ---------------------------------------------------------------------------
# Live frame monitor
# ---------------------------------------------------------------------------


class _FrameMonitor(QWidget):
    """Scrolling table of received LIN frames."""

    MAX_ROWS = 500

    def __init__(self, parent=None):
        """Initialize the frame monitor table and clear action."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>Frame Monitor</b>"))
        hdr.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(70)
        self._clear_btn.clicked.connect(self._clear)
        hdr.addWidget(self._clear_btn)
        layout.addLayout(hdr)

        cols = ["Timestamp (ms)", "Frame ID", "DLC", "Data (hex)", "Status"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for c in (0, 1, 2, 4):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    def add_frame(self, frame: ReceivedFrame) -> None:
        """Append one received frame to the monitor table."""
        ts_ms = frame.timestamp_ns / 1_000_000
        hex_data = " ".join(f"{b:02X}" for b in frame.data)
        status = "CRC ERR" if frame.crc_error else "OK"

        row = self._table.rowCount()
        if row >= self.MAX_ROWS:
            self._table.removeRow(0)
            row = self._table.rowCount()
        self._table.insertRow(row)

        def _i(txt, center=False):
            """Create one read-only table item."""
            it = QTableWidgetItem(str(txt))
            it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if center:
                it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            return it

        self._table.setItem(row, 0, _i(f"{ts_ms:.3f}", center=True))
        self._table.setItem(row, 1, _i(f"0x{frame.frame_id:02X}", center=True))
        self._table.setItem(row, 2, _i(str(len(frame.data)), center=True))
        self._table.setItem(row, 3, _i(hex_data))
        status_item = _i(status, center=True)
        if frame.crc_error:
            status_item.setForeground(QColor("red"))
        else:
            status_item.setForeground(QColor("green"))
        self._table.setItem(row, 4, status_item)
        self._table.scrollToBottom()

    def _clear(self) -> None:
        """Remove all rows from the frame monitor."""
        self._table.setRowCount(0)


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

    status_message = pyqtSignal(str)
    """Signal emitted to update the main window status bar."""

    def __init__(self, parent=None):
        """Initialize the communication panel and signal bridge."""
        super().__init__(parent)
        self._ldf: Optional[LDFFile] = None
        self._master = LINMaster(
            on_frame_received=self._on_frame_received,
            on_error=self._on_error,
        )
        self._bridge = _Bridge()
        self._bridge.frame_received.connect(self._monitor_add_frame)
        self._bridge.error_occurred.connect(self._show_error)

        self._build_ui()
        self._refresh_channels()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the vertical layout containing controls and frame monitor."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)

        # Top half: controls
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout.addWidget(self._build_connection_group())
        controls_layout.addWidget(self._build_tx_group())
        controls_layout.addWidget(self._build_schedule_group())
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

        self._status_led = QLabel("●")
        self._status_led.setStyleSheet("color: red; font-size: 18px;")
        layout.addWidget(self._status_led)

        self._channel_combo = QComboBox()
        self._channel_combo.setMinimumWidth(200)
        layout.addWidget(QLabel("Channel:"))
        layout.addWidget(self._channel_combo)

        self._refresh_btn = QPushButton("↻ Refresh")
        self._refresh_btn.setFixedWidth(90)
        self._refresh_btn.clicked.connect(self._refresh_channels)
        layout.addWidget(self._refresh_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(90)
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

        self._send_btn = QPushButton("▶ Send")
        self._send_btn.setEnabled(False)
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

        self._sched_start_btn = QPushButton("▶ Run")
        self._sched_start_btn.setEnabled(False)
        self._sched_start_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #005B9F; color: white; }"
        )
        self._sched_start_btn.clicked.connect(self._run_schedule)
        layout.addWidget(self._sched_start_btn)

        self._sched_stop_btn = QPushButton("■ Stop")
        self._sched_stop_btn.setEnabled(False)
        self._sched_stop_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #8B0000; color: white; }"
        )
        self._sched_stop_btn.clicked.connect(self._stop_schedule)
        layout.addWidget(self._sched_stop_btn)

        layout.addStretch()
        return box

    # ------------------------------------------------------------------
    # LDF propagation
    # ------------------------------------------------------------------

    def load_ldf(self, ldf: LDFFile) -> None:
        """Update the panel whenever a new LDF file is loaded."""
        self._ldf = ldf

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
            self._master.is_connected and self._sched_combo.count() > 0
        )

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def _refresh_channels(self) -> None:
        """Refresh the list of available Vector hardware channels."""
        self._channel_combo.clear()
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
        if self._master.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        """Open the selected hardware channel."""
        mask = self._channel_combo.currentData()
        if mask is None:
            self.status_message.emit("No hardware channel selected.")
            return
        try:
            self._master.connect(
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
        except Exception as exc:
            self.status_message.emit(f"Connection failed: {exc}")
            log.exception("Connection failed")

    def _disconnect(self) -> None:
        """Disconnect the active hardware channel and reset the UI."""
        try:
            self._master.disconnect()
        except Exception as exc:
            log.warning("Disconnect error: %s", exc)
        self._status_led.setStyleSheet("color: red; font-size: 18px;")
        self._connect_btn.setText("Connect")
        self._connect_btn.setStyleSheet("QPushButton { background-color: #3A7D44; color: white; }")
        self._send_btn.setEnabled(False)
        self._sched_start_btn.setEnabled(False)
        self._sched_stop_btn.setEnabled(False)
        self.status_message.emit("Disconnected.")

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
                    "Invalid hex data — use space-separated bytes, e.g. '01 FF A0'"
                )
                return
            try:
                self._master.send_frame_data(frame.frame_id, data)
                self.status_message.emit(
                    f"Sent master response for 0x{frame.frame_id:02X} ({frame.name})."
                )
            except Exception as exc:
                self.status_message.emit(f"TX error: {exc}")
        else:
            try:
                self._master.send_frame(frame.frame_id)
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
            self._master.run_schedule(sched)
            self._sched_start_btn.setEnabled(False)
            self._sched_stop_btn.setEnabled(True)
            self.status_message.emit(f"Running schedule '{sched.name}'.")
        except Exception as exc:
            self.status_message.emit(f"Schedule start error: {exc}")

    def _stop_schedule(self) -> None:
        """Stop the currently running schedule table."""
        self._master.stop_schedule()
        self._sched_start_btn.setEnabled(True)
        self._sched_stop_btn.setEnabled(False)
        self.status_message.emit("Schedule stopped.")

    # ------------------------------------------------------------------
    # Callbacks from LINMaster (called from background threads)
    # ------------------------------------------------------------------

    def _on_frame_received(self, frame: ReceivedFrame) -> None:
        """Bridge a received frame from the worker thread to the GUI thread."""
        self._bridge.frame_received.emit(frame)

    def _on_error(self, msg: str) -> None:
        """Bridge a hardware error from the worker thread to the GUI thread."""
        self._bridge.error_occurred.emit(msg)

    @pyqtSlot(object)
    def _monitor_add_frame(self, frame: ReceivedFrame) -> None:
        """Append a received frame to the live monitor widget."""
        self._monitor.add_frame(frame)

    @pyqtSlot(str)
    def _show_error(self, msg: str) -> None:
        """Forward a hardware error message to the main window status bar."""
        self.status_message.emit(f"Hardware error: {msg}")
