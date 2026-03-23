"""
Atomic features covered:
- Block loading of LDF files that contain consistency errors
- Ask for confirmation before loading LDF files that contain only warnings
- Always allow loading when a file has no issues (no dialog shown)
- Offer a Save Report button so the user can persist the validation report
- Build a plain-text validation report with file path, date, counts and issue list
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication, QDialog

import src.gui.main_window_qt as main_window_qt
from src.gui.main_window_qt import MainWindow
from src.ldf_consistency import ConsistencyIssue
from src.ldf_parser import parse_ldf_string


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CLEAN_LDF = """
    LIN_description_file ;
    LIN_protocol_version = "2.1" ;
    LIN_language_version = "2.1" ;
    LIN_speed = 19.2 kbps ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S1 ; }
    Signals { S1: 8, 0, M, S1 ; }
    Frames { F1 : 0x10, M, 1 { S1, 0 ; } }
    Schedule_tables { Main { F1 delay 10 ms ; } }
"""


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Provide a reusable QApplication for Qt widget tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _error_issue() -> ConsistencyIssue:
    """Return a representative blocking consistency error issue."""
    return ConsistencyIssue("error", "SIGNAL_INIT_RANGE", "Signal S1 initial value out of range")


def _warning_issue() -> ConsistencyIssue:
    """Return a representative non-blocking consistency warning issue."""
    return ConsistencyIssue("warning", "SCHEDULE_DELAY_MULTIPLE", "Delay not multiple of 1 ms")


# ---------------------------------------------------------------------------
# _build_issues_report_text  (pure static method — no Qt needed)
# ---------------------------------------------------------------------------


def test_report_text_contains_file_path_and_counts() -> None:
    """Ensure the saved report header includes the file path and issue counts."""
    issues = [_error_issue(), _warning_issue()]
    text = MainWindow._build_issues_report_text("/path/to/my.ldf", issues)

    assert "/path/to/my.ldf" in text
    assert "Errors   : 1" in text
    assert "Warnings : 1" in text


def test_report_text_lists_every_issue_code_and_message() -> None:
    """Every issue code and its human-readable message must appear in the report."""
    issues = [_error_issue(), _warning_issue()]
    text = MainWindow._build_issues_report_text("/some.ldf", issues)

    assert "SIGNAL_INIT_RANGE" in text
    assert "Signal S1 initial value out of range" in text
    assert "SCHEDULE_DELAY_MULTIPLE" in text
    assert "[ERROR  ]" in text
    assert "[WARNING]" in text


def test_report_text_includes_date_stamp() -> None:
    """The report must include a Date line for traceability."""
    text = MainWindow._build_issues_report_text("/f.ldf", [_error_issue()])
    assert "Date     :" in text


# ---------------------------------------------------------------------------
# _load_ldf gate — dialog mocked via monkeypatch on _show_ldf_issues_dialog
# ---------------------------------------------------------------------------


def test_load_ldf_clean_file_loads_without_showing_dialog(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """A file with no consistency issues must load silently (no dialog shown)."""
    ldf = parse_ldf_string(CLEAN_LDF)
    monkeypatch.setattr(main_window_qt, "parse_ldf", lambda _: ldf)
    monkeypatch.setattr(main_window_qt, "validate_ldf", lambda _: [])

    dialog_calls: list = []
    monkeypatch.setattr(
        MainWindow,
        "_show_ldf_issues_dialog",
        lambda *_args: dialog_calls.append(True) or True,
    )

    window = MainWindow()
    window._load_ldf("clean.ldf")

    assert not dialog_calls, "No dialog must appear when the file is clean"
    assert window._ldf is ldf


def test_load_ldf_error_file_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """A file with errors must not be loaded; the user sees the block dialog."""
    ldf = parse_ldf_string(CLEAN_LDF)
    monkeypatch.setattr(main_window_qt, "parse_ldf", lambda _: ldf)
    monkeypatch.setattr(main_window_qt, "validate_ldf", lambda _: [_error_issue()])

    dialog_called: list = []

    def _mock_dialog(self, path, issues):  # noqa: ANN001
        """Simulate a user-facing issues dialog that blocks loading."""
        dialog_called.append(True)
        return False  # error file is always blocked

    monkeypatch.setattr(MainWindow, "_show_ldf_issues_dialog", _mock_dialog)

    window = MainWindow()
    window._load_ldf("error.ldf")

    assert dialog_called, "Block dialog must be shown for an error file"
    assert window._ldf is None, "LDF must NOT be loaded when errors are present"


def test_load_ldf_warning_file_loads_when_user_accepts(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """If the user clicks 'Open Anyway' on the warning dialog, the file is loaded."""
    ldf = parse_ldf_string(CLEAN_LDF)
    monkeypatch.setattr(main_window_qt, "parse_ldf", lambda _: ldf)
    monkeypatch.setattr(main_window_qt, "validate_ldf", lambda _: [_warning_issue()])
    monkeypatch.setattr(MainWindow, "_show_ldf_issues_dialog", lambda *_: True)

    window = MainWindow()
    window._load_ldf("warning.ldf")

    assert window._ldf is ldf, "LDF must be loaded when user accepts the warning"


def test_load_ldf_warning_file_not_loaded_when_user_cancels(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """If the user cancels the warning dialog, the file must NOT be loaded."""
    ldf = parse_ldf_string(CLEAN_LDF)
    monkeypatch.setattr(main_window_qt, "parse_ldf", lambda _: ldf)
    monkeypatch.setattr(main_window_qt, "validate_ldf", lambda _: [_warning_issue()])
    monkeypatch.setattr(MainWindow, "_show_ldf_issues_dialog", lambda *_: False)

    window = MainWindow()
    window._load_ldf("warning.ldf")

    assert window._ldf is None, "LDF must NOT be loaded when user cancels"


# ---------------------------------------------------------------------------
# _show_ldf_issues_dialog return-value semantics — exec_ mocked
# ---------------------------------------------------------------------------


def test_issues_dialog_always_returns_false_for_error_files(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """An error file dialog must return False even when exec_ returns Accepted."""
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

    window = MainWindow()
    result = window._show_ldf_issues_dialog("/my.ldf", [_error_issue()])

    assert result is False


def test_issues_dialog_returns_true_when_warnings_accepted(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """Warning dialog returns True when user clicks 'Open Anyway' (Accepted)."""
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

    window = MainWindow()
    result = window._show_ldf_issues_dialog("/my.ldf", [_warning_issue()])

    assert result is True


def test_issues_dialog_returns_false_when_warnings_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """Warning dialog returns False when user clicks Cancel (Rejected)."""
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)

    window = MainWindow()
    result = window._show_ldf_issues_dialog("/my.ldf", [_warning_issue()])

    assert result is False


def test_issues_dialog_is_shown_with_both_errors_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    """A file with mixed errors+warnings is still blocked (errors take priority)."""
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

    issues = [_error_issue(), _warning_issue()]
    window = MainWindow()
    result = window._show_ldf_issues_dialog("/my.ldf", issues)

    assert result is False, "Mixed errors+warnings must be treated as blocked"
