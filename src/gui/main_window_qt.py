"""Easy-LIN main window for the preserved PyQt frontend.

Provides the top-level application window hosting the LDF viewer, hardware
communication dock, menus, toolbar, and persistent window state.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

import logging
import os
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QDockWidget,
    QAction,
    QFileDialog,
    QMessageBox,
    QLabel,
    QToolBar,
)
from PyQt5.QtCore import Qt, QSettings, QSize
from PyQt5.QtGui import QFont, QKeySequence

from src.ldf_parser import parse_ldf, LDFFile, LDFParseError
from src.gui.ldf_viewer import LDFViewer
from src.gui.communication_panel import CommunicationPanel

log = logging.getLogger(__name__)

APP_NAME = "Easy-LIN"
APP_ORG = "Easy-LIN"
APP_VERSION = "1.0.0"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        """Initialize the main PyQt window and restore persisted state."""
        super().__init__()
        self._ldf: Optional[LDFFile] = None
        self._ldf_path: Optional[str] = None
        self._settings = QSettings(APP_ORG, APP_NAME)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._restore_geometry()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the placeholder central widget, dock, and status bar."""
        # Central placeholder (shown before any LDF is loaded)
        self._placeholder = QWidget()
        placeholder_lbl = QLabel(
            "<h2>Welcome to Easy-LIN</h2>"
            "<p>Open an LDF file via <b>File ÔåÆ Open LDFÔÇª</b> to get started.</p>"
            "<p>Easy-LIN acts as a LIN master and allows you to:<br>"
            "&nbsp;ÔÇó Inspect every section of an LDF file<br>"
            "&nbsp;ÔÇó Monitor and send LIN frames in real time<br>"
            "&nbsp;ÔÇó Execute schedule tables automatically</p>"
        )
        placeholder_lbl.setAlignment(Qt.AlignCenter)
        placeholder_lbl.setTextFormat(Qt.RichText)
        font = QFont()
        font.setPointSize(11)
        placeholder_lbl.setFont(font)
        from PyQt5.QtWidgets import QVBoxLayout

        pl = QVBoxLayout(self._placeholder)
        pl.addWidget(placeholder_lbl)
        self.setCentralWidget(self._placeholder)

        # Communication dock (right side)
        self._comm_panel = CommunicationPanel()
        self._comm_panel.status_message.connect(self.statusBar().showMessage)
        dock = QDockWidget("Communication", self)
        dock.setObjectName("CommunicationDock")
        dock.setWidget(self._comm_panel)
        dock.setMinimumWidth(420)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._comm_dock = dock

        self.statusBar().showMessage("Ready")

    def _build_menu(self) -> None:
        """Create the main menu bar and its actions."""
        mb = self.menuBar()

        # ---- File -------------------------------------------------------
        file_menu = mb.addMenu("&File")

        self._open_action = QAction("&Open LDFÔÇª", self)
        self._open_action.setShortcut(QKeySequence.Open)
        self._open_action.setStatusTip("Open a LIN Description File (.ldf)")
        self._open_action.triggered.connect(self._open_ldf)
        file_menu.addAction(self._open_action)

        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu("Recent Files")
        self._update_recent_menu()

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ---- View -------------------------------------------------------
        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._comm_dock.toggleViewAction())

        # ---- Help -------------------------------------------------------
        help_menu = mb.addMenu("&Help")

        about_action = QAction("&About Easy-LIN", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        vector_action = QAction("Vector XL Driver LibraryÔÇª", self)
        vector_action.triggered.connect(self._open_vector_docs)
        help_menu.addAction(vector_action)

    def _build_toolbar(self) -> None:
        """Create the fixed main toolbar."""
        tb: QToolBar = self.addToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))
        tb.addAction(self._open_action)

    # ------------------------------------------------------------------
    # LDF loading
    # ------------------------------------------------------------------

    def load_ldf_file(self, path: str) -> None:
        """Public entry point for loading an LDF file (e.g. from CLI)."""
        self._load_ldf(path)

    def _open_ldf(self) -> None:
        """Prompt for an LDF file and load it into the main viewer."""
        last_dir = self._settings.value("last_open_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open LDF File",
            last_dir,
            "LIN Description Files (*.ldf);;All Files (*)",
        )
        if not path:
            return
        self._load_ldf(path)

    def _load_ldf(self, path: str) -> None:
        """Parse and display the requested LDF file."""
        try:
            ldf = parse_ldf(path)
        except FileNotFoundError:
            QMessageBox.critical(self, APP_NAME, f"File not found:\n{path}")
            return
        except LDFParseError as exc:
            QMessageBox.critical(self, APP_NAME, f"LDF parse error:\n{exc}")
            return
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Unexpected error loading LDF:\n{exc}")
            log.exception("Unexpected error loading LDF")
            return

        self._ldf = ldf
        self._ldf_path = path

        # Update window title
        self.setWindowTitle(f"{APP_NAME}  ÔÇö  {os.path.basename(path)}")

        # Replace central widget with LDF viewer
        if isinstance(self.centralWidget(), LDFViewer):
            self.centralWidget().refresh(ldf)
        else:
            viewer = LDFViewer(ldf)
            self.setCentralWidget(viewer)

        # Update communication panel
        self._comm_panel.load_ldf(ldf)

        # Save to recent files
        self._add_recent(path)
        self._settings.setValue("last_open_dir", os.path.dirname(path))

        slaves = ldf.nodes.slaves if ldf.nodes else []
        self.statusBar().showMessage(
            f"Loaded: {os.path.basename(path)}  |  "
            f"LIN {ldf.protocol_version}  |  {ldf.speed} kbps  |  "
            f"{len(ldf.frames)} frames  |  "
            f"{len(slaves)} slave(s)"
        )

    # ------------------------------------------------------------------
    # Recent files
    # ------------------------------------------------------------------

    def _add_recent(self, path: str) -> None:
        """Insert one path into the recent-files history."""
        recent = self._settings.value("recent_files", []) or []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]
        self._settings.setValue("recent_files", recent)
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        """Rebuild the recent-files submenu from persisted settings."""
        self._recent_menu.clear()
        recent = self._settings.value("recent_files", []) or []
        for path in recent:
            action = QAction(os.path.basename(path), self)
            action.setData(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _checked, p=path: self._load_ldf(p))
            self._recent_menu.addAction(action)
        if not recent:
            empty = QAction("(empty)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        """Display the About dialog for the preserved PyQt frontend."""
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>Easy-LIN {APP_VERSION}</h3>"
            "<p>An open-source LIN master GUI for Vector VN16xx hardware.</p>"
            "<ul>"
            "<li>Parse and display LDF files (LIN 1.3 / 2.0 / 2.1 / 2.2)</li>"
            "<li>Connect via Vector XL Driver Library</li>"
            "<li>Send / receive LIN frames in real time</li>"
            "<li>Execute schedule tables automatically</li>"
            "</ul>"
            "<p>Uses the <b>Vector XL Driver Library</b> (vxlapi.dll) for hardware "
            "communication.  The driver must be installed separately from "
            "<a href='https://www.vector.com/'>vector.com</a>.</p>",
        )

    @staticmethod
    def _open_vector_docs() -> None:
        """Open the public Vector XL Driver Library page in a browser."""
        import webbrowser

        webbrowser.open(
            "https://www.vector.com/int/en/products/products-a-z/software/xl-driver-library/"
        )

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        """Restore window geometry and dock layout from settings."""
        geom = self._settings.value("geometry")
        state = self._settings.value("windowState")
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        """Persist geometry and dock state before closing the window."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        super().closeEvent(event)
