"""Integration-style tests for communication window."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_hardware_combobox_populated_on_startup(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        MockMaster.return_value = MagicMock(is_connected=False)
        MockMaster.list_lin_channels.return_value = [
            {"name": "LIN1", "channel_index": 0, "channel_mask": 1}
        ]
        from src.gui.communication_window import CommunicationWindow

        win = CommunicationWindow()
        assert win._comm_panel._channel_combo.count() >= 1


def test_connect_button_enables_on_channel_selected(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master = MagicMock(is_connected=False)
        MockMaster.return_value = master
        MockMaster.list_lin_channels.return_value = [
            {"name": "LIN1", "channel_index": 0, "channel_mask": 1}
        ]
        from src.gui.communication_window import CommunicationWindow

        win = CommunicationWindow()
        win._comm_panel._channel_combo.setCurrentIndex(0)
        assert win._comm_panel._connect_btn.isEnabled() is True


def test_connect_button_triggers_lin_controller_connect(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master = MagicMock(is_connected=False)
        master.preflight.return_value = (True, "OK")
        MockMaster.return_value = master
        MockMaster.list_lin_channels.return_value = [
            {
                "name": "LIN1",
                "channel_index": 0,
                "channel_mask": 1,
            }
        ]
        from src.gui.communication_window import CommunicationWindow

        win = CommunicationWindow()
        win._comm_panel._connect()
        master.connect.assert_called_once()


def test_disconnect_button_triggers_lin_controller_disconnect(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master = MagicMock(is_connected=True)
        MockMaster.return_value = master
        MockMaster.list_lin_channels.return_value = [
            {"name": "LIN1", "channel_index": 0, "channel_mask": 1}
        ]
        from src.gui.communication_window import CommunicationWindow

        win = CommunicationWindow()
        win._comm_panel._disconnect()
        master.disconnect.assert_called_once()
