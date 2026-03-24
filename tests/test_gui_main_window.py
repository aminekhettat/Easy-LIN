"""Additional tests for src/gui/main_window_qt.py to cover untested paths.

Covers:
- _open_ldf with file dialog (monkeypatch QFileDialog.getOpenFileName)
- _load_ldf error paths: FileNotFoundError, LDFParseError, generic Exception
- _load_ldf parse-success announcement: "Parse successful", master name, slave count
- _add_recent and _update_recent_menu (with duplicates, max 10)
- _show_about dialog
- _show_accessibility_help
- _open_vector_docs (mock webbrowser.open)
- _load_logo_pixmap with existing and non-existing paths
- _restore_geometry with and without saved geometry
- closeEvent persists geometry and closes comm window
- _toggle_communication_window (show/hide)
- _focus_ldf_details compatibility alias
- _set_status_label_color with invalid color
- _build_about_html
- _build_issues_report_text
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
    QLabel,
    QDialog,
    QPushButton,
    QListWidget,
    QDialogButtonBox,
    QComboBox,
    QPlainTextEdit,
    QTextBrowser,
)
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent

from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFFrameSignal,
    LDFNodes,
    LDFMaster,
    LDFSignal,
    LDFParseError,
    LDFScheduleTable,
    LDFScheduleEntry,
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
        signals=[
            LDFSignal(name="Sig1", size=8, init_value=0, publisher="M", subscribers=["S1"]),
        ],
        frames=[
            LDFFrame(
                name="Frame1",
                frame_id=0x10,
                publisher="M",
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


@pytest.fixture
def main_window(qapp):
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master_inst = MagicMock()
        master_inst.is_connected = False
        MockMaster.return_value = master_inst
        MockMaster.list_lin_channels = MagicMock(return_value=[])

        from src.gui.main_window_qt import MainWindow

        win = MainWindow()
        yield win


# ---------------------------------------------------------------------------
# _open_ldf with file dialog
# ---------------------------------------------------------------------------


class TestOpenLdf:
    def test_load_ldf_file_wrapper_calls_load_ldf(self, main_window):
        main_window._load_ldf = MagicMock()
        main_window.load_ldf_file("/tmp/wrapper.ldf")
        main_window._load_ldf.assert_called_once_with("/tmp/wrapper.ldf")

    def test_open_ldf_dialog_cancel(self, main_window, monkeypatch):
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **kw: ("", "")),
        )
        main_window._load_ldf = MagicMock()
        main_window._open_ldf()
        main_window._load_ldf.assert_not_called()

    def test_open_ldf_dialog_select_file(self, main_window, monkeypatch):
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **kw: ("/tmp/test.ldf", "LIN Description Files (*.ldf)")),
        )
        main_window._load_ldf = MagicMock()
        main_window._open_ldf()
        main_window._load_ldf.assert_called_once_with("/tmp/test.ldf")


# ---------------------------------------------------------------------------
# _load_ldf error paths
# ---------------------------------------------------------------------------


class TestLoadLdfErrors:
    def test_load_ldf_file_not_found(self, main_window, monkeypatch):
        monkeypatch.setattr(
            "src.gui.main_window_qt.parse_ldf",
            MagicMock(side_effect=FileNotFoundError("not found")),
        )
        with patch.object(QMessageBox, "critical"):
            main_window._load_ldf("/nonexistent.ldf")
        # Should not set _ldf
        assert main_window._ldf is None

    def test_load_ldf_parse_error(self, main_window, monkeypatch):
        monkeypatch.setattr(
            "src.gui.main_window_qt.parse_ldf",
            MagicMock(side_effect=LDFParseError("bad syntax")),
        )
        with patch.object(QMessageBox, "critical"):
            main_window._load_ldf("/bad.ldf")
        assert main_window._ldf is None

    def test_load_ldf_generic_exception(self, main_window, monkeypatch):
        monkeypatch.setattr(
            "src.gui.main_window_qt.parse_ldf",
            MagicMock(side_effect=RuntimeError("unexpected")),
        )
        with patch.object(QMessageBox, "critical"):
            main_window._load_ldf("/error.ldf")
        assert main_window._ldf is None

    def test_load_ldf_success(self, main_window, monkeypatch):
        ldf = _make_ldf()
        monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
        monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
        main_window._load_ldf("/good.ldf")
        assert main_window._ldf is ldf

    def test_load_ldf_announces_parse_success_with_master_and_slaves(
        self, main_window, monkeypatch
    ):
        """Screen reader must hear 'Parse successful', master name, and slave count on load."""
        ldf = _make_ldf()  # 1 master "M", 1 slave "S1", 1 frame
        monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
        monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
        events: list[tuple[str, bool]] = []
        monkeypatch.setattr(
            main_window,
            "_announce_event",
            lambda message, timeout_ms=5000, assertive=False: events.append((message, assertive)),
        )
        main_window._load_ldf("/good.ldf")
        assert events, "No announcement was made after loading"
        msg, is_assertive = events[-1]
        assert "Parse successful" in msg
        assert "1 master" in msg
        assert "M" in msg  # master name
        assert "1 slave" in msg  # slave count
        assert is_assertive, "Parse success announcement must be assertive for screen readers"

    def test_focus_ldf_tree_silent_does_not_announce_focus(self, main_window, monkeypatch):
        """_focus_ldf_tree_silent must not emit a 'Focus:' announcement (avoids overwriting parse msg)."""

        ldf = _make_ldf()
        monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
        monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))

        # Load so there is an LDFViewer as central widget.
        main_window._load_ldf("/good.ldf")

        events: list[str] = []
        monkeypatch.setattr(
            main_window,
            "_announce_event",
            lambda message, timeout_ms=5000, assertive=False: events.append(message),
        )
        main_window._focus_ldf_tree_silent()

        assert not any("Focus" in e for e in events), (
            "_focus_ldf_tree_silent must not emit a Focus announcement"
        )

    def test_load_ldf_success_refreshes_existing_viewer(self, main_window, monkeypatch):
        from src.gui.ldf_viewer import LDFViewer

        first_ldf = _make_ldf()
        second_ldf = _make_ldf()
        monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
        monkeypatch.setattr(
            "src.gui.main_window_qt.parse_ldf",
            MagicMock(side_effect=[first_ldf, second_ldf]),
        )

        main_window._load_ldf("/good1.ldf")
        viewer = main_window.centralWidget()
        assert isinstance(viewer, LDFViewer)

        with patch.object(viewer, "refresh") as refresh:
            main_window._load_ldf("/good2.ldf")
        refresh.assert_called_once_with(second_ldf)


# ---------------------------------------------------------------------------
# _add_recent and _update_recent_menu
# ---------------------------------------------------------------------------


class TestRecentFiles:
    def test_add_recent(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = []
        main_window._add_recent("/path/a.ldf")
        main_window._settings.setValue.assert_called()

    def test_add_recent_duplicate(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = ["/path/a.ldf", "/path/b.ldf"]
        main_window._add_recent("/path/a.ldf")
        # a.ldf should be moved to the front
        call_args = main_window._settings.setValue.call_args
        assert call_args[0][0] == "recent_files"
        recent = call_args[0][1]
        assert recent[0] == "/path/a.ldf"

    def test_add_recent_max_ten(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        existing = [f"/path/{i}.ldf" for i in range(12)]
        main_window._settings.value.return_value = existing
        main_window._add_recent("/path/new.ldf")
        call_args = main_window._settings.setValue.call_args
        recent = call_args[0][1]
        assert len(recent) <= 10

    def test_update_recent_menu_empty(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = []
        main_window._update_recent_menu()
        actions = main_window._recent_menu.actions()
        assert len(actions) == 1
        assert not actions[0].isEnabled()

    def test_update_recent_menu_with_entries(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = ["/path/a.ldf", "/path/b.ldf"]
        main_window._update_recent_menu()
        actions = main_window._recent_menu.actions()
        assert len(actions) == 2


# ---------------------------------------------------------------------------
# _show_about dialog
# ---------------------------------------------------------------------------


class TestShowAbout:
    def test_show_about_does_not_crash(self, main_window, monkeypatch):
        """Patch exec on the dialog so it returns immediately."""
        from PySide6.QtWidgets import QDialog

        monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
        main_window._show_about()

    def test_show_about_sets_accessible_metadata(self, main_window, monkeypatch):
        captured = {}

        def _fake_exec(dialog):
            captured["dialog_name"] = dialog.accessibleName()
            captured["dialog_description"] = dialog.accessibleDescription()
            about_text = dialog.findChildren(QTextBrowser)[0]
            captured["about_description"] = about_text.accessibleDescription()
            close_buttons = [
                button for button in dialog.findChildren(QPushButton) if "Close" in button.text()
            ]
            captured["close_name"] = close_buttons[0].accessibleName()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        main_window._show_about()

        assert captured["dialog_name"] == "About Easy-LIN dialog"
        assert "Application information" in captured["dialog_description"]
        assert "Version, author, contact" in captured["about_description"]
        assert captured["close_name"] == "Close About dialog"


class TestMainWindowAccessibilityMetadata:
    def test_main_window_core_widgets_have_accessible_metadata(self, main_window):
        assert main_window.accessibleName() == "Easy-LIN main window"
        assert "Main application window" in main_window.accessibleDescription()
        assert main_window._placeholder.accessibleName() == "Welcome placeholder"
        assert (
            main_window._placeholder.accessibleDescription()
            == "Placeholder view shown before an LDF file is loaded."
        )
        assert main_window._sb_ldf.accessibleName() == "LDF summary status"
        assert main_window._sb_ldf.accessibleDescription().strip()
        assert main_window._sb_issues.accessibleDescription().strip()
        assert main_window._sb_comm.accessibleDescription().strip()
        assert main_window._sb_event.accessibleDescription().strip()

    def test_show_about_falls_back_to_company_text_when_logo_missing(
        self, main_window, monkeypatch
    ):
        from src.gui.main_window_qt import APP_COMPANY, MainWindow

        captured = {"found_company_text": False}

        monkeypatch.setattr(MainWindow, "_load_logo_pixmap", staticmethod(lambda _path: None))

        def _fake_exec(dialog):
            labels = dialog.findChildren(QLabel)
            captured["found_company_text"] = any(lbl.text() == APP_COMPANY for lbl in labels)
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)
        main_window._show_about()
        assert captured["found_company_text"] is True


# ---------------------------------------------------------------------------
# _show_accessibility_help
# ---------------------------------------------------------------------------


class TestShowAccessibilityHelp:
    def test_show_accessibility_help(self, main_window, monkeypatch):
        captured = {}

        def _fake_exec(box):
            captured["title"] = box.windowTitle()
            captured["name"] = box.accessibleName()
            captured["description"] = box.accessibleDescription()
            captured["text"] = box.text()
            return QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QMessageBox, "exec", _fake_exec)

        main_window._show_accessibility_help()

        assert captured["title"] == "Easy-LIN Accessibility"
        assert captured["name"] == "Accessibility help dialog"
        assert "Keyboard shortcut reference" in captured["description"]
        assert "Ctrl+1: Focus hierarchy tree" in captured["text"]


# ---------------------------------------------------------------------------
# _open_vector_docs
# ---------------------------------------------------------------------------


class TestOpenVectorDocs:
    def test_open_vector_docs(self, monkeypatch):
        mock_open = MagicMock()
        monkeypatch.setattr("webbrowser.open", mock_open)
        from src.gui.main_window_qt import MainWindow

        MainWindow._open_vector_docs()
        mock_open.assert_called_once()
        assert "vector.com" in mock_open.call_args[0][0]


# ---------------------------------------------------------------------------
# _load_logo_pixmap
# ---------------------------------------------------------------------------


class TestLoadLogoPixmap:
    def test_load_logo_nonexistent(self):
        from src.gui.main_window_qt import MainWindow

        result = MainWindow._load_logo_pixmap("/nonexistent/path/logo.png")
        assert result is None

    def test_load_logo_existing_invalid(self, tmp_path):
        """An existing file that is not a valid image should return None."""
        from src.gui.main_window_qt import MainWindow

        fake_img = tmp_path / "fake.png"
        fake_img.write_bytes(b"not an image")
        result = MainWindow._load_logo_pixmap(str(fake_img))
        assert result is None


# ---------------------------------------------------------------------------
# _restore_geometry
# ---------------------------------------------------------------------------


class TestRestoreGeometry:
    def test_restore_geometry_with_saved(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = main_window.saveGeometry()
        main_window._restore_geometry()
        # Should not crash

    def test_restore_geometry_without_saved(self, main_window):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._settings.value.return_value = None
        main_window._restore_geometry()
        # Should not crash


# ---------------------------------------------------------------------------
# closeEvent
# ---------------------------------------------------------------------------


class TestCloseEvent:
    def test_close_event_persists_geometry(self, main_window, qapp):
        main_window._settings = MagicMock(spec=QSettings)
        main_window._comm_window._settings = MagicMock(spec=QSettings)
        event = QCloseEvent()
        main_window.closeEvent(event)
        main_window._settings.setValue.assert_called()

    def test_close_event_closes_comm_window(self, main_window, qapp):
        main_window._comm_window._settings = MagicMock(spec=QSettings)
        main_window._settings = MagicMock(spec=QSettings)
        event = QCloseEvent()
        main_window.closeEvent(event)
        # comm_window should have deleteLater called (or at least geometry saved)
        main_window._comm_window._settings.setValue.assert_called()


# ---------------------------------------------------------------------------
# _toggle_communication_window
# ---------------------------------------------------------------------------


class TestToggleCommunicationWindow:
    def test_toggle_show(self, main_window, qapp):
        main_window._ensure_comm_selection = MagicMock(return_value=True)
        main_window._comm_window.hide()
        qapp.processEvents()
        assert not main_window._comm_window.isVisible()
        main_window._toggle_communication_window()
        qapp.processEvents()
        assert main_window._comm_window.isVisible()

    def test_toggle_hide(self, main_window, qapp):
        main_window._ensure_comm_selection = MagicMock(return_value=True)
        main_window._comm_window.show()
        qapp.processEvents()
        main_window._toggle_communication_window()
        qapp.processEvents()
        assert not main_window._comm_window.isVisible()

    def test_toggle_show_cancelled_when_selection_missing(self, main_window, qapp):
        main_window._ensure_comm_selection = MagicMock(return_value=False)
        main_window._comm_window.hide()
        main_window._toggle_communication_window()
        qapp.processEvents()
        assert not main_window._comm_window.isVisible()


class TestCommunicationSelectionFlow:
    def test_resolve_node_choices_without_ldf(self, main_window):
        main_window._ldf = None
        masters, slaves = main_window._resolve_node_choices()
        assert masters == []
        assert slaves == []

    def test_resolve_node_choices_with_list_master_branch(self, main_window):
        ldf = _make_ldf()
        ldf.nodes.master = ["M1", "M2"]
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf
        masters, slaves = main_window._resolve_node_choices()
        assert masters == ["M1", "M2"]
        assert slaves == ["S1", "S2"]

    def test_prompt_comm_selection_single_single_fast_path(self, main_window):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1"]
        main_window._ldf = ldf
        assert main_window._prompt_comm_selection() == ("M", ["S1"])

    def test_prompt_comm_selection_missing_master(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.master = []
        main_window._ldf = ldf
        monkeypatch.setattr(
            QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        )
        assert main_window._prompt_comm_selection() is None

    def test_prompt_comm_selection_missing_slave(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = []
        main_window._ldf = ldf
        monkeypatch.setattr(
            QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        )
        assert main_window._prompt_comm_selection() is None

    def test_prompt_comm_selection_cancelled_dialog(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf
        monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)
        assert main_window._prompt_comm_selection() is None

    def test_prompt_comm_selection_requires_one_slave(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf

        warned = {"value": False}

        def _warning(*_args, **_kwargs):
            warned["value"] = True
            return QMessageBox.StandardButton.Ok

        def _fake_exec(dialog):
            slave_list = dialog.findChildren(QListWidget)[0]
            slave_list.clearSelection()
            box = dialog.findChildren(QDialogButtonBox)[0]
            box.button(QDialogButtonBox.StandardButton.Ok).click()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))
        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        assert main_window._prompt_comm_selection() is None
        assert warned["value"] is True

    def test_prompt_comm_selection_accepts_and_returns_values(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf
        monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

        selection = main_window._prompt_comm_selection()
        assert selection is not None
        assert selection[0] == "M"
        assert selection[1] == ["S1", "S2"]

    def test_prompt_comm_selection_accept_button_path(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf

        def _fake_exec(dialog):
            box = dialog.findChildren(QDialogButtonBox)[0]
            box.button(QDialogButtonBox.StandardButton.Ok).click()
            return dialog.result()

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        selection = main_window._prompt_comm_selection()
        assert selection is not None
        assert selection[0] == "M"
        assert selection[1] == ["S1", "S2"]

    def test_prompt_comm_selection_dialog_has_accessible_metadata(self, main_window, monkeypatch):
        ldf = _make_ldf()
        ldf.nodes.slaves = ["S1", "S2"]
        main_window._ldf = ldf
        captured = {}

        def _fake_exec(dialog):
            captured["dialog_name"] = dialog.accessibleName()
            captured["dialog_description"] = dialog.accessibleDescription()
            master_combo = dialog.findChildren(QComboBox)[0]
            slave_list = dialog.findChildren(QListWidget)[0]
            captured["master_name"] = master_combo.accessibleName()
            captured["slave_name"] = slave_list.accessibleName()
            captured["focus_widget"] = dialog.focusWidget()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        assert main_window._prompt_comm_selection() is None
        assert captured["dialog_name"] == "Communication node selection dialog"
        assert "Choose one master node" in captured["dialog_description"]
        assert captured["master_name"] == "Communication master selection"
        assert captured["slave_name"] == "Communication slave selection"
        assert isinstance(captured["focus_widget"], QComboBox)

    def test_ensure_comm_selection_without_ldf(self, main_window):
        main_window._ldf = None
        assert main_window._ensure_comm_selection() is False

    def test_ensure_comm_selection_existing_profile(self, main_window):
        main_window._ldf = _make_ldf()
        main_window._comm_selection = ("M", ["S1"])
        assert main_window._ensure_comm_selection() is True

    def test_ensure_comm_selection_cancelled(self, main_window):
        main_window._ldf = _make_ldf()
        main_window._comm_selection = None
        main_window._prompt_comm_selection = MagicMock(return_value=None)
        assert main_window._ensure_comm_selection() is False

    def test_ensure_comm_selection_success(self, main_window):
        main_window._ldf = _make_ldf()
        main_window._comm_selection = None
        main_window._prompt_comm_selection = MagicMock(return_value=("M", ["S1", "S2"]))
        main_window._comm_window.queue_selection = MagicMock()
        assert main_window._ensure_comm_selection() is True
        main_window._comm_window.queue_selection.assert_called_once_with("M", ["S1", "S2"])


# ---------------------------------------------------------------------------
# _focus_ldf_details compatibility alias
# ---------------------------------------------------------------------------


class TestFocusLdfDetails:
    def test_focus_ldf_details_no_viewer(self, main_window):
        """With placeholder as central widget, should not crash."""
        main_window._focus_ldf_details()

    def test_focus_ldf_details_with_viewer(self, main_window, monkeypatch):
        ldf = _make_ldf()
        monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
        monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
        main_window._load_ldf("/test.ldf")
        main_window._focus_ldf_details()


# ---------------------------------------------------------------------------
# _set_status_label_color
# ---------------------------------------------------------------------------


class TestSetStatusLabelColor:
    def test_valid_color(self, qapp):
        from src.gui.main_window_qt import MainWindow

        label = QLabel("test")
        MainWindow._set_status_label_color(label, "#FF0000")
        assert "color" in label.styleSheet()

    def test_invalid_color(self, qapp):
        from src.gui.main_window_qt import MainWindow

        label = QLabel("test")
        label.setStyleSheet("")
        MainWindow._set_status_label_color(label, "not_a_valid_color_at_all")
        # Should not crash; style may or may not be set depending on Qt validation


# ---------------------------------------------------------------------------
# _build_about_html
# ---------------------------------------------------------------------------


class TestBuildAboutHtml:
    def test_build_about_html_content(self):
        from src.gui.main_window_qt import MainWindow

        html = MainWindow._build_about_html()
        assert "Easy-LIN" in html
        assert "mailto:" in html
        assert "blindsystems.org" in html


# ---------------------------------------------------------------------------
# _build_issues_report_text
# ---------------------------------------------------------------------------


class TestBuildIssuesReportText:
    def test_build_issues_report_text(self):
        from src.gui.main_window_qt import MainWindow

        class FakeIssue:
            def __init__(self, severity, code, message):
                self.severity = severity
                self.code = code
                self.message = message

        issues = [
            FakeIssue("error", "E001", "Missing signal"),
            FakeIssue("warning", "W002", "Unused frame"),
        ]
        text = MainWindow._build_issues_report_text("/test.ldf", issues)
        assert "Easy-LIN LDF Validation Report" in text
        assert "Errors   : 1" in text
        assert "Warnings : 1" in text
        assert "[ERROR  ] E001: Missing signal" in text
        assert "[WARNING] W002: Unused frame" in text

    def test_build_issues_report_text_empty(self):
        from src.gui.main_window_qt import MainWindow

        text = MainWindow._build_issues_report_text("/empty.ldf", [])
        assert "Errors   : 0" in text
        assert "Warnings : 0" in text


class TestIssuesDialogSaveReport:
    def test_issues_dialog_sets_accessible_metadata(self, main_window, monkeypatch):
        class FakeIssue:
            def __init__(self, severity, code, message):
                self.severity = severity
                self.code = code
                self.message = message

        captured = {}

        def _fake_exec(dialog):
            captured["dialog_name"] = dialog.accessibleName()
            captured["dialog_description"] = dialog.accessibleDescription()
            report_view = dialog.findChildren(QPlainTextEdit)[0]
            captured["report_name"] = report_view.accessibleName()
            captured["focus_widget"] = dialog.focusWidget()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        result = main_window._show_ldf_issues_dialog(
            "/my.ldf",
            [FakeIssue("warning", "W001", "Minor warning")],
        )

        assert result is False
        assert captured["dialog_name"] == "LDF validation report dialog"
        assert "Review validation errors and warnings" in captured["dialog_description"]
        assert captured["report_name"] == "Validation report"
        assert isinstance(captured["focus_widget"], QPlainTextEdit)

    def test_save_report_oserror_shows_warning(self, main_window, monkeypatch):
        class FakeIssue:
            def __init__(self, severity, code, message):
                self.severity = severity
                self.code = code
                self.message = message

        issues = [FakeIssue("warning", "W001", "Minor warning")]

        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *args, **kwargs: ("C:/tmp/report.txt", "Text files (*.txt)")),
        )

        def _fake_exec(dialog):
            save_button = None
            for button in dialog.findChildren(QPushButton):
                if button.text().startswith("Save Report"):
                    save_button = button
                    break
            assert save_button is not None
            save_button.click()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        with (
            patch("builtins.open", side_effect=OSError("disk full")),
            patch.object(QMessageBox, "warning") as warning,
        ):
            result = main_window._show_ldf_issues_dialog("/my.ldf", issues)

        assert result is False
        warning.assert_called_once()

    def test_save_report_writes_report_text(self, main_window, monkeypatch):
        class FakeIssue:
            def __init__(self, severity, code, message):
                self.severity = severity
                self.code = code
                self.message = message

        issues = [FakeIssue("warning", "W001", "Minor warning")]

        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *args, **kwargs: ("C:/tmp/report.txt", "Text files (*.txt)")),
        )

        def _fake_exec(dialog):
            save_button = None
            for button in dialog.findChildren(QPushButton):
                if button.text().startswith("Save Report"):
                    save_button = button
                    break
            assert save_button is not None
            save_button.click()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        mopen = mock_open()
        with patch("builtins.open", mopen):
            result = main_window._show_ldf_issues_dialog("/my.ldf", issues)

        assert result is False
        mopen.assert_called_once_with("C:/tmp/report.txt", "w", encoding="utf-8")


# ---------------------------------------------------------------------------
# Region cycling and focus
# ---------------------------------------------------------------------------


class TestRegionCycling:
    def test_focus_next_region(self, main_window):
        main_window._region_cycle_index = 0
        main_window._focus_next_region()
        assert main_window._region_cycle_index == 1

    def test_focus_previous_region(self, main_window):
        main_window._region_cycle_index = 1
        main_window._focus_previous_region()
        assert main_window._region_cycle_index == 0

    def test_focus_ldf_tree_no_viewer(self, main_window):
        main_window._focus_ldf_tree()  # Should not crash

    def test_focus_communication(self, main_window):
        main_window._ensure_comm_selection = MagicMock(return_value=True)
        main_window._focus_communication()
        assert main_window._region_cycle_index == 1


# ---------------------------------------------------------------------------
# Status bar event announcements
# ---------------------------------------------------------------------------


class TestAnnounceEvent:
    def test_announce_event_normal(self, main_window):
        main_window._announce_event("Test message")
        assert "Test message" in main_window._sb_event.text()

    def test_announce_event_error(self, main_window):
        main_window._announce_event("Connection error occurred")
        assert "error" in main_window._sb_event.text().lower()

    def test_announce_event_warning(self, main_window):
        main_window._announce_event("Warning: low battery")

    def test_set_comm_status(self, main_window):
        main_window._set_comm_status("Connected")
        assert "Connected" in main_window._sb_comm.text()

    def test_set_comm_status_unknown(self, main_window):
        main_window._set_comm_status("CustomState")
        assert "CustomState" in main_window._sb_comm.text()

    def test_set_ldf_status(self, main_window):
        ldf = _make_ldf()
        main_window._set_ldf_status(ldf)
        assert "19.2" in main_window._sb_ldf.text()

    def test_set_ldf_issues_status_no_issues(self, main_window):
        main_window._set_ldf_issues_status(0, 0)
        assert "0" in main_window._sb_issues.text()

    def test_set_ldf_issues_status_warnings(self, main_window):
        main_window._set_ldf_issues_status(3, 0)
        assert "3" in main_window._sb_issues.text()

    def test_set_ldf_issues_status_errors(self, main_window):
        main_window._set_ldf_issues_status(1, 2)
        assert "2" in main_window._sb_issues.text()

    # ---------------------------------------------------------------------------
    # _on_node_selection_changed and node lock wiring
    # ---------------------------------------------------------------------------

    class TestNodeSelectionChangedWiring:
        def test_on_node_selection_changed_updates_comm_selection(self, main_window):
            main_window._comm_window.queue_selection = MagicMock()
            main_window._on_node_selection_changed("M", ["S1", "S2"])
            assert main_window._comm_selection == ("M", ["S1", "S2"])
            main_window._comm_window.queue_selection.assert_called_once_with("M", ["S1", "S2"])

        def test_set_comm_status_connected_locks_viewer(self, main_window, monkeypatch):
            from src.gui.ldf_viewer import LDFViewer

            mock_viewer = MagicMock(spec=LDFViewer)
            monkeypatch.setattr(main_window, "centralWidget", lambda: mock_viewer)
            main_window._set_comm_status("Connected")
            mock_viewer.lock_node_selection.assert_called_once_with(True)

        def test_set_comm_status_disconnected_unlocks_viewer(self, main_window, monkeypatch):
            from src.gui.ldf_viewer import LDFViewer

            mock_viewer = MagicMock(spec=LDFViewer)
            monkeypatch.setattr(main_window, "centralWidget", lambda: mock_viewer)
            main_window._set_comm_status("Disconnected")
            mock_viewer.lock_node_selection.assert_called_once_with(False)

        def test_set_comm_status_non_viewer_widget_does_not_crash(self, main_window, monkeypatch):
            monkeypatch.setattr(main_window, "centralWidget", lambda: QLabel("not a viewer"))
            main_window._set_comm_status("Connected")  # must not raise

        def test_load_ldf_initializes_comm_selection_from_tree(self, main_window, monkeypatch):
            ldf = _make_ldf()
            monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
            monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
            main_window._comm_selection = None
            main_window._load_ldf("/good_nodes.ldf")
            # Tree checkboxes should auto-select "M" (master) and "S1" (slave)
            assert main_window._comm_selection == ("M", ["S1"])

        def test_load_ldf_queues_comm_window_sync(self, main_window, monkeypatch):
            ldf = _make_ldf()
            monkeypatch.setattr("src.gui.main_window_qt.parse_ldf", MagicMock(return_value=ldf))
            monkeypatch.setattr("src.gui.main_window_qt.validate_ldf", MagicMock(return_value=[]))
            main_window._comm_window.queue_ldf = MagicMock()
            main_window._comm_window.queue_selection = MagicMock()

            main_window._load_ldf("/good_nodes.ldf")

            main_window._comm_window.queue_ldf.assert_called_once_with(ldf)
            main_window._comm_window.queue_selection.assert_called_once_with("M", ["S1"])
