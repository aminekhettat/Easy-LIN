"""
Easy-LIN main application window.

Layout
------
┌──────────────────────────────────────────────────────┐
│  Menu bar                                            │
├────────────────┬─────────────────────────────────────┤
│                │                                     │
│  LDF Tree View │      Detail Viewer                  │
│  (left pane)   │      (right pane)                   │
│                │                                     │
├────────────────┴─────────────────────────────────────┤
│  Communication Panel (LIN bus monitor + send)        │
├──────────────────────────────────────────────────────┤
│  Status bar                                          │
└──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.ldf.parser import LDFFile, LDFParser
from src.gui.ldf_tree import LDFTreeView
from src.gui.signal_viewer import DetailViewer
from src.gui.comm_panel import CommunicationPanel

logger = logging.getLogger(__name__)

_APP_TITLE = 'Easy-LIN'
_ABOUT_TEXT = (
    'Easy-LIN\n\n'
    'A Python GUI tool for reading LIN Description Files (LDF) and '
    'communicating on the LIN bus via Vector CAN hardware.\n\n'
    'LIN protocol versions 1.3, 2.0, 2.1 and 2.2 are supported.'
)


class MainWindow(tk.Tk):
    """The top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(_APP_TITLE)
        self.geometry('1200x780')
        self.minsize(800, 550)

        self._ldf: Optional[LDFFile] = None
        self._parser = LDFParser()

        self._apply_theme()
        self._build_menu()
        self._build_layout()
        self._build_status_bar()

        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._set_status('Ready.  Open an LDF file to get started.')

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        # Use 'clam' as a clean cross-platform base
        available = style.theme_names()
        for preferred in ('clam', 'alt', 'default'):
            if preferred in available:
                style.theme_use(preferred)
                break
        style.configure('TLabelframe.Label', font=('Segoe UI', 9, 'bold'))
        style.configure('TButton', padding=4)
        self.configure(background='#ecf0f1')

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        # ── File ─────────────────────────────────────────────────────
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label='Open LDF…', accelerator='Ctrl+O', command=self._open_ldf
        )
        file_menu.add_command(
            label='Close LDF', command=self._close_ldf
        )
        file_menu.add_separator()
        file_menu.add_command(label='Exit', command=self._on_close)
        menubar.add_cascade(label='File', menu=file_menu)

        # ── View ─────────────────────────────────────────────────────
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(
            label='Expand All Tree', command=self._expand_all
        )
        view_menu.add_command(
            label='Collapse All Tree', command=self._collapse_all
        )
        menubar.add_cascade(label='View', menu=view_menu)

        # ── Help ─────────────────────────────────────────────────────
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label='About', command=self._show_about)
        menubar.add_cascade(label='Help', menu=help_menu)

        self.config(menu=menubar)
        self.bind('<Control-o>', lambda _: self._open_ldf())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        # ── Outer vertical paned window (top area / comm panel) ───────
        outer_pane = ttk.PanedWindow(self, orient='vertical')
        outer_pane.pack(fill='both', expand=True, padx=4, pady=4)

        # ── Top: horizontal paned window (tree / detail) ──────────────
        top_pane = ttk.PanedWindow(outer_pane, orient='horizontal')

        # Left: LDF tree view
        tree_frame = ttk.LabelFrame(top_pane, text='LDF Structure')
        self._tree_view = LDFTreeView(
            tree_frame, on_select=self._on_tree_select
        )
        self._tree_view.pack(fill='both', expand=True, padx=2, pady=2)
        top_pane.add(tree_frame, weight=2)

        # Right: detail viewer
        self._detail_viewer = DetailViewer(top_pane)
        top_pane.add(self._detail_viewer, weight=3)

        outer_pane.add(top_pane, weight=3)

        # ── Bottom: communication panel ───────────────────────────────
        self._comm_panel = CommunicationPanel(outer_pane)
        outer_pane.add(self._comm_panel, weight=1)

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, relief='sunken')
        bar.pack(side='bottom', fill='x')
        self._status_var = tk.StringVar()
        ttk.Label(
            bar, textvariable=self._status_var, anchor='w', padding=(6, 2)
        ).pack(side='left', fill='x', expand=True)

    # ------------------------------------------------------------------
    # LDF file operations
    # ------------------------------------------------------------------

    def _open_ldf(self) -> None:
        path = filedialog.askopenfilename(
            title='Open LDF file',
            filetypes=[('LIN Description Files', '*.ldf'), ('All files', '*.*')],
        )
        if not path:
            return
        try:
            ldf = self._parser.parse_file(path)
            self._load_ldf(ldf)
            self._set_status(
                f'Loaded: {Path(path).name}  '
                f'({len(ldf.signals)} signals, '
                f'{len(ldf.frames)} frames, '
                f'{len(ldf.schedule_tables)} schedule tables)'
            )
        except Exception as exc:
            logger.exception("Failed to parse LDF file %s", path)
            messagebox.showerror('Parse error', f'Could not parse LDF file:\n{exc}')

    def _close_ldf(self) -> None:
        self._ldf = None
        self._tree_view.clear()
        self._detail_viewer.clear()
        self.title(_APP_TITLE)
        self._set_status('LDF file closed.')

    def _load_ldf(self, ldf: LDFFile) -> None:
        self._ldf = ldf
        self._tree_view.load(ldf)
        self._detail_viewer.set_ldf(ldf)
        self._comm_panel.set_ldf(ldf)
        filename = Path(ldf.source_path).name if ldf.source_path else 'LDF'
        self.title(f'{_APP_TITLE} – {filename}')

    # ------------------------------------------------------------------
    # Tree selection
    # ------------------------------------------------------------------

    def _on_tree_select(self, info: dict) -> None:
        self._detail_viewer.show(info)

    # ------------------------------------------------------------------
    # View helpers
    # ------------------------------------------------------------------

    def _expand_all(self) -> None:
        tree = self._tree_view._tree
        for item in tree.get_children():
            self._expand_item(tree, item)

    def _expand_item(self, tree: ttk.Treeview, item: str) -> None:
        tree.item(item, open=True)
        for child in tree.get_children(item):
            self._expand_item(tree, child)

    def _collapse_all(self) -> None:
        tree = self._tree_view._tree
        for item in tree.get_children():
            self._collapse_item(tree, item)

    def _collapse_item(self, tree: ttk.Treeview, item: str) -> None:
        tree.item(item, open=False)
        for child in tree.get_children(item):
            self._collapse_item(tree, child)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _show_about(self) -> None:
        messagebox.showinfo('About Easy-LIN', _ABOUT_TEXT)

    def _on_close(self) -> None:
        self._comm_panel.stop()
        self.destroy()
