"""Tests for src/main_qt.py -- run_qt_app launcher function.

Covers:
- Default argv falls back to sys.argv
- QApplication creation with correct name, org, style
- MainWindow creation and show
- LDF loading from argv when len > 1 and arg does not start with --
- Skipping LDF loading when only -- args present
- SystemExit raised with app.exec() return code
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _offscreen(monkeypatch):
    """Force offscreen Qt and stable lock behavior for launcher tests."""
    import os

    from PySide6 import QtCore, QtWidgets

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    class _AlwaysAcquiredLock:
        """Default lock stub: always acquire to avoid cross-test lock leakage."""

        def __init__(self, _path: str):
            self._locked = True

        def tryLock(self, _timeout: int) -> bool:
            return self._locked

    monkeypatch.setattr(QtCore, "QLockFile", _AlwaysAcquiredLock)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *args, **kwargs: None)


class _FakeApp:
    """Minimal stand-in for QApplication."""

    def __init__(self, argv):
        self.argv = argv
        self._name = None
        self._org = None
        self._style = None

    def setApplicationName(self, name):
        self._name = name

    def setOrganizationName(self, org):
        self._org = org

    def setStyle(self, style):
        self._style = style

    def exec(self):
        return 0


class _FakeWindow:
    """Minimal stand-in for MainWindow."""

    def __init__(self):
        self.shown = False
        self.loaded_path = None

    def show(self):
        self.shown = True

    def load_ldf_file(self, path):
        self.loaded_path = path


def _make_patches(fake_app_cls=None, fake_window_cls=None):
    """Return patches for QApplication and MainWindow."""
    if fake_app_cls is None:
        fake_app_cls = _FakeApp
    if fake_window_cls is None:
        fake_window_cls = _FakeWindow
    return (
        patch("src.main_qt.QApplication", fake_app_cls, create=True),
        patch("src.main_qt.MainWindow", fake_window_cls, create=True),
    )


def test_run_qt_app_defaults_to_sys_argv(monkeypatch):
    """When argv is None, sys.argv should be used."""
    monkeypatch.setattr(sys, "argv", ["easy-lin"])
    fake_app = _FakeApp(["easy-lin"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit) as exc_info:
            run_qt_app(None)
        assert exc_info.value.code == 0


def test_run_qt_app_with_explicit_argv():
    """When argv is provided, it should be passed to QApplication."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app) as mock_qapp,
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit) as exc_info:
            run_qt_app(["test"])
        assert exc_info.value.code == 0
        mock_qapp.assert_called_once_with(["test"])


def test_run_qt_app_sets_app_properties():
    """App name, org, and style should be set."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test"])
        assert fake_app._name == "Easy-LIN"
        assert fake_app._org == "Easy-LIN"
        assert fake_app._style == "Fusion"


def test_run_qt_app_creates_and_shows_window():
    """MainWindow should be created and shown."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test"])
        assert fake_window.shown is True


def test_run_qt_app_loads_ldf_from_argv():
    """When argv has a non-flag argument, load_ldf_file should be called."""
    fake_app = _FakeApp(["test", "sample.ldf"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test", "sample.ldf"])
        assert fake_window.loaded_path == "sample.ldf"


def test_run_qt_app_skips_flag_only_argv():
    """When all args after argv[0] are flags, no LDF should be loaded."""
    fake_app = _FakeApp(["test", "--verbose", "--debug"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test", "--verbose", "--debug"])
        assert fake_window.loaded_path is None


def test_run_qt_app_loads_first_non_flag_arg():
    """The first non-flag argument should be used for LDF loading."""
    fake_app = _FakeApp(["test", "--verbose", "first.ldf", "second.ldf"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test", "--verbose", "first.ldf", "second.ldf"])
        assert fake_window.loaded_path == "first.ldf"


def test_run_qt_app_no_extra_args():
    """When argv has only the program name, no LDF is loaded."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test"])
        assert fake_window.loaded_path is None


def test_run_qt_app_exec_return_code():
    """SystemExit code should match the value from app.exec()."""
    fake_app = _FakeApp(["test"])
    fake_app.exec = lambda: 42
    fake_window = _FakeWindow()

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit) as exc_info:
            run_qt_app(["test"])
        assert exc_info.value.code == 42


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

class _FakeLockFile:
    """Stand-in for QLockFile that controls whether the lock is available."""

    def __init__(self, available: bool = True):
        self._available = available

    def __call__(self, path: str):
        return self

    def tryLock(self, timeout: int) -> bool:
        return self._available


def test_run_qt_app_single_instance_already_running():
    """When QLockFile cannot be acquired, a warning is shown and app returns early."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()
    lock = _FakeLockFile(available=False)

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("PySide6.QtCore.QLockFile", lock),
        patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn,
    ):
        from src.main_qt import run_qt_app
        assert run_qt_app(["test"]) is None
        mock_warn.assert_called_once()
        assert fake_window.shown is False


def test_run_qt_app_single_instance_acquired():
    """When the lock is acquired, the application starts normally."""
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()
    lock = _FakeLockFile(available=True)

    with (
        patch("PySide6.QtWidgets.QApplication", return_value=fake_app),
        patch("PySide6.QtCore.QLockFile", lock),
        patch("src.gui.main_window_qt.MainWindow", return_value=fake_window),
    ):
        from src.main_qt import run_qt_app
        with pytest.raises(SystemExit):
            run_qt_app(["test"])
        assert fake_window.shown is True
