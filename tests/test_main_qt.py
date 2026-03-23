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

import pytest


from src.main_qt import run_qt_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeApp:
    """Minimal stand-in for QApplication."""

    def __init__(self, argv):
        self.argv = argv
        self._name = None
        self._org = None
        self._style = None
        self._exec_return = 0

    def setApplicationName(self, name):
        self._name = name

    def setOrganizationName(self, org):
        self._org = org

    def setStyle(self, style):
        self._style = style

    def exec(self):
        return self._exec_return


class _FakeWindow:
    """Minimal stand-in for MainWindow."""

    def __init__(self):
        self.shown = False
        self.loaded_path = None

    def show(self):
        self.shown = True

    def load_ldf_file(self, path):
        self.loaded_path = path


class _FakeLock:
    """Stand-in for QLockFile."""

    def __init__(self, acquired: bool = True):
        self._acquired = acquired

    def tryLock(self, _timeout: int) -> bool:
        return self._acquired


def _make_seams(argv=None, *, acquired=True, exec_return=0):
    """Return (fake_app, fake_window, lock, kwargs dict) ready for run_qt_app."""
    _argv = argv or ["test"]
    fake_app = _FakeApp(_argv)
    fake_app._exec_return = exec_return
    fake_window = _FakeWindow()
    lock = _FakeLock(acquired=acquired)
    kwargs = dict(
        _app_factory=lambda a: fake_app,
        _lock_factory=lambda _p: lock,
        _window_factory=lambda: fake_window,
    )
    return fake_app, fake_window, lock, kwargs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_qt_app_defaults_to_sys_argv(monkeypatch):
    """When argv is None, sys.argv should be used."""
    monkeypatch.setattr(sys, "argv", ["easy-lin"])
    fake_app, fake_window, _lock, kwargs = _make_seams(["easy-lin"])

    with pytest.raises(SystemExit) as exc_info:
        run_qt_app(None, **kwargs)
    assert exc_info.value.code == 0


def test_run_qt_app_with_explicit_argv():
    """When argv is provided, it should be passed to QApplication."""
    received = []
    fake_app = _FakeApp(["test"])
    fake_window = _FakeWindow()
    lock = _FakeLock()

    def factory(a):
        received.append(a)
        return fake_app

    with pytest.raises(SystemExit) as exc_info:
        run_qt_app(
            ["test"],
            _app_factory=factory,
            _lock_factory=lambda _: lock,
            _window_factory=lambda: fake_window,
        )
    assert exc_info.value.code == 0
    assert received == [["test"]]


def test_run_qt_app_sets_app_properties():
    """App name, org, and style should be set."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"])

    with pytest.raises(SystemExit):
        run_qt_app(["test"], **kwargs)

    assert fake_app._name == "Easy-LIN"
    assert fake_app._org == "Easy-LIN"
    assert fake_app._style == "Fusion"


def test_run_qt_app_creates_and_shows_window():
    """MainWindow should be shown."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"])

    with pytest.raises(SystemExit):
        run_qt_app(["test"], **kwargs)

    assert fake_window.shown is True


def test_run_qt_app_loads_ldf_from_argv():
    """When argv has a non-flag argument, load_ldf_file should be called."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test", "sample.ldf"])

    with pytest.raises(SystemExit):
        run_qt_app(["test", "sample.ldf"], **kwargs)

    assert fake_window.loaded_path == "sample.ldf"


def test_run_qt_app_skips_flag_only_argv():
    """When all args after argv[0] are flags, no LDF should be loaded."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test", "--verbose", "--debug"])

    with pytest.raises(SystemExit):
        run_qt_app(["test", "--verbose", "--debug"], **kwargs)

    assert fake_window.loaded_path is None


def test_run_qt_app_loads_first_non_flag_arg():
    """The first non-flag argument should be used for LDF loading."""
    fake_app, fake_window, _lock, kwargs = _make_seams(
        ["test", "--verbose", "first.ldf", "second.ldf"]
    )

    with pytest.raises(SystemExit):
        run_qt_app(["test", "--verbose", "first.ldf", "second.ldf"], **kwargs)

    assert fake_window.loaded_path == "first.ldf"


def test_run_qt_app_no_extra_args():
    """When argv has only the program name, no LDF is loaded."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"])

    with pytest.raises(SystemExit):
        run_qt_app(["test"], **kwargs)

    assert fake_window.loaded_path is None


def test_run_qt_app_exec_return_code():
    """SystemExit code should match the value from app.exec()."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"], exec_return=42)

    with pytest.raises(SystemExit) as exc_info:
        run_qt_app(["test"], **kwargs)

    assert exc_info.value.code == 42


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------

def test_run_qt_app_single_instance_already_running():
    """When QLockFile cannot be acquired, a warning is shown and app returns early."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"], acquired=False)
    warnings = []
    kwargs["_warn"] = lambda *a, **kw: warnings.append(a)

    assert run_qt_app(["test"], **kwargs) is None
    assert len(warnings) == 1
    assert fake_window.shown is False


def test_run_qt_app_single_instance_acquired():
    """When the lock is acquired, the application starts normally."""
    fake_app, fake_window, _lock, kwargs = _make_seams(["test"], acquired=True)

    with pytest.raises(SystemExit):
        run_qt_app(["test"], **kwargs)

    assert fake_window.shown is True
