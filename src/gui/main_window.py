"""Easy-LIN main application window.

This Tk window hosts the accessible tree view, narrated detail panel, LIN
communication panel, and status bar used by the default Easy-LIN frontend.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.ldf_parser import LDFFile, LDFParseError, parse_ldf
from src.gui.ldf_tree import LDFTreeView
from src.gui.signal_viewer import DetailViewer
from src.gui.comm_panel import CommunicationPanel
from src.ldf_presenter import describe_key

logger = logging.getLogger(__name__)

_APP_TITLE = "Easy-LIN"
_ABOUT_TEXT = (
    "Easy-LIN\n\n"
    "A Python GUI tool for reading LIN Description Files (LDF) and "
    "communicating on the LIN bus via Vector CAN hardware.\n\n"
    "LIN protocol versions 1.3, 2.0, 2.1 and 2.2 are supported."
)


class MainWindow(tk.Tk):
    """The top-level application window."""

    def __init__(self) -> None:
        """Initialize the main window and its child widgets."""
        super().__init__()
        self.title(_APP_TITLE)
        self.geometry("1200x780")
        self.minsize(800, 550)

        self._ldf: Optional[LDFFile] = None
        self._last_description = "Ready. Open an LDF file to get started."
        self._closing = False

        self._apply_theme()
        self._build_menu()
        self._build_layout()
        self._build_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_status("Ready.  Open an LDF file to get started.")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """Apply the base ttk theme used by the Tk frontend."""
        style = ttk.Style(self)
        # Use 'clam' as a clean cross-platform base
        available = style.theme_names()
        for preferred in ("clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break
        style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", padding=4)
        self.configure(background="#ecf0f1")

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """Create application menus and keyboard shortcuts."""
        menubar = tk.Menu(self)

        # â”€â”€ File â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open LDFâ€¦", accelerator="Ctrl+O", command=self._open_ldf)
        file_menu.add_command(
            label="Focus Tree",
            accelerator="Ctrl+1",
            command=lambda: self._tree_view.focus_tree(),
        )
        file_menu.add_command(
            label="Focus Details",
            accelerator="Ctrl+2",
            command=lambda: self._detail_viewer.focus_text(),
        )
        file_menu.add_command(label="Close LDF", command=self._close_ldf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # â”€â”€ View â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Expand All Tree", command=self._expand_all)
        view_menu.add_command(label="Collapse All Tree", command=self._collapse_all)
        menubar.add_cascade(label="View", menu=view_menu)

        # â”€â”€ Help â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Accessibility Help", command=self._show_accessibility_help)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)
        self.bind("<Control-o>", lambda _: self._open_ldf())
        self.bind("<Control-1>", lambda _: self._tree_view.focus_tree())
        self.bind("<Control-2>", lambda _: self._detail_viewer.focus_text())
        self.bind("<F1>", lambda _: self._show_accessibility_help())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        """Create the main paned layout for navigation and communication."""
        # â”€â”€ Outer vertical paned window (top area / comm panel) â”€â”€â”€â”€â”€â”€â”€
        outer_pane = ttk.PanedWindow(self, orient="vertical")
        outer_pane.pack(fill="both", expand=True, padx=4, pady=4)

        # â”€â”€ Top: horizontal paned window (tree / detail) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        top_pane = ttk.PanedWindow(outer_pane, orient="horizontal")

        # Left: LDF tree view
        tree_frame = ttk.LabelFrame(top_pane, text="LDF Structure")
        self._tree_view = LDFTreeView(tree_frame, on_select=self._on_tree_select)
        self._tree_view.pack(fill="both", expand=True, padx=2, pady=2)
        top_pane.add(tree_frame, weight=2)

        # Right: detail viewer
        self._detail_viewer = DetailViewer(top_pane)
        top_pane.add(self._detail_viewer, weight=3)

        outer_pane.add(top_pane, weight=3)

        # â”€â”€ Bottom: communication panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._comm_panel = CommunicationPanel(outer_pane)
        outer_pane.add(self._comm_panel, weight=1)

    def _build_status_bar(self) -> None:
        """Create the status bar shown at the bottom of the window."""
        bar = ttk.Frame(self, relief="sunken")
        bar.pack(side="bottom", fill="x")
        self._status_var = tk.StringVar()
        ttk.Label(bar, textvariable=self._status_var, anchor="w", padding=(6, 2)).pack(
            side="left", fill="x", expand=True
        )

    # ------------------------------------------------------------------
    # LDF file operations
    # ------------------------------------------------------------------

    def _open_ldf(self) -> None:
        """Prompt for an LDF file and load it into the application."""
        path = filedialog.askopenfilename(
            parent=self,
            title="Open LDF file",
            filetypes=[("LIN Description Files", "*.ldf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            ldf = parse_ldf(path)
            self._load_ldf(ldf)
            self._set_status(
                f"Loaded: {Path(path).name}  "
                f"({len(ldf.signals)} signals, "
                f"{len(ldf.frames)} frames, "
                f"{len(ldf.schedule_tables)} schedule tables)"
            )
        except LDFParseError as exc:
            logger.exception("LDF syntax/structure error while parsing %s", path)
            messagebox.showerror(
                "Parse error",
                f"Could not parse LDF file:\n{exc}",
                parent=self,
            )
        except Exception as exc:
            logger.exception("Failed to parse LDF file %s", path)
            messagebox.showerror(
                "Open error",
                f"Unexpected error while opening the selected file:\n{exc}",
                parent=self,
            )

    def _close_ldf(self) -> None:
        """Unload the current LDF from all visible widgets."""
        self._ldf = None
        self._tree_view.clear()
        self._detail_viewer.clear()
        self.title(_APP_TITLE)
        self._set_status("LDF file closed.")

    def _load_ldf(self, ldf: LDFFile) -> None:
        """Populate all UI panels from a parsed LDF object."""
        self._ldf = ldf
        self._tree_view.load(ldf)
        self._detail_viewer.set_ldf(ldf)
        self._comm_panel.set_ldf(ldf)
        source_path = getattr(ldf, "source_path", "")
        filename = Path(source_path).name if source_path else "LDF"
        self.title(f"{_APP_TITLE} â€“ {filename}")

    # ------------------------------------------------------------------
    # Tree selection
    # ------------------------------------------------------------------

    def _on_tree_select(self, info: dict) -> None:
        """Update the details panel and status line for the selected node."""
        self._detail_viewer.show(info)
        if self._ldf and info.get("key"):
            description = describe_key(self._ldf, info["key"])
            line = description.splitlines()[0] if description else ""
            self._last_description = line
            self._set_status(line)

    # ------------------------------------------------------------------
    # View helpers
    # ------------------------------------------------------------------

    def _expand_all(self) -> None:
        """Expand every node in the structure tree."""
        tree = self._tree_view._tree
        for item in tree.get_children():
            self._expand_item(tree, item)

    def _expand_item(self, tree: ttk.Treeview, item: str) -> None:
        """Recursively expand one tree item and all its children."""
        tree.item(item, open=True)
        for child in tree.get_children(item):
            self._expand_item(tree, child)

    def _collapse_all(self) -> None:
        """Collapse every node in the structure tree."""
        tree = self._tree_view._tree
        for item in tree.get_children():
            self._collapse_item(tree, item)

    def _collapse_item(self, tree: ttk.Treeview, item: str) -> None:
        """Recursively collapse one tree item and all its children."""
        tree.item(item, open=False)
        for child in tree.get_children(item):
            self._collapse_item(tree, child)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        """Replace the current status-bar message."""
        self._status_var.set(msg)

    def _show_about(self) -> None:
        """Display the application about dialog."""
        messagebox.showinfo("About Easy-LIN", _ABOUT_TEXT, parent=self)

    def _show_accessibility_help(self) -> None:
        """Display keyboard shortcuts and accessibility guidance."""
        messagebox.showinfo(
            "Accessibility Help",
            "Easy-LIN Accessibility Shortcuts\n\n"
            "Ctrl+O: Open LDF file\n"
            "Ctrl+1: Focus tree navigation\n"
            "Ctrl+2: Focus textual details\n"
            "F1: Open this help\n\n"
            "Tip: Tree selections are mirrored to the status bar and details panel "
            "for better screen reader narration.",
            parent=self,
        )

    def _on_close(self) -> None:
        """Stop communication threads and close the application window."""
        if self._closing:
            return
        self._closing = True
        try:
            self._comm_panel.stop()
        except Exception:
            logger.exception("Error while stopping communication panel on exit")
        self.quit()
        self.destroy()

