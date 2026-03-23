"""Primary PySide6 launcher for Easy-LIN.

This module starts the default Qt-based interface used by ``main.py``.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import sys
import os
import tempfile


def run_qt_app(argv: list[str] | None = None) -> None:
    """Start the PySide6 application and exit with its return code."""
    if argv is None:
        argv = sys.argv

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QMessageBox

    from src.gui.main_window_qt import MainWindow

    app = QApplication(argv)
    app.setApplicationName("Easy-LIN")
    app.setOrganizationName("Easy-LIN")
    app.setStyle("Fusion")

    _lock_path = os.path.join(tempfile.gettempdir(), "easy_lin_single_instance.lock")
    _instance_lock = QLockFile(_lock_path)
    if not _instance_lock.tryLock(100):
        QMessageBox.warning(
            None,
            "Easy-LIN \u2014 Already Running",
            "An instance of Easy-LIN is already running.\n"
            "Please bring the existing window to the front.",
        )
        return

    window = MainWindow()
    window.show()

    if len(argv) > 1:
        ldf_arg = next((arg for arg in argv[1:] if not arg.startswith("--")), None)
        if ldf_arg:
            window.load_ldf_file(ldf_arg)

    raise SystemExit(app.exec())
