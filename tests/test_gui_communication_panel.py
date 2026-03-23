"""Tests for src/gui/communication_panel.py.

Covers:
- _Bridge signal emissions (frame_received, error_occurred)
- _FrameMonitor: add_frame (normal + CRC error), MAX_ROWS overflow, _clear
- CommunicationPanel: construction, load_ldf, focus_primary_control,
  _refresh_channels, _toggle_connection, _connect (success/failure/no mask),
  _disconnect (with exception), _on_frame_selected, _send_frame (master request,
  master response, invalid hex, no frame), _run_schedule (success/failure/no sched),
  _stop_schedule, _on_frame_received, _on_error, _monitor_add_frame, _show_error
- Signal emissions: status_message, communication_state_changed
"""

from __future__ import annotations

import os
import csv
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QGroupBox, QLabel, QSplitter
from PySide6.QtCore import Qt

from src.lin_master import ReceivedFrame
from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFFrameSignal,
    LDFScheduleTable,
    LDFScheduleEntry,
    LDFNodes,
    LDFMaster,
    LDFSignal,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_ldf(master_name="M", slaves=None):
    """Return a minimal LDFFile with frames and schedules."""
    if slaves is None:
        slaves = ["S1"]

    ldf = LDFFile(
        protocol_version="2.1",
        language_version="2.1",
        speed=19.2,
        nodes=LDFNodes(
            master=LDFMaster(name=master_name, time_base=5.0, jitter=0.1),
            slaves=list(slaves),
        ),
        signals=[
            LDFSignal(
                name="Sig1",
                size=8,
                init_value=0,
                publisher=master_name,
                subscribers=list(slaves[:1]) or ["S1"],
            ),
        ],
        frames=[
            LDFFrame(
                name="Frame1",
                frame_id=0x10,
                publisher=master_name,
                frame_size=2,
                signals=[LDFFrameSignal(signal_name="Sig1", bit_offset=0)],
            ),
        ],
        schedule_tables=[
            LDFScheduleTable(
                name="MainSched",
                entries=[LDFScheduleEntry(frame_name="Frame1", delay=10.0)],
            ),
        ],
    )
    ldf.build_lookups()
    return ldf


# ---------------------------------------------------------------------------
# _Bridge tests
# ---------------------------------------------------------------------------

class TestBridge:
    def test_frame_received_signal(self, qapp):
        from src.gui.communication_panel import _Bridge

        bridge = _Bridge()
        received = []
        bridge.frame_received.connect(received.append)
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01\x02", timestamp_ns=1000)
        bridge.frame_received.emit(frame)
        qapp.processEvents()
        assert len(received) == 1
        assert received[0] is frame

    def test_error_occurred_signal(self, qapp):
        from src.gui.communication_panel import _Bridge

        bridge = _Bridge()
        errors = []
        bridge.error_occurred.connect(errors.append)
        bridge.error_occurred.emit("test error")
        qapp.processEvents()
        assert errors == ["test error"]


# ---------------------------------------------------------------------------
# _FrameMonitor tests
# ---------------------------------------------------------------------------

