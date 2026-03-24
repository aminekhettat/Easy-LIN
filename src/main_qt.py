"""Primary PySide6 launcher for Easy-LIN.

This module starts the default Qt-based interface used by ``main.py``.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.8.3
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import sys
import os
import tempfile


def run_qt_app(  # noqa: PLR0913
    argv: list[str] | None = None,
    *,
    _app_factory=None,
    _lock_factory=None,
    _window_factory=None,
    _warn=None,
) -> None:
    """Start the PySide6 application and exit with its return code.

    The ``_app_factory``, ``_lock_factory``, ``_window_factory``, and
    ``_warn`` keyword arguments are test seams; production code must never
    pass them.
    """
    if argv is None:
        argv = sys.argv

    from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: PLC0415
    from PySide6.QtCore import QLockFile  # noqa: PLC0415
    from src.gui.main_window_qt import MainWindow  # noqa: PLC0415

    if _app_factory is None:
        _app_factory = QApplication  # pragma: no cover
    if _lock_factory is None:
        _lock_factory = QLockFile  # pragma: no cover
    if _window_factory is None:
        _window_factory = MainWindow  # pragma: no cover
    if _warn is None:
        _warn = QMessageBox.warning

    app = _app_factory(argv)
    app.setApplicationName("Easy-LIN")
    app.setOrganizationName("Easy-LIN")
    app.setStyle("Fusion")

    _lock_path = os.path.join(tempfile.gettempdir(), "easy_lin_single_instance.lock")
    _instance_lock = _lock_factory(_lock_path)
    if not _instance_lock.tryLock(100):
        _warn(
            None,
            "Easy-LIN \u2014 Already Running",
            "An instance of Easy-LIN is already running.\n"
            "Please bring the existing window to the front.",
        )
        return

    window = _window_factory()
    window.show()

    if len(argv) > 1:
        ldf_arg = next((arg for arg in argv[1:] if not arg.startswith("--")), None)
        if ldf_arg:
            window.load_ldf_file(ldf_arg)

    raise SystemExit(app.exec())
