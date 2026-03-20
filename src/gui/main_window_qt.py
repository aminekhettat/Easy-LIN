"""Easy-LIN main window for the preserved PyQt frontend.

Provides the top-level application window hosting the LDF viewer, hardware
communication dock, menus, toolbar, and persistent window state.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QDockWidget,
    QAction,
    QShortcut,
    QFileDialog,
    QMessageBox,
    QLabel,
    QToolBar,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QTextBrowser,
    QPlainTextEdit,
)
from PyQt5.QtCore import Qt, QSettings, QSize, QTimer
from PyQt5.QtGui import QFont, QKeySequence, QColor, QPixmap

from src.ldf_parser import parse_ldf, LDFFile, LDFParseError
from src.ldf_consistency import validate_ldf
from src.gui.ldf_viewer import LDFViewer
from src.gui.communication_panel import CommunicationPanel

log = logging.getLogger(__name__)

APP_NAME = "Easy-LIN"
APP_ORG = "Easy-LIN"
APP_VERSION = "0.5.2"
APP_AUTHOR = "Amine Khettat"
APP_COMPANY = "BLIND SYSTEMS"
APP_CONTACT_EMAIL = "contact@blindsystems.org"
APP_WEBSITE = "https://www.blindsystems.org"
APP_COPYRIGHT = "Copyright (c) 2026 Amine Khettat"
APP_COMPANY_LOGO_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "blind_systems_logo.png")
)

STATUS_COLOR_OK = "#1F7A1F"
STATUS_COLOR_WARN = "#9A6700"
STATUS_COLOR_ERROR = "#B00020"
STATUS_COLOR_INFO = "#1A4A8A"
STATUS_COLOR_NEUTRAL = "#4A4A4A"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        """Initialize the main PyQt window and restore persisted state."""
        super().__init__()
        self._ldf: Optional[LDFFile] = None
        self._ldf_path: Optional[str] = None
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._region_cycle_index = 0

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_shortcuts()
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
            "<p>Open an LDF file via <b>File > Open LDF...</b> to get started.</p>"
            "<p>Easy-LIN acts as a LIN master and allows you to:<br>"
            "- Inspect every section of an LDF file<br>"
            "- Monitor and send LIN frames in real time<br>"
            "- Execute schedule tables automatically</p>"
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
        self._comm_panel.setObjectName("communicationPanel")
        self._comm_panel.status_message.connect(self._on_comm_status_message)
        self._comm_panel.communication_state_changed.connect(self._set_comm_status)
        dock = QDockWidget("Communication", self)
        dock.setObjectName("CommunicationDock")
        dock.setWidget(self._comm_panel)
        dock.setMinimumWidth(420)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._comm_dock = dock

        self._build_status_tracker()
        self._announce_event("Ready", timeout_ms=2000)

    def _build_status_tracker(self) -> None:
        """Create persistent status fields in the bottom status bar."""
        sb = self.statusBar()
        self._sb_ldf = QLabel("LDF: not loaded")
        self._sb_issues = QLabel("LDF issues: Warnings: 0 | Errors: 0")
        self._sb_comm = QLabel("Comm: Disconnected")
        self._sb_event = QLabel("Last event: Ready")

        self._sb_ldf.setAccessibleName("LDF summary status")
        self._sb_issues.setAccessibleName("LDF issues status")
        self._sb_comm.setAccessibleName("Communication status")
        self._sb_event.setAccessibleName("Latest event status")

        self._set_status_label_color(self._sb_ldf, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_issues, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_comm, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_event, STATUS_COLOR_INFO)

        sb.addPermanentWidget(self._sb_ldf)
        sb.addPermanentWidget(self._sb_issues)
        sb.addPermanentWidget(self._sb_comm)
        sb.addPermanentWidget(self._sb_event, 1)

    def _announce_event(self, message: str, timeout_ms: int = 5000) -> None:
        """Show a short-lived status bar message and persist it as latest event."""
        self.statusBar().showMessage(message, timeout_ms)
        self._sb_event.setText(f"Last event: {message}")
        event_color = STATUS_COLOR_INFO
        lowered = message.lower()
        if "error" in lowered or "failed" in lowered:
            event_color = STATUS_COLOR_ERROR
        elif "warning" in lowered:
            event_color = STATUS_COLOR_WARN
        self._set_status_label_color(self._sb_event, event_color)

    @staticmethod
    def _set_status_label_color(label: QLabel, color_hex: str) -> None:
        """Apply a readable foreground color to one status field."""
        color = QColor(color_hex)
        if not color.isValid():
            return
        label.setStyleSheet(f"color: {color_hex};")

    def _on_comm_status_message(self, message: str) -> None:
        """Receive status messages from the communication panel."""
        self._announce_event(message)

    def _set_comm_status(self, state: str) -> None:
        """Update the persistent communication state field."""
        self._sb_comm.setText(f"Comm: {state}")
        state_map = {
            "Connected": STATUS_COLOR_OK,
            "Disconnected": STATUS_COLOR_NEUTRAL,
            "No hardware": STATUS_COLOR_WARN,
            "Error": STATUS_COLOR_ERROR,
        }
        self._set_status_label_color(self._sb_comm, state_map.get(state, STATUS_COLOR_INFO))

    def _set_ldf_status(self, ldf: LDFFile) -> None:
        """Update persistent LDF summary field."""
        self._sb_ldf.setText(
            f"LDF: LIN {ldf.protocol_version} | {ldf.speed} kbps | Frames: {len(ldf.frames)}"
        )
        self._set_status_label_color(self._sb_ldf, STATUS_COLOR_INFO)

    def _set_ldf_issues_status(self, warning_count: int, error_count: int) -> None:
        """Update persistent LDF validation issue counts."""
        self._sb_issues.setText(f"LDF issues: Warnings: {warning_count} | Errors: {error_count}")
        if error_count > 0:
            color = STATUS_COLOR_ERROR
        elif warning_count > 0:
            color = STATUS_COLOR_WARN
        else:
            color = STATUS_COLOR_OK
        self._set_status_label_color(self._sb_issues, color)

    def _build_menu(self) -> None:
        """Create the main menu bar and its actions."""
        mb = self.menuBar()

        # ---- File -------------------------------------------------------
        file_menu = mb.addMenu("&File")

        self._open_action = QAction("&Open LDF...", self)
        self._open_action.setShortcut(QKeySequence.Open)
        self._open_action.setStatusTip("Open a LIN Description File (.ldf)")
        self._open_action.triggered.connect(self._open_ldf)
        file_menu.addAction(self._open_action)

        focus_viewer_action = QAction("Focus LDF Tree", self)
        focus_viewer_action.setShortcut("Ctrl+1")
        focus_viewer_action.triggered.connect(self._focus_ldf_tree)
        file_menu.addAction(focus_viewer_action)

        focus_comm_action = QAction("Focus Communication", self)
        focus_comm_action.setShortcut("Ctrl+2")
        focus_comm_action.triggered.connect(self._focus_communication)
        file_menu.addAction(focus_comm_action)

        next_region_action = QAction("Next Region", self)
        next_region_action.setShortcut("F6")
        next_region_action.triggered.connect(self._focus_next_region)
        file_menu.addAction(next_region_action)

        prev_region_action = QAction("Previous Region", self)
        prev_region_action.setShortcut("Shift+F6")
        prev_region_action.triggered.connect(self._focus_previous_region)
        file_menu.addAction(prev_region_action)

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

        accessibility_action = QAction("Accessibility Help", self)
        accessibility_action.setShortcut("F1")
        accessibility_action.triggered.connect(self._show_accessibility_help)
        help_menu.addAction(accessibility_action)

        about_action = QAction("&About Easy-LIN", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        vector_action = QAction("Vector XL Driver Library...", self)
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

        issues = validate_ldf(ldf)
        warning_count = sum(1 for issue in issues if issue.severity == "warning")
        error_count = sum(1 for issue in issues if issue.severity == "error")

        if issues:
            proceed = self._show_ldf_issues_dialog(path, issues)
            if not proceed:
                return

        self._ldf = ldf
        self._ldf_path = path

        # Update window title
        self.setWindowTitle(f"{APP_NAME} - {os.path.basename(path)}")

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

        self._set_ldf_status(ldf)
        self._set_ldf_issues_status(warning_count, error_count)

        slaves = ldf.nodes.slaves if ldf.nodes else []
        self._announce_event(
            f"Loaded: {os.path.basename(path)}  |  "
            f"LIN {ldf.protocol_version}  |  {ldf.speed} kbps  |  "
            f"{len(ldf.frames)} frames  |  "
            f"{len(slaves)} slave(s)",
            timeout_ms=6000,
        )
        QTimer.singleShot(0, self._focus_ldf_tree)

    # ------------------------------------------------------------------
    # LDF validation gate dialogs
    # ------------------------------------------------------------------

    @staticmethod
    def _build_issues_report_text(path: str, issues: List) -> str:
        """Return a plain-text validation report suitable for saving to a file."""
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        lines = [
            "Easy-LIN LDF Validation Report",
            "=" * 40,
            f"File     : {path}",
            f"Date     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Errors   : {error_count}",
            f"Warnings : {warning_count}",
            "",
            "Issues",
            "------",
        ]
        for iss in issues:
            tag = "ERROR  " if iss.severity == "error" else "WARNING"
            lines.append(f"[{tag}] {iss.code}: {iss.message}")
        return "\n".join(lines)

    def _show_ldf_issues_dialog(self, path: str, issues: List) -> bool:
        """Show a validation report dialog.

        Returns True when the user chooses to open the file despite warnings.
        Always returns False when the file contains errors.
        """
        error_issues = [i for i in issues if i.severity == "error"]
        warning_issues = [i for i in issues if i.severity == "warning"]
        has_errors = bool(error_issues)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{APP_NAME} \u2013 LDF Validation Report")
        dlg.setMinimumSize(640, 420)

        layout = QVBoxLayout(dlg)

        if has_errors:
            summary = (
                f"<b>This file cannot be opened.</b><br>"
                f"It contains <b>{len(error_issues)} error(s)</b>"
                + (f" and <b>{len(warning_issues)} warning(s)</b>" if warning_issues else "")
                + ".<br>Review the report below, save it if needed, then fix your file."
            )
        else:
            summary = (
                f"<b>This file contains {len(warning_issues)} warning(s).</b><br>"
                "Opening it may cause unexpected behaviour.<br>"
                "You can save the report to analyse and repair your file before proceeding."
            )

        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        report_view = QPlainTextEdit()
        report_view.setReadOnly(True)
        report_view.setFont(QFont("Courier New", 9))
        report_view.setPlainText(self._build_issues_report_text(path, issues))
        report_view.setAccessibleName("Validation report")
        report_view.setAccessibleDescription("List of errors and warnings found in the LDF file")
        layout.addWidget(report_view)

        btn_box = QDialogButtonBox()
        save_btn = btn_box.addButton("Save Report\u2026", QDialogButtonBox.ActionRole)
        save_btn.setAccessibleName("Save validation report to a file")
        if has_errors:
            close_btn = btn_box.addButton(QDialogButtonBox.Close)
            close_btn.setDefault(True)
        else:
            open_btn = btn_box.addButton("Open Anyway", QDialogButtonBox.AcceptRole)
            open_btn.setAccessibleName("Open the LDF file despite the warnings")
            cancel_btn = btn_box.addButton(QDialogButtonBox.Cancel)
            cancel_btn.setDefault(True)

        layout.addWidget(btn_box)

        def _save_report() -> None:
            """Persist the current validation report text to a user-selected file."""
            default_name = os.path.splitext(path)[0] + "_validation_report.txt"
            save_path, _ = QFileDialog.getSaveFileName(
                dlg,
                "Save Validation Report",
                default_name,
                "Text files (*.txt);;All files (*)",
            )
            if save_path:
                try:
                    with open(save_path, "w", encoding="utf-8") as fh:
                        fh.write(self._build_issues_report_text(path, issues))
                except OSError as exc:
                    QMessageBox.warning(dlg, APP_NAME, f"Could not save report:\n{exc}")

        save_btn.clicked.connect(_save_report)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)

        result = dlg.exec_()
        if has_errors:
            return False
        return result == QDialog.Accepted

    def _build_shortcuts(self) -> None:
        """Create global shortcuts that work regardless of menu focus state."""
        self._shortcut_focus_tree = QShortcut(QKeySequence("Ctrl+1"), self)
        self._shortcut_focus_tree.setContext(Qt.ApplicationShortcut)
        self._shortcut_focus_tree.activated.connect(self._focus_ldf_tree)

        self._shortcut_focus_details = QShortcut(QKeySequence("Ctrl+2"), self)
        self._shortcut_focus_details.setContext(Qt.ApplicationShortcut)
        self._shortcut_focus_details.activated.connect(self._focus_communication)

        self._shortcut_next_region = QShortcut(QKeySequence("F6"), self)
        self._shortcut_next_region.setContext(Qt.ApplicationShortcut)
        self._shortcut_next_region.activated.connect(self._focus_next_region)

        self._shortcut_prev_region = QShortcut(QKeySequence("Shift+F6"), self)
        self._shortcut_prev_region.setContext(Qt.ApplicationShortcut)
        self._shortcut_prev_region.activated.connect(self._focus_previous_region)

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
        """Display an About dialog with clickable contact links and company logo."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {APP_NAME}")
        dialog.setMinimumWidth(560)

        layout = QVBoxLayout(dialog)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setAccessibleName("Company logo")
        logo_label.setAccessibleDescription("Logo image loaded from bundled local file")

        logo_pixmap = self._load_logo_pixmap(APP_COMPANY_LOGO_PATH)
        if logo_pixmap is not None:
            logo_label.setPixmap(
                logo_pixmap.scaled(220, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            logo_label.setText(APP_COMPANY)
        layout.addWidget(logo_label)

        about_text = QTextBrowser()
        about_text.setOpenExternalLinks(True)
        about_text.setReadOnly(True)
        about_text.setAccessibleName("About Easy-LIN details")
        about_text.setHtml(self._build_about_html())
        layout.addWidget(about_text)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec_()

    @staticmethod
    def _build_about_html() -> str:
        """Build rich HTML used by the About dialog."""
        return (
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>An open-source LIN master GUI for Vector VN16xx hardware.</p>"
            "<ul>"
            "<li>Parse and display LDF files (LIN 1.3 / 2.0 / 2.1 / 2.2)</li>"
            "<li>Connect via Vector XL Driver Library</li>"
            "<li>Send / receive LIN frames in real time</li>"
            "<li>Execute schedule tables automatically</li>"
            "</ul>"
            f"<p><b>Author:</b> {APP_AUTHOR}<br>"
            f"<b>Company:</b> {APP_COMPANY}<br>"
            f"<b>{APP_COPYRIGHT}</b><br>"
            f"<b>Email:</b> <a href='mailto:{APP_CONTACT_EMAIL}'>{APP_CONTACT_EMAIL}</a><br>"
            f"<b>Website:</b> <a href='{APP_WEBSITE}'>{APP_WEBSITE}</a></p>"
            "<p>Uses the <b>Vector XL Driver Library</b> (vxlapi.dll) for hardware "
            "communication. The driver must be installed separately from "
            "<a href='https://www.vector.com/'>vector.com</a>.</p>"
        )

    @staticmethod
    def _load_logo_pixmap(path: str) -> Optional[QPixmap]:
        """Return a pixmap loaded from a local file path, or ``None`` when unavailable."""
        if not os.path.exists(path):
            return None
        pixmap = QPixmap()
        if not pixmap.load(path):
            return None
        return pixmap

    def _show_accessibility_help(self) -> None:
        """Display keyboard shortcuts for accessible navigation."""
        QMessageBox.information(
            self,
            f"{APP_NAME} Accessibility",
            "Keyboard shortcuts:\n\n"
            "Ctrl+O: Open LDF file\n"
            "Ctrl+1: Focus hierarchy tree\n"
            "Ctrl+2: Focus communication panel\n"
            "Ctrl+C: Copy focused hierarchy line\n"
            "F6: Focus next region\n"
            "Shift+F6: Focus previous region\n"
            "F1: Open accessibility help\n\n"
            "Tip: use Tab and Shift+Tab to move between controls.",
        )

    def _focus_ldf_tree(self) -> None:
        """Move focus to the hierarchy tree in the LDF viewer."""
        viewer = self.centralWidget()
        if isinstance(viewer, LDFViewer):
            viewer.focus_hierarchy_tree()
            self._region_cycle_index = 0
            self._announce_event("Focus: hierarchy tree", timeout_ms=2000)
        elif viewer is not None:
            viewer.setFocus(Qt.ShortcutFocusReason)

    def _focus_ldf_details(self) -> None:
        """Compatibility alias that focuses the hierarchy tree."""
        viewer = self.centralWidget()
        if isinstance(viewer, LDFViewer):
            viewer.focus_hierarchy_tree()
            self._region_cycle_index = 0
            self._announce_event("Focus: hierarchy tree", timeout_ms=2000)
        elif viewer is not None:
            viewer.setFocus(Qt.ShortcutFocusReason)

    def _focus_communication(self) -> None:
        """Move focus to the communication panel controls."""
        self._comm_panel.focus_primary_control()
        self._region_cycle_index = 1
        self._announce_event("Focus: communication", timeout_ms=2000)

    def _focus_next_region(self) -> None:
        """Cycle keyboard focus to the next major UI region."""
        self._region_cycle_index = (self._region_cycle_index + 1) % 2
        self._focus_region_by_index(self._region_cycle_index)

    def _focus_previous_region(self) -> None:
        """Cycle keyboard focus to the previous major UI region."""
        self._region_cycle_index = (self._region_cycle_index - 1) % 2
        self._focus_region_by_index(self._region_cycle_index)

    def _focus_region_by_index(self, index: int) -> None:
        """Focus one region identified by cycle index."""
        if index == 0:
            self._focus_ldf_tree()
        else:
            self._focus_communication()

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
