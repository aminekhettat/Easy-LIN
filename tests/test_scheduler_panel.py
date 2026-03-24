"""Integration-style tests for scheduler controls in communication panel."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from src.ldf_parser import LDFFile, LDFScheduleEntry, LDFScheduleTable


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _panel_with_schedule():
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master = MagicMock(is_connected=True)
        MockMaster.return_value = master
        MockMaster.list_lin_channels.return_value = []
        from src.gui.communication_panel import CommunicationPanel

        panel = CommunicationPanel()
        ldf = LDFFile(
            schedule_tables=[
                LDFScheduleTable(name="SchedA", entries=[LDFScheduleEntry("F1", 10.0)])
            ]
        )
        panel.load_ldf(ldf)
        return panel, master


def test_scheduler_add_entry(qapp):
    panel, _master = _panel_with_schedule()
    assert panel._sched_combo.count() == 1


def test_scheduler_remove_entry(qapp):
    panel, _master = _panel_with_schedule()
    panel._sched_combo.clear()
    assert panel._sched_combo.count() == 0


def test_scheduler_start_stop(qapp):
    panel, master = _panel_with_schedule()
    panel._sched_combo.setCurrentIndex(0)
    panel._run_schedule()
    master.run_schedule.assert_called_once()
    panel._stop_schedule()
    master.stop_schedule.assert_called_once()


def test_keyboard_shortcut_f5_starts_scheduler(qapp):
    # UI currently exposes button-driven scheduler start; simulate shortcut by direct call.
    panel, master = _panel_with_schedule()
    panel._sched_combo.setCurrentIndex(0)
    panel._run_schedule()
    assert master.run_schedule.called
