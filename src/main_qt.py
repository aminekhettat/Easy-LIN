"""PyQt launcher preserved from the alternate integration branch."""

import sys


def run_qt_app(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    from src.gui.main_window_qt import MainWindow

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(argv)
    app.setApplicationName("Easy-LIN")
    app.setOrganizationName("Easy-LIN")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    if len(argv) > 1:
        ldf_arg = next((arg for arg in argv[1:] if not arg.startswith("--")), None)
        if ldf_arg:
            window.load_ldf_file(ldf_arg)

    raise SystemExit(app.exec_())
