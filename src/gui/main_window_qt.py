"""Easy-LIN main window for the PySide6 frontend.

Provides the top-level application window hosting the LDF viewer,
menus, toolbar, and persistent window state.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

# pylint: disable=too-many-lines

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QFileDialog,
    QMessageBox,
    QLabel,
    QToolBar,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QPlainTextEdit,
    QComboBox,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, QSettings, QSize, QTimer
from PySide6.QtGui import (
    QAction,
    QFont,
    QKeySequence,
    QColor,
    QPixmap,
    QShortcut,
    QAccessible,
    QAccessibleAnnouncementEvent,
)

from src.ldf_parser import parse_ldf, LDFFile, LDFParseError
from src.ldf_consistency import validate_ldf
from src.gui.ldf_viewer import LDFViewer
from src.gui.communication_window import CommunicationWindow

log = logging.getLogger(__name__)

APP_NAME = "Easy-LIN"
APP_ORG = "Easy-LIN"
APP_VERSION = "0.10.0"
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
        """Initialize the main PySide6 window and restore persisted state."""
        super().__init__()
        self._ldf: Optional[LDFFile] = None
        self._ldf_path: Optional[str] = None
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._region_cycle_index = 0
        self._comm_selection: Optional[tuple[str, list[str]]] = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 700)
        self.setAccessibleName("Easy-LIN main window")
        self.setAccessibleDescription(
            "Main application window for loading LDF files, navigating their hierarchy, and opening the communication window."
        )

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
        self._placeholder.setAccessibleName("Welcome placeholder")
        self._placeholder.setAccessibleDescription(
            "Placeholder view shown before an LDF file is loaded."
        )
        placeholder_lbl = QLabel(
            "<h2>Welcome to Easy-LIN</h2>"
            "<p>Open an LDF file via <b>File > Open LDF...</b> to get started.</p>"
            "<p>Easy-LIN acts as a LIN master and allows you to:<br>"
            "- Inspect every section of an LDF file<br>"
            "- Monitor and send LIN frames in real time<br>"
            "- Execute schedule tables automatically</p>"
        )
        placeholder_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_lbl.setTextFormat(Qt.TextFormat.RichText)
        placeholder_lbl.setAccessibleName("Welcome message")
        placeholder_lbl.setAccessibleDescription(
            "Introductory guidance explaining how to open an LDF file and what Easy-LIN can do."
        )
        font = QFont()
        font.setPointSize(11)
        placeholder_lbl.setFont(font)
        pl = QVBoxLayout(self._placeholder)
        pl.addWidget(placeholder_lbl)
        self.setCentralWidget(self._placeholder)

        # Separate communication window
        self._comm_window = CommunicationWindow()
        self._comm_window.status_message.connect(self._on_comm_status_message)
        self._comm_window.communication_state_changed.connect(self._set_comm_status)
        self._comm_window.hide()

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
        self._sb_ldf.setAccessibleDescription(
            "Summarizes the currently loaded LDF version, speed, and frame count."
        )
        self._sb_issues.setAccessibleDescription(
            "Shows the current number of LDF validation warnings and errors."
        )
        self._sb_comm.setAccessibleDescription(
            "Shows whether hardware communication is connected, disconnected, or in error."
        )
        self._sb_event.setAccessibleDescription(
            "Shows the latest event or user feedback message from the application."
        )

        self._set_status_label_color(self._sb_ldf, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_issues, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_comm, STATUS_COLOR_NEUTRAL)
        self._set_status_label_color(self._sb_event, STATUS_COLOR_INFO)

        sb.addPermanentWidget(self._sb_ldf)
        sb.addPermanentWidget(self._sb_issues)
        sb.addPermanentWidget(self._sb_comm)
        sb.addPermanentWidget(self._sb_event, 1)

    def _announce_event(
        self, message: str, timeout_ms: int = 5000, assertive: bool = False
    ) -> None:
        """Show a short-lived status bar message and persist it as latest event.

        When *assertive* is True, also fires a QAccessibleAnnouncementEvent so
        that screen readers (NVDA, JAWS, Narrator) interrupt what they are
        currently reading and speak the message immediately.
        """
        self.statusBar().showMessage(message, timeout_ms)
        self._sb_event.setText(f"Last event: {message}")
        event_color = STATUS_COLOR_INFO
        lowered = message.lower()
        if "error" in lowered or "failed" in lowered:
            event_color = STATUS_COLOR_ERROR
        elif "warning" in lowered:
            event_color = STATUS_COLOR_WARN
        self._set_status_label_color(self._sb_event, event_color)
        if assertive:
            try:
                ann = QAccessibleAnnouncementEvent(self, message)
                ann.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive)
                QAccessible.updateAccessibility(ann)
            except Exception:
                pass

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
        _viewer = self.centralWidget()
        if isinstance(_viewer, LDFViewer):
            _viewer.lock_node_selection(state == "Connected")

    def _on_node_selection_changed(self, master: str, slaves: list[str]) -> None:
        """Update communication selection when node checkboxes change in the LDF tree."""
        self._comm_selection = (master, slaves)
        self._comm_window.queue_selection(master, slaves)
        self._announce_event(
            f"Node selection: master {master!r}, {len(slaves)} slave(s)",
            timeout_ms=3000,
        )

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

        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu("Recent Files")
        self._update_recent_menu()

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ---- Accessibility ---------------------------------------------
        accessibility_menu = mb.addMenu("&Accessibility")

        focus_viewer_action = QAction("Focus LDF Tree", self)
        focus_viewer_action.setShortcut("Ctrl+1")
        focus_viewer_action.triggered.connect(self._focus_ldf_tree)
        accessibility_menu.addAction(focus_viewer_action)

        focus_comm_action = QAction("Focus Communication", self)
        focus_comm_action.setShortcut("Ctrl+2")
        focus_comm_action.triggered.connect(self._focus_communication)
        accessibility_menu.addAction(focus_comm_action)

        next_region_action = QAction("Next Region", self)
        next_region_action.setShortcut("F6")
        next_region_action.triggered.connect(self._focus_next_region)
        accessibility_menu.addAction(next_region_action)

        prev_region_action = QAction("Previous Region", self)
        prev_region_action.setShortcut("Shift+F6")
        prev_region_action.triggered.connect(self._focus_previous_region)
        accessibility_menu.addAction(prev_region_action)

        accessibility_menu.addSeparator()

        accessibility_action = QAction("Accessibility Help", self)
        accessibility_action.setShortcut("F1")
        accessibility_action.triggered.connect(self._show_accessibility_help)
        accessibility_menu.addAction(accessibility_action)

        # ---- View -------------------------------------------------------
        view_menu = mb.addMenu("&View")
        self._toggle_comm_action = QAction("Communication Window", self)
        self._toggle_comm_action.setShortcut("Ctrl+Shift+C")
        self._toggle_comm_action.triggered.connect(self._toggle_communication_window)
        view_menu.addAction(self._toggle_comm_action)

        # ---- Help -------------------------------------------------------
        help_menu = mb.addMenu("&Help")

        about_action = QAction("&About Easy-LIN", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        manual_action = QAction("Open &GUI User Manual", self)
        manual_action.triggered.connect(self._open_user_manual)
        help_menu.addAction(manual_action)

    def _build_toolbar(self) -> None:
        """Create the fixed main toolbar."""
        tb: QToolBar = self.addToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))
        tb.setAccessibleName("Main toolbar")
        tb.setAccessibleDescription(
            "Toolbar containing quick-access actions such as opening an LDF file."
        )
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
            viewer.node_selection_changed.connect(self._on_node_selection_changed)

        # Update communication window and reset communication selection.
        self._comm_window.queue_ldf(ldf)
        self._comm_selection = None
        # Initialize comm selection from tree node checkboxes.
        _cur_viewer = self.centralWidget()
        if isinstance(_cur_viewer, LDFViewer):
            _master, _slaves = _cur_viewer.selected_nodes()
            if _master and _slaves:
                self._comm_selection = (_master, _slaves)
                self._comm_window.queue_selection(_master, _slaves)

        # Save to recent files
        self._add_recent(path)
        self._settings.setValue("last_open_dir", os.path.dirname(path))

        self._set_ldf_status(ldf)
        self._set_ldf_issues_status(warning_count, error_count)

        slaves = ldf.nodes.slaves if ldf.nodes else []
        master_name = ldf.nodes.master.name if ldf.nodes and ldf.nodes.master else "unknown"
        self._announce_event(
            f"Parse successful. "
            f"{os.path.basename(path)}, "
            f"LIN {ldf.protocol_version}, {ldf.speed} kbps. "
            f"1 master: {master_name}. "
            f"{len(slaves)} slave(s). "
            f"{len(ldf.frames)} frames.",
            timeout_ms=8000,
            assertive=True,
        )
        QTimer.singleShot(0, self._focus_ldf_tree_silent)

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
        dlg.setAccessibleName("LDF validation report dialog")
        dlg.setAccessibleDescription(
            "Review validation errors and warnings before deciding whether the selected LDF file can be opened."
        )

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
        summary_label.setAccessibleName("Validation summary")
        layout.addWidget(summary_label)

        report_view = QPlainTextEdit()
        report_view.setReadOnly(True)
        report_view.setFont(QFont("Courier New", 9))
        report_view.setPlainText(self._build_issues_report_text(path, issues))
        report_view.setAccessibleName("Validation report")
        report_view.setAccessibleDescription("List of errors and warnings found in the LDF file")
        layout.addWidget(report_view)

        btn_box = QDialogButtonBox()
        save_btn = btn_box.addButton("Save Report\u2026", QDialogButtonBox.ButtonRole.ActionRole)
        save_btn.setAccessibleName("Save validation report to a file")
        save_btn.setAccessibleDescription("Save the current validation report to a text file.")
        if has_errors:
            close_btn = btn_box.addButton(QDialogButtonBox.StandardButton.Close)
            close_btn.setAccessibleName("Close validation report")
            close_btn.setAccessibleDescription(
                "Close this validation report. The file cannot be opened until the reported errors are fixed."
            )
            close_btn.setDefault(True)
        else:
            open_btn = btn_box.addButton("Open Anyway", QDialogButtonBox.ButtonRole.AcceptRole)
            open_btn.setAccessibleName("Open the LDF file despite the warnings")
            open_btn.setAccessibleDescription(
                "Continue opening the selected LDF file even though warnings were reported."
            )
            cancel_btn = btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
            cancel_btn.setAccessibleName("Cancel opening the LDF file")
            cancel_btn.setAccessibleDescription(
                "Close this validation report without opening the selected LDF file."
            )
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
        report_view.setFocus(Qt.FocusReason.OtherFocusReason)
        dlg.setTabOrder(report_view, save_btn)
        if has_errors:
            dlg.setTabOrder(save_btn, close_btn)
        else:
            dlg.setTabOrder(save_btn, open_btn)
            dlg.setTabOrder(open_btn, cancel_btn)

        result = dlg.exec()
        if has_errors:
            return False
        return result == QDialog.DialogCode.Accepted

    def _build_shortcuts(self) -> None:
        """Create global shortcuts that work regardless of menu focus state."""
        self._shortcut_focus_tree = QShortcut(QKeySequence("Ctrl+1"), self)
        self._shortcut_focus_tree.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_focus_tree.activated.connect(self._focus_ldf_tree)

        self._shortcut_focus_details = QShortcut(QKeySequence("Ctrl+2"), self)
        self._shortcut_focus_details.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_focus_details.activated.connect(self._focus_communication)

        self._shortcut_next_region = QShortcut(QKeySequence("F6"), self)
        self._shortcut_next_region.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_next_region.activated.connect(self._focus_next_region)

        self._shortcut_prev_region = QShortcut(QKeySequence("Shift+F6"), self)
        self._shortcut_prev_region.setContext(Qt.ShortcutContext.ApplicationShortcut)
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
        """Display an About dialog using accessible label-only content."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {APP_NAME}")
        dialog.setMinimumSize(640, 520)
        dialog.resize(760, 560)
        dialog.setAccessibleName(f"About {APP_NAME} dialog")
        dialog.setAccessibleDescription(
            "Application information, support contacts, and company details for Easy-LIN."
        )

        layout = QVBoxLayout(dialog)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setMaximumHeight(110)
        logo_label.setAccessibleName("Company logo")
        logo_label.setAccessibleDescription("Logo image loaded from bundled local file")

        logo_pixmap = self._load_logo_pixmap(APP_COMPANY_LOGO_PATH)
        if logo_pixmap is not None:
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    180,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo_label.setText(APP_COMPANY)
        layout.addWidget(logo_label)

        def _make_label(text: str, description: str, point_size: int = 10) -> QLabel:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByKeyboard
                | Qt.TextInteractionFlag.TextSelectableByMouse
            )
            lbl.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            # Keep the accessible name equal to the visible content so screen
            # readers speak the actual information instead of abstract labels.
            lbl.setAccessibleName(text)
            lbl.setAccessibleDescription(description)
            font = lbl.font()
            font.setPointSize(point_size)
            lbl.setFont(font)
            return lbl

        title_label = _make_label(
            f"{APP_NAME} {APP_VERSION}",
            "Product name and version.",
            point_size=13,
        )
        summary_label = _make_label(
            "An open-source LIN master GUI for Vector VN16xx hardware.",
            "Product summary description.",
            point_size=11,
        )
        author_label = _make_label(
            f"Author: {APP_AUTHOR}",
            "Author information.",
        )
        company_label = _make_label(
            f"Company: {APP_COMPANY}",
            "Company information.",
        )
        copyright_label = _make_label(
            APP_COPYRIGHT,
            "Copyright statement.",
        )
        email_label = _make_label(
            f"Email: {APP_CONTACT_EMAIL}",
            "Support email address.",
        )
        website_label = _make_label(
            f"Website: {APP_WEBSITE}",
            "Project website URL.",
        )

        layout.addWidget(title_label)
        layout.addWidget(summary_label)
        layout.addWidget(author_label)
        layout.addWidget(company_label)
        layout.addWidget(copyright_label)
        layout.addWidget(email_label)
        layout.addWidget(website_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setAccessibleName("Close About dialog")
            close_btn.setAccessibleDescription("Close the About Easy-LIN dialog.")
        layout.addWidget(buttons)
        summary_label.setFocus(Qt.FocusReason.OtherFocusReason)
        if close_btn is not None:
            dialog.setTabOrder(summary_label, close_btn)

        dialog.exec()

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
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle(f"{APP_NAME} Accessibility")
        msg_box.setAccessibleName("Accessibility help dialog")
        msg_box.setAccessibleDescription(
            "Keyboard shortcut reference for navigating the Easy-LIN interface."
        )
        msg_box.setText(
            "Keyboard shortcuts:\n\n"
            "Ctrl+O: Open LDF file\n"
            "Ctrl+1: Focus hierarchy tree\n"
            "Ctrl+2: Focus communication window\n"
            "Ctrl+Shift+C: Toggle communication window\n"
            "Ctrl+C: Copy focused hierarchy line\n"
            "Ctrl+F: Search in hierarchy tree\n"
            "F3: Find next match\n"
            "Alt+Up/Down: Navigate to previous/next sibling\n"
            "Ctrl+Shift+Right: Expand all children\n"
            "Ctrl+Shift+Left: Collapse all children\n"
            "F6: Focus next region\n"
            "Shift+F6: Focus previous region\n"
            "F1: Open accessibility help\n\n"
            "Tip: use Tab and Shift+Tab to move between controls."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _resolve_node_choices(self) -> tuple[list[str], list[str]]:
        """Extract candidate masters and slaves from the currently loaded LDF."""
        if self._ldf is None or self._ldf.nodes is None:
            return [], []

        masters: list[str] = []
        node_master = getattr(self._ldf.nodes, "master", None)
        if node_master is not None:
            if isinstance(node_master, list):
                masters = [str(m) for m in node_master if str(m).strip()]
            else:
                name = getattr(node_master, "name", str(node_master))
                if str(name).strip():
                    masters = [str(name)]

        slaves = [str(s) for s in (self._ldf.nodes.slaves or []) if str(s).strip()]
        return masters, slaves

    def _prompt_comm_selection(self) -> Optional[tuple[str, list[str]]]:
        """Prompt the user to select one master and at least one slave node."""
        masters, slaves = self._resolve_node_choices()
        if not masters:
            QMessageBox.warning(self, APP_NAME, "No master node found in this LDF.")
            return None
        if not slaves:
            QMessageBox.warning(self, APP_NAME, "No slave node found in this LDF.")
            return None

        if len(masters) == 1 and len(slaves) == 1:
            return masters[0], [slaves[0]]

        dlg = QDialog(self)
        dlg.setWindowTitle("Communication Node Selection")
        dlg.setMinimumWidth(420)
        dlg.setAccessibleName("Communication node selection dialog")
        dlg.setAccessibleDescription(
            "Choose one master node and one or more slave nodes for the communication session."
        )
        layout = QVBoxLayout(dlg)

        master_label = QLabel("Select one master:")
        layout.addWidget(master_label)
        master_combo = QComboBox()
        master_combo.setAccessibleName("Communication master selection")
        master_combo.setAccessibleDescription(
            "Choose the master node that will control the communication session."
        )
        for master in masters:
            master_combo.addItem(master)
        master_label.setBuddy(master_combo)
        layout.addWidget(master_combo)

        slave_label = QLabel("Select at least one slave:")
        layout.addWidget(slave_label)
        slaves_list = QListWidget()
        slaves_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        slaves_list.setAccessibleName("Communication slave selection")
        slaves_list.setAccessibleDescription(
            "Select one or more slave nodes to include in the communication session."
        )
        for slave in slaves:
            item = QListWidgetItem(slave)
            slaves_list.addItem(item)
        slaves_list.selectAll()
        slave_label.setBuddy(slaves_list)
        layout.addWidget(slaves_list)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btn_box)
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setAccessibleName("Confirm communication node selection")
            ok_btn.setAccessibleDescription("Apply the selected master and slave nodes.")
        if cancel_btn is not None:
            cancel_btn.setAccessibleName("Cancel communication node selection")
            cancel_btn.setAccessibleDescription(
                "Close this dialog without changing the communication selection."
            )

        def _accept_if_valid() -> None:
            """Reject confirmation until at least one slave node is selected."""
            selected_slaves = [i.text() for i in slaves_list.selectedItems()]
            if not selected_slaves:
                QMessageBox.warning(dlg, APP_NAME, "Select at least one slave to continue.")
                return
            dlg.accept()

        btn_box.accepted.connect(_accept_if_valid)
        btn_box.rejected.connect(dlg.reject)
        master_combo.setFocus(Qt.FocusReason.OtherFocusReason)
        dlg.setTabOrder(master_combo, slaves_list)
        if ok_btn is not None:
            dlg.setTabOrder(slaves_list, ok_btn)
            if cancel_btn is not None:
                dlg.setTabOrder(ok_btn, cancel_btn)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        selected_slaves = [i.text() for i in slaves_list.selectedItems()]
        return master_combo.currentText(), selected_slaves

    def _ensure_comm_selection(self) -> bool:
        """Ensure communication node selection is available before showing comm window."""
        if self._ldf is None:
            self._announce_event("Load an LDF file first.", timeout_ms=3000)
            return False
        if self._comm_selection is not None:
            return True

        selection = self._prompt_comm_selection()
        if selection is None:
            self._announce_event("Communication setup cancelled.", timeout_ms=3000)
            return False

        master, slaves = selection
        self._comm_window.queue_selection(master, slaves)
        self._comm_selection = (master, slaves)
        self._announce_event(
            f"Communication selection: master {master}, slaves {len(slaves)}",
            timeout_ms=4000,
        )
        return True

    def _focus_ldf_tree(self) -> None:
        """Move focus to the hierarchy tree in the LDF viewer."""
        viewer = self.centralWidget()
        if isinstance(viewer, LDFViewer):
            viewer.focus_hierarchy_tree()
            self._region_cycle_index = 0
            self._announce_event("Focus: hierarchy tree", timeout_ms=2000)
        elif viewer is not None:
            viewer.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _focus_ldf_tree_silent(self) -> None:
        """Move focus to the hierarchy tree after an LDF load.

        Unlike _focus_ldf_tree this variant does *not* emit a 'Focus:
        hierarchy tree' announcement so the parse-success message that was
        just fired stays as the last event heard by screen readers.
        """
        viewer = self.centralWidget()
        if isinstance(viewer, LDFViewer):
            viewer.focus_hierarchy_tree()
            self._region_cycle_index = 0
        elif viewer is not None:
            viewer.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _focus_ldf_details(self) -> None:
        """Compatibility alias that focuses the hierarchy tree."""
        viewer = self.centralWidget()
        if isinstance(viewer, LDFViewer):
            viewer.focus_hierarchy_tree()
            self._region_cycle_index = 0
            self._announce_event("Focus: hierarchy tree", timeout_ms=2000)
        elif viewer is not None:
            viewer.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _focus_communication(self) -> None:
        """Show and focus the communication window controls."""
        if not self._ensure_comm_selection():
            return
        self._comm_window.focus_primary_control()
        self._region_cycle_index = 1
        self._announce_event("Focus: communication", timeout_ms=2000)

    def _toggle_communication_window(self) -> None:
        """Show or hide the standalone communication window."""
        if self._comm_window.isVisible():
            self._comm_window.hide()
            return
        if not self._ensure_comm_selection():
            return
        self._comm_window.show()
        self._comm_window.raise_()

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
    def _open_user_manual() -> None:
        """Open the local GUI user manual in the default browser."""
        import webbrowser

        root = Path(__file__).resolve().parents[2]
        candidates = [
            root / "docs" / "_build" / "html" / "index.html",
            root / "docs" / "index.rst",
            root / "README.md",
        ]
        for path in candidates:
            if path.exists():
                webbrowser.open(path.resolve().as_uri())
                return

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        """Restore window geometry from settings."""
        geom = self._settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

    def closeEvent(self, event) -> None:
        """Persist geometry before closing the window and communication window."""
        self._settings.setValue("geometry", self.saveGeometry())
        # Force-close the communication window (bypass its hide-on-close)
        self._comm_window._settings.setValue("comm_geometry", self._comm_window.saveGeometry())
        self._comm_window.deleteLater()
        super().closeEvent(event)