class TestFrameMonitor:
    def test_add_frame_normal(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01\x02", timestamp_ns=5_000_000)
        monitor.add_frame(frame)
        assert monitor._table.rowCount() == 1
        assert monitor._table.item(0, 4).text() == "OK"

    def test_add_frame_crc_error(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        frame = ReceivedFrame(frame_id=0x10, data=b"\xFF", timestamp_ns=1_000_000, crc_error=True)
        monitor.add_frame(frame)
        assert monitor._table.rowCount() == 1
        assert monitor._table.item(0, 4).text() == "CRC ERR"

    def test_max_rows_overflow(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        for i in range(monitor.MAX_ROWS + 10):
            frame = ReceivedFrame(frame_id=i & 0x3F, data=b"\x00", timestamp_ns=i * 1000)
            monitor.add_frame(frame)
        assert monitor._table.rowCount() == monitor.MAX_ROWS

    def test_clear(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        for _ in range(5):
            monitor.add_frame(ReceivedFrame(0x10, b"\x00", 1000))
        assert monitor._table.rowCount() == 5
        monitor._clear()
        assert monitor._table.rowCount() == 0

    def test_export_csv_cancelled(self, qapp):
        """When file dialog is cancelled (empty path), no file is written."""
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.add_frame(ReceivedFrame(0x10, b"\x01\x02", 5_000_000))
        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = ("", "")
            monitor._export_csv()  # Should return without writing

    def test_export_csv_writes_file(self, qapp, tmp_path):
        """A chosen path produces a CSV file with header and data rows."""
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.set_session_metadata({"Frame Publishers": "0x10=M", "Selected Master": "M"})
        monitor.add_frame(ReceivedFrame(0x10, b"\x01\x02", 5_000_000))
        out_path = str(tmp_path / "export.csv")
        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = (out_path, "CSV files (*.csv)")
            monitor._export_csv()
        with open(out_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        header_index = rows.index(monitor.CSV_COLUMNS)
        assert rows[header_index][0] == "Timestamp (ms)"
        assert rows[header_index + 1][2] == "0x10"

    def test_export_csv_empty_table(self, qapp, tmp_path):
        """An empty monitor still produces a valid CSV with only the header."""
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        out_path = str(tmp_path / "empty.csv")
        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = (out_path, "CSV files (*.csv)")
            monitor._export_csv()
        with open(out_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == monitor.CSV_COLUMNS

    def test_toggle_csv_logging_cancelled(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        messages = []
        monitor.status_message.connect(messages.append)

        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = ("", "")
            monitor._toggle_csv_logging()

        assert monitor.is_logging is False
        assert any("cancelled" in message.lower() for message in messages)

    def test_live_csv_logging_writes_rows(self, qapp, tmp_path):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.set_session_metadata(
            {
                "LDF File Name": "network.ldf",
                "Selected Master": "M",
                "Selected Slaves": "S1; S2",
                "Frame Publishers": "0x10=M",
            }
        )
        out_path = str(tmp_path / "live.csv")

        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = (out_path, "CSV files (*.csv)")
            monitor._toggle_csv_logging()

        frame = ReceivedFrame(frame_id=0x10, data=b"\x01\x02", timestamp_ns=5_000_000, checksum=0x5A)
        monitor.add_frame(frame)
        monitor.stop_csv_logging()

        with open(out_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))

        assert rows[0] == ["Session Metadata"]
        assert rows[1] == ["Key", "Value"]
        assert ["LDF File Name", "network.ldf"] in rows
        assert ["Selected Master", "M"] in rows
        assert ["Selected Slaves", "S1; S2"] in rows
        header_index = rows.index(monitor.CSV_COLUMNS)
        assert rows[header_index + 1][0] == "5.000"
        assert rows[header_index + 1][1] == "Master -> Slave"
        assert rows[header_index + 1][2] == "0x10"
        assert rows[header_index + 1][3] == "2"
        assert rows[header_index + 1][4] == "OK"
        assert rows[header_index + 1][5] == "0x5A"
        assert rows[header_index + 1][6] == "01 02"
        assert monitor.is_logging is False

    def test_toggle_csv_logging_stops_active_session(self, qapp, tmp_path):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        out_path = str(tmp_path / "toggle-stop.csv")
        messages = []
        monitor.status_message.connect(messages.append)

        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = (out_path, "CSV files (*.csv)")
            monitor._toggle_csv_logging()

        assert monitor.is_logging is True
        monitor._toggle_csv_logging()

        assert monitor.is_logging is False
        assert any("started" in message.lower() for message in messages)
        assert any("stopped" in message.lower() for message in messages)

    def test_stop_csv_logging_without_active_session(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.stop_csv_logging()
        assert monitor.is_logging is False

    def test_export_csv_includes_metadata_preamble(self, qapp, tmp_path):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.set_session_metadata({"LDF File Name": "session.ldf", "Selected Master": "M"})
        monitor.add_frame(ReceivedFrame(0x10, b"\x01", 1_000_000, checksum=0x99))
        out_path = str(tmp_path / "metadata.csv")

        with patch("src.gui.communication_panel.QFileDialog") as MockDlg:
            MockDlg.getSaveFileName.return_value = (out_path, "CSV files (*.csv)")
            monitor._export_csv()

        with open(out_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))

        assert rows[0] == ["Session Metadata"]
        assert ["LDF File Name", "session.ldf"] in rows
        header_index = rows.index(monitor.CSV_COLUMNS)
        assert rows[header_index + 1][5] == "0x99"

    def test_frame_direction_uses_slave_publisher_metadata(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        monitor.set_session_metadata(
            {
                "Selected Master": "M",
                "Selected Slaves": "S1",
                "Frame Publishers": "0x22=S1",
            }
        )

        record = monitor._frame_to_record(ReceivedFrame(0x22, b"\x10", 1_000_000, checksum=0x77))

        assert record["direction"] == "Slave -> Master"

    def test_frame_direction_unknown_without_matching_metadata(self, qapp):
        from src.gui.communication_panel import _FrameMonitor

        monitor = _FrameMonitor()
        record = monitor._frame_to_record(ReceivedFrame(0x33, b"\x10", 1_000_000))
        assert record["direction"] == "Unknown"


# ---------------------------------------------------------------------------
# CommunicationPanel tests
# ---------------------------------------------------------------------------

@pytest.fixture
def panel(qapp):
    """Create a CommunicationPanel with a mocked LINMaster."""
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master_inst = MagicMock()
        master_inst.is_connected = False
        master_inst.preflight.return_value = (True, "OK")
        MockMaster.return_value = master_inst
        MockMaster.list_lin_channels = MagicMock(return_value=[])

        from src.gui.communication_panel import CommunicationPanel
        p = CommunicationPanel()
        p._master = master_inst
        yield p


class TestCommunicationPanelConstruction:
    def test_panel_created(self, panel):
        assert panel is not None
        assert panel.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_panel_and_explicit_children_have_accessible_metadata(self, panel):
        assert panel.accessibleName() == "Communication panel"
        assert "LIN hardware connection" in panel.accessibleDescription()
        assert panel._monitor.accessibleName() == "Frame monitor panel"
        assert panel._monitor._table.accessibleName() == "Received LIN frame monitor"

        group_boxes = panel.findChildren(QGroupBox)
        assert group_boxes
        assert all(box.accessibleName().strip() for box in group_boxes)
        assert all(box.accessibleDescription().strip() for box in group_boxes)

        splitters = panel.findChildren(QSplitter)
        assert splitters
        assert all(splitter.accessibleName().strip() for splitter in splitters)
        assert all(splitter.accessibleDescription().strip() for splitter in splitters)

        labels = [
            label for label in panel.findChildren(QLabel)
            if label.text() and ("Channel:" in label.text() or "Frame:" in label.text() or "Schedule:" in label.text() or "Data (hex" in label.text() or "Frame Monitor" in label.text())
        ]
        assert labels
        assert all(label.accessibleName().strip() for label in labels)
        assert all(label.accessibleDescription().strip() for label in labels)

        widgets = [
            panel._channel_combo,
            panel._frame_combo,
            panel._data_edit,
            panel._master_response_chk,
            panel._sched_combo,
            panel._changed_only_chk,
            panel._refresh_btn,
            panel._connect_btn,
            panel._send_btn,
            panel._sched_start_btn,
            panel._sched_stop_btn,
            panel._monitor._log_btn,
            panel._monitor._export_btn,
            panel._monitor._clear_btn,
        ]
        assert all(widget.accessibleName().strip() for widget in widgets)
        assert all(widget.accessibleDescription().strip() for widget in widgets)

    def test_panel_has_monitor(self, panel):
        assert panel._monitor is not None

    def test_panel_has_bridge(self, panel):
        assert panel._bridge is not None

    def test_panel_has_changed_only_checkbox(self, panel):
        assert panel._changed_only_chk is not None

    def test_lin_master_created_with_changed_callback(self, qapp):
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            master_inst.preflight.return_value = (True, "OK")
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.communication_panel import CommunicationPanel
            CommunicationPanel()

        assert MockMaster.call_count == 1
        kwargs = MockMaster.call_args.kwargs
        assert "on_frame_changed" in kwargs
        assert callable(kwargs["on_frame_changed"])


class TestCommunicationPanelLoadLdf:
    def test_load_ldf_populates_combos(self, panel):
        ldf = _make_ldf()
        panel._master.is_connected = False
        panel.load_ldf(ldf)
        assert panel._frame_combo.count() == 1
        assert panel._sched_combo.count() == 1
        assert panel._ldf is ldf

    def test_load_ldf_sched_button_disabled_when_disconnected(self, panel):
        ldf = _make_ldf()
        panel._master.is_connected = False
        panel.load_ldf(ldf)
        assert panel._sched_start_btn.isEnabled() is False

    def test_load_ldf_sched_button_enabled_when_connected(self, panel):
        ldf = _make_ldf()
        panel._master.is_connected = True
        panel.load_ldf(ldf)
        assert panel._sched_start_btn.isEnabled() is True

    def test_load_ldf_updates_monitor_metadata(self, panel):
        # Regression test: Windows-style paths (backslashes) must be normalised
        # before os.path.basename so that "C:\temp\network.ldf" yields "network.ldf"
        # on Linux CI runners where backslash is not a path separator.
        ldf = _make_ldf()
        ldf.source_path = r"C:\temp\network.ldf"
        panel.load_ldf(ldf)

        assert panel._monitor._session_metadata["LDF File Name"] == "network.ldf"
        assert panel._monitor._session_metadata["Declared Master"] == "M"
        assert panel._monitor._session_metadata["Declared Slaves"] == "S1"
        assert panel._monitor._session_metadata["Frame Publishers"] == "0x10=M"

    def test_load_ldf_updates_monitor_metadata_unix_path(self, panel):
        # Complement to the Windows-path regression test: verify that Unix-style
        # paths also yield only the basename in "LDF File Name".
        ldf = _make_ldf()
        ldf.source_path = "/home/user/projects/network.ldf"
        panel.load_ldf(ldf)

        assert panel._monitor._session_metadata["LDF File Name"] == "network.ldf"


class TestCommunicationPanelFocus:
    def test_focus_primary_control(self, panel):
        panel.focus_primary_control()
        # Should not raise


class TestCommunicationPanelRefreshChannels:
    def test_refresh_channels_empty(self, panel):
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            MockMaster.list_lin_channels.return_value = []
            panel._refresh_channels()
        assert panel._channel_combo.count() == 1
        assert "No Vector hardware" in panel._channel_combo.itemText(0)

    def test_refresh_channels_with_hardware(self, panel):
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            MockMaster.list_lin_channels.return_value = [
                {"name": "LIN1", "channel_index": 0, "channel_mask": 1},
                {"name": "LIN2", "channel_index": 1, "channel_mask": 2},
            ]
            panel._refresh_channels()
        assert panel._channel_combo.count() == 2


class TestCommunicationPanelToggleConnection:
    def test_toggle_calls_disconnect_when_connected(self, panel):
        panel._master.is_connected = True
        panel._disconnect = MagicMock()
        panel._toggle_connection()
        panel._disconnect.assert_called_once()

    def test_toggle_calls_connect_when_disconnected(self, panel):
        panel._master.is_connected = False
        panel._connect = MagicMock()
        panel._toggle_connection()
        panel._connect.assert_called_once()


class TestCommunicationPanelConnect:
    def test_connect_no_mask(self, panel, qapp):
        """When current channel data is None, status should report no hardware."""
        panel._channel_combo.clear()
        panel._channel_combo.addItem("No hardware", None)
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._connect()
        qapp.processEvents()
        assert any("No hardware" in m for m in messages)
        assert "No hardware" in states

    def test_connect_success(self, panel, qapp):
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._master.connect = MagicMock()
        panel._master.is_connected = True  # after connect
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._connect()
        qapp.processEvents()
        panel._master.connect.assert_called_once_with(channel_mask=1, ldf=panel._ldf)
        assert any("Connected" in m for m in messages)
        assert "Connected" in states
        assert panel._send_btn.isEnabled() is True

    def test_connect_failure(self, panel, qapp):
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._master.connect = MagicMock(side_effect=RuntimeError("hw error"))
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._connect()
        qapp.processEvents()
        assert any("Connection failed" in m for m in messages)
        assert "Error" in states

    def test_connect_success_emits_dll_provenance_bundled(self, panel, qapp):
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._master.connect = MagicMock()
        panel._master.dll_path = "C:/projects/Easy-LIN/third_party/vector/bin/vxlapi64.dll"
        messages = []
        panel.status_message.connect(messages.append)
        panel._connect()
        qapp.processEvents()
        assert any("bundled" in m for m in messages)

    def test_connect_success_emits_dll_provenance_system(self, panel, qapp):
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._master.connect = MagicMock()
        panel._master.dll_path = r"C:\Windows\System32\vxlapi64.dll"
        messages = []
        panel.status_message.connect(messages.append)
        panel._connect()
        qapp.processEvents()
        assert any("system" in m for m in messages)

    def test_connect_success_no_provenance_when_dll_path_none(self, panel, qapp):
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._master.connect = MagicMock()
        panel._master.dll_path = None
        messages = []
        panel.status_message.connect(messages.append)
        panel._connect()
        qapp.processEvents()
        assert not any("Runtime:" in m for m in messages)

    def test_connect_blocked_when_preflight_fails(self, panel, qapp):
        """When preflight returns failure the connect should be aborted."""
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._backend.preflight = MagicMock(return_value=(False, "driver not installed"))
        panel._backend.connect = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._connect()
        qapp.processEvents()
        panel._backend.connect.assert_not_called()
        assert any("preflight" in m.lower() for m in messages)
        assert "Error" in states

    def test_connect_proceeds_when_preflight_ok(self, panel, qapp):
        """When preflight returns (True, 'OK') the connect is attempted normally."""
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._backend.preflight = MagicMock(return_value=(True, "OK"))
        panel._backend.connect = MagicMock()
        panel._backend.dll_path = None
        messages = []
        panel.status_message.connect(messages.append)
        panel._connect()
        qapp.processEvents()
        panel._backend.connect.assert_called_once()

    def test_connect_preflight_in_backend_protocol(self):
        """CommunicationBackend Protocol declares preflight()."""
        from src.gui.communication_panel import CommunicationBackend
        import inspect
        members = {name for name, _ in inspect.getmembers(CommunicationBackend)}
        assert "preflight" in members


class TestVectorBackendAdapterPreflight:
    def test_preflight_delegates_to_master(self):
        from src.gui.communication_panel import VectorBackendAdapter

        adapter = VectorBackendAdapter(
            on_frame_received=lambda _f: None,
            on_error=lambda _m: None,
            on_frame_changed=lambda _f, _p: None,
        )
        adapter._master = MagicMock()
        adapter._master.preflight.return_value = (True, "OK")
        ok, msg = adapter.preflight()
        assert ok is True
        assert msg == "OK"
        adapter._master.preflight.assert_called_once()

    def test_preflight_failure_propagated(self):
        from src.gui.communication_panel import VectorBackendAdapter

        adapter = VectorBackendAdapter(
            on_frame_received=lambda _f: None,
            on_error=lambda _m: None,
            on_frame_changed=lambda _f, _p: None,
        )
        adapter._master = MagicMock()
        adapter._master.preflight.return_value = (False, "driver not running")
        ok, msg = adapter.preflight()
        assert ok is False
        assert "driver not running" in msg


class TestCommunicationPanelDisconnect:
    def test_disconnect_normal(self, panel, qapp):
        panel._master.disconnect = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._disconnect()
        qapp.processEvents()
        panel._master.disconnect.assert_called_once()
        assert any("Disconnected" in m for m in messages)
        assert "Disconnected" in states
        assert panel._send_btn.isEnabled() is False

    def test_disconnect_with_exception(self, panel, qapp):
        panel._master.disconnect = MagicMock(side_effect=RuntimeError("close error"))
        messages = []
        panel.status_message.connect(messages.append)
        panel._disconnect()
        qapp.processEvents()
        # Should still complete and emit Disconnected
        assert any("Disconnected" in m for m in messages)


class TestCommunicationPanelOnFrameSelected:
    def test_on_frame_selected_prefills_data(self, panel):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        # The data edit should contain zeroes matching the frame size
        expected = "00 00"
        assert panel._data_edit.text() == expected

    def test_on_frame_selected_no_data(self, panel):
        panel._frame_combo.clear()
        panel._on_frame_selected(0)
        # Should not crash


class TestCommunicationPanelSendFrame:
    def test_send_frame_no_frame_selected(self, panel):
        panel._frame_combo.clear()
        panel._send_frame()  # Should return silently

    def test_send_frame_master_request(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        panel._master_response_chk.setChecked(False)
        panel._master.send_frame = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        panel._send_frame()
        qapp.processEvents()
        panel._master.send_frame.assert_called_once_with(0x10)
        assert any("master request" in m for m in messages)

    def test_send_frame_master_request_exception(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        panel._master_response_chk.setChecked(False)
        panel._master.send_frame = MagicMock(side_effect=RuntimeError("tx err"))
        messages = []
        panel.status_message.connect(messages.append)
        panel._send_frame()
        qapp.processEvents()
        assert any("TX error" in m for m in messages)

    def test_send_frame_master_response(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        panel._master_response_chk.setChecked(True)
        panel._data_edit.setText("01 FF")
        panel._master.send_frame_data = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        panel._send_frame()
        qapp.processEvents()
        panel._master.send_frame_data.assert_called_once_with(0x10, [0x01, 0xFF])
        assert any("master response" in m for m in messages)

    def test_send_frame_master_response_exception(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        panel._master_response_chk.setChecked(True)
        panel._data_edit.setText("01 FF")
        panel._master.send_frame_data = MagicMock(side_effect=RuntimeError("tx err"))
        messages = []
        panel.status_message.connect(messages.append)
        panel._send_frame()
        qapp.processEvents()
        assert any("TX error" in m for m in messages)

    def test_send_frame_invalid_hex(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._frame_combo.setCurrentIndex(0)
        panel._master_response_chk.setChecked(True)
        panel._data_edit.setText("ZZ GG")
        messages = []
        panel.status_message.connect(messages.append)
        panel._send_frame()
        qapp.processEvents()
        assert any("Invalid hex" in m for m in messages)


class TestCommunicationPanelSchedule:
    def test_run_schedule_success(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._sched_combo.setCurrentIndex(0)
        panel._master.run_schedule = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        panel._run_schedule()
        qapp.processEvents()
        panel._master.run_schedule.assert_called_once()
        assert panel._sched_start_btn.isEnabled() is False
        assert panel._sched_stop_btn.isEnabled() is True
        assert any("Running schedule" in m for m in messages)

    def test_run_schedule_failure(self, panel, qapp):
        ldf = _make_ldf()
        panel.load_ldf(ldf)
        panel._sched_combo.setCurrentIndex(0)
        panel._master.run_schedule = MagicMock(side_effect=RuntimeError("sched err"))
        messages = []
        panel.status_message.connect(messages.append)
        panel._run_schedule()
        qapp.processEvents()
        assert any("Schedule start error" in m for m in messages)

    def test_run_schedule_no_sched(self, panel):
        panel._sched_combo.clear()
        panel._run_schedule()  # Should return silently (sched is None)

    def test_stop_schedule(self, panel, qapp):
        panel._master.stop_schedule = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)
        panel._stop_schedule()
        qapp.processEvents()
        panel._master.stop_schedule.assert_called_once()
        assert panel._sched_start_btn.isEnabled() is True
        assert panel._sched_stop_btn.isEnabled() is False
        assert any("Schedule stopped" in m for m in messages)


class TestCommunicationPanelCallbacks:
    def test_on_frame_received_emits_bridge_signal(self, panel, qapp):
        received = []
        panel._bridge.frame_received.connect(received.append)
        panel._changed_only_chk.setChecked(False)
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01", timestamp_ns=1000)
        panel._on_frame_received(frame)
        qapp.processEvents()
        assert len(received) == 1

    def test_on_frame_received_filtered_when_changed_only(self, panel, qapp):
        received = []
        panel._bridge.frame_received.connect(received.append)
        panel._changed_only_chk.setChecked(True)
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01", timestamp_ns=1000)
        panel._on_frame_received(frame)
        qapp.processEvents()
        assert len(received) == 0

    def test_on_frame_changed_emits_when_changed_only(self, panel, qapp):
        received = []
        panel._bridge.frame_received.connect(received.append)
        panel._changed_only_chk.setChecked(True)
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01", timestamp_ns=1000)
        panel._on_frame_changed(frame, None)
        qapp.processEvents()
        assert len(received) == 1

    def test_on_frame_changed_ignored_when_show_all(self, panel, qapp):
        received = []
        panel._bridge.frame_received.connect(received.append)
        panel._changed_only_chk.setChecked(False)
        frame = ReceivedFrame(frame_id=0x10, data=b"\x01", timestamp_ns=1000)
        panel._on_frame_changed(frame, None)
        qapp.processEvents()
        assert len(received) == 0

    def test_on_error_emits_bridge_signal(self, panel, qapp):
        errors = []
        panel._bridge.error_occurred.connect(errors.append)
        panel._on_error("test error")
        qapp.processEvents()
        assert errors == ["test error"]

    def test_monitor_add_frame(self, panel, qapp):
        frame = ReceivedFrame(frame_id=0x10, data=b"\xAA\xBB", timestamp_ns=5_000_000)
        panel._monitor_add_frame(frame)
        assert panel._monitor._table.rowCount() == 1

    def test_monitor_status_messages_are_forwarded(self, panel, qapp):
        messages = []
        panel.status_message.connect(messages.append)

        panel._monitor.status_message.emit("CSV logging started")
        qapp.processEvents()

        assert "CSV logging started" in messages

    def test_show_error(self, panel, qapp):
        messages = []
        panel.status_message.connect(messages.append)
        states = []
        panel.communication_state_changed.connect(states.append)
        panel._show_error("hw problem")
        qapp.processEvents()
        assert any("Hardware error" in m for m in messages)
        assert "Error" in states

    def test_monitor_filter_toggle_emits_enabled_message(self, panel, qapp):
        messages = []
        panel.status_message.connect(messages.append)
        panel._changed_only_chk.setChecked(True)
        qapp.processEvents()
        assert any("filter enabled" in m.lower() for m in messages)

    def test_monitor_filter_toggle_emits_disabled_message(self, panel, qapp):
        panel._changed_only_chk.setChecked(True)
        qapp.processEvents()
        messages = []
        panel.status_message.connect(messages.append)
        panel._changed_only_chk.setChecked(False)
        qapp.processEvents()
        assert any("filter disabled" in m.lower() for m in messages)

    def test_configure_selection_sets_gate(self, panel):
        panel.load_ldf(_make_ldf(slaves=["S1", "S2"]))
        panel.configure_selection("M", ["S1", "S2"])
        assert panel._selection is not None
        assert panel._selection.master == "M"
        assert list(panel._selection.slaves) == ["S1", "S2"]
        assert panel._monitor._session_metadata["Selected Master"] == "M"
        assert panel._monitor._session_metadata["Selected Slaves"] == "S1; S2"

    def test_configure_selection_rejects_selection_without_ldf(self, panel):
        panel.configure_selection("M", ["S1"])

        assert panel._selection is None
        assert panel._monitor._session_metadata.get("Selected Master", "") == ""
        assert panel._monitor._session_metadata.get("Selected Slaves", "") == ""

    def test_configure_selection_rejects_invalid_master(self, panel):
        panel.load_ldf(_make_ldf(master_name="DeclaredMaster", slaves=["S1", "S2"]))

        panel.configure_selection("OtherMaster", ["S1"])

        assert panel._selection is None
        assert panel._monitor._session_metadata.get("Selected Master", "") == ""
        assert panel._monitor._session_metadata.get("Selected Slaves", "") == ""

    def test_configure_selection_rejects_invalid_slave(self, panel):
        panel.load_ldf(_make_ldf(slaves=["S1", "S2"]))

        panel.configure_selection("M", ["S1", "OtherSlave"])

        assert panel._selection is None
        assert panel._monitor._session_metadata.get("Selected Master", "") == ""
        assert panel._monitor._session_metadata.get("Selected Slaves", "") == ""

    def test_connect_with_ldf_without_selection_is_blocked(self, panel, qapp):
        panel._ldf = MagicMock()
        panel._selection = None
        panel._channel_combo.clear()
        panel._channel_combo.addItem("LIN1", 1)
        panel._backend.connect = MagicMock()
        messages = []
        panel.status_message.connect(messages.append)

        panel._connect()
        qapp.processEvents()

        panel._backend.connect.assert_not_called()
        assert any("select one master" in m.lower() for m in messages)

    def test_panel_stop_csv_logging_delegates_to_monitor(self, panel):
        panel._monitor.stop_csv_logging = MagicMock()

        panel.stop_csv_logging()

        panel._monitor.stop_csv_logging.assert_called_once()


class TestVectorBackendAdapter:
    def test_adapter_forwards_send_calls(self):
        from src.gui.communication_panel import VectorBackendAdapter

        adapter = VectorBackendAdapter(
            on_frame_received=lambda _f: None,
            on_error=lambda _m: None,
            on_frame_changed=lambda _f, _p: None,
        )
        adapter._master = MagicMock()

        adapter.send_frame(0x10)
        adapter.send_frame_data(0x11, [1, 2])

        adapter._master.send_frame.assert_called_once_with(0x10)
        adapter._master.send_frame_data.assert_called_once_with(0x11, [1, 2])

    def test_adapter_dll_path_delegates_to_master(self):
        from src.gui.communication_panel import VectorBackendAdapter

        adapter = VectorBackendAdapter(
            on_frame_received=lambda _f: None,
            on_error=lambda _m: None,
            on_frame_changed=lambda _f, _p: None,
        )
        adapter._master = MagicMock()
        adapter._master.dll_path = r"C:\path\vxlapi64.dll"
        assert adapter.dll_path == r"C:\path\vxlapi64.dll"

    def test_adapter_dll_path_none_when_master_lacks_attribute(self):
        from src.gui.communication_panel import VectorBackendAdapter

        adapter = VectorBackendAdapter(
            on_frame_received=lambda _f: None,
            on_error=lambda _m: None,
            on_frame_changed=lambda _f, _p: None,
        )

        class _NoDllPath:  # no dll_path attribute
            pass

        adapter._master = _NoDllPath()
        assert adapter.dll_path is None
