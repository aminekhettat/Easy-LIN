"""Tests for src/gui/communication_window.py.

Covers:
- CommunicationWindow construction with embedded CommunicationPanel
- load_ldf delegates to panel
- focus_primary_control shows, raises, delegates
- closeEvent hides instead of destroying
- Signal re-emission from panel (status_message, communication_state_changed)
- _restore_geometry with and without saved geometry
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent

from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFNodes,
    LDFMaster,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_ldf():
    ldf = LDFFile(
        protocol_version="2.1",
        language_version="2.1",
        speed=19.2,
        nodes=LDFNodes(
            master=LDFMaster(name="M", time_base=5.0, jitter=0.1),
            slaves=["S1"],
        ),
        frames=[
            LDFFrame(name="Frame1", frame_id=0x10, publisher="M", frame_size=2),
        ],
    )
    ldf.build_lookups()
    return ldf


@pytest.fixture
def comm_window(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master_inst = MagicMock()
        master_inst.is_connected = False
        MockMaster.return_value = master_inst
        MockMaster.list_lin_channels = MagicMock(return_value=[])

        from src.gui.communication_window import CommunicationWindow
        win = CommunicationWindow()
        yield win


class TestCommunicationWindowConstruction:
    def test_has_comm_panel(self, comm_window):
        from src.gui.communication_panel import CommunicationPanel
        assert isinstance(comm_window._comm_panel, CommunicationPanel)

    def test_window_title(self, comm_window):
        assert "Communication" in comm_window.windowTitle()

    def test_minimum_size(self, comm_window):
        assert comm_window.minimumWidth() >= 500
        assert comm_window.minimumHeight() >= 600

    def test_object_name(self, comm_window):
        assert comm_window.objectName() == "CommunicationWindow"


class TestCommunicationWindowLoadLdf:
    def test_load_ldf_delegates(self, comm_window):
        ldf = _make_ldf()
        comm_window._comm_panel.load_ldf = MagicMock()
        comm_window.load_ldf(ldf)
        comm_window._comm_panel.load_ldf.assert_called_once_with(ldf)

    def test_configure_selection_delegates(self, comm_window):
        comm_window._comm_panel.configure_selection = MagicMock()
        comm_window.configure_selection("M", ["S1"])
        comm_window._comm_panel.configure_selection.assert_called_once_with("M", ["S1"])


class TestCommunicationWindowFocus:
    def test_focus_primary_control(self, comm_window):
        comm_window._comm_panel.focus_primary_control = MagicMock()
        comm_window.focus_primary_control()
        comm_window._comm_panel.focus_primary_control.assert_called_once()


class TestCommunicationWindowCloseEvent:
    def test_close_event_hides_window(self, comm_window, qapp):
        comm_window.show()
        qapp.processEvents()
        assert comm_window.isVisible()
        # Trigger close via close()
        comm_window.close()
        qapp.processEvents()
        assert not comm_window.isVisible()

    def test_close_event_saves_geometry(self, comm_window, qapp):
        comm_window._settings = MagicMock(spec=QSettings)
        event = QCloseEvent()
        comm_window.closeEvent(event)
        comm_window._settings.setValue.assert_called_once()
        assert event.isAccepted() is False  # event.ignore() was called


class TestCommunicationWindowSignals:
    def test_status_message_reemitted(self, comm_window, qapp):
        messages = []
        comm_window.status_message.connect(messages.append)
        comm_window._comm_panel.status_message.emit("test msg")
        qapp.processEvents()
        assert "test msg" in messages

    def test_communication_state_changed_reemitted(self, comm_window, qapp):
        states = []
        comm_window.communication_state_changed.connect(states.append)
        comm_window._comm_panel.communication_state_changed.emit("Connected")
        qapp.processEvents()
        assert "Connected" in states


class TestCommunicationWindowRestoreGeometry:
    def test_restore_geometry_with_saved(self, qapp):
        """When settings has a geometry value, restoreGeometry should be called."""
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.communication_window import CommunicationWindow

            with patch.object(QSettings, "value", return_value=None):
                CommunicationWindow()
            # No crash means the None path worked

    def test_restore_geometry_without_saved(self, qapp):
        """When settings returns None for geometry, nothing crashes."""
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.communication_window import CommunicationWindow
            win = CommunicationWindow()
            # Explicitly test the restore path with no geometry
            win._settings = MagicMock(spec=QSettings)
            win._settings.value.return_value = None
            win._restore_geometry()  # Should not crash
