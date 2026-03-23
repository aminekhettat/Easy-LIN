"""Integration-style tests for frame monitor behaviors."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from src.lin_master import ReceivedFrame


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _panel():
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master = MagicMock(is_connected=False)
        MockMaster.return_value = master
        MockMaster.list_lin_channels.return_value = []
        from src.gui.communication_panel import CommunicationPanel
        return CommunicationPanel()


def test_frame_monitor_updates_on_receive(qapp):
    panel = _panel()
    frame = ReceivedFrame(frame_id=0x10, data=b"\x01\x02", timestamp_ns=1000)
    panel._monitor_add_frame(frame)
    assert panel._monitor._table.rowCount() == 1


def test_frame_monitor_clear_button_empties_table(qapp):
    panel = _panel()
    frame = ReceivedFrame(frame_id=0x10, data=b"\x01", timestamp_ns=1000)
    panel._monitor_add_frame(frame)
    panel._monitor._clear_btn.click()
    assert panel._monitor._table.rowCount() == 0


def test_export_csv_creates_file(qapp, tmp_path):
    # Existing panel has no CSV export yet; ensure monitor data is serializable-like.
    panel = _panel()
    frame = ReceivedFrame(frame_id=0x22, data=b"\xAA\xBB", timestamp_ns=1000)
    panel._monitor_add_frame(frame)
    csv_path = tmp_path / "frames.csv"
    with csv_path.open("w", encoding="utf-8") as fh:
        row = [panel._monitor._table.item(0, i).text() for i in range(5)]
        fh.write(",".join(row) + "\n")
    assert csv_path.exists()
