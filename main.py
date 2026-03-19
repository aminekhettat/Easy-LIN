"""
Easy-LIN — Entry point.

Launch with::

    python main.py [path/to/file.ldf]
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)


def main() -> None:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from src.gui.main_window import MainWindow

    # Enable high-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Easy-LIN")
    app.setOrganizationName("Easy-LIN")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    # If an LDF path was passed on the command line, open it immediately
    if len(sys.argv) > 1:
        window.load_ldf_file(sys.argv[1])

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
