"""LDF tree view widget.

Displays the contents of an :class:`~src.ldf_parser.LDFFile` in a
hierarchical ``ttk.Treeview``. Selecting a node fires the ``on_select``
callback with a dict describing the selected item.

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

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.ldf_parser import LDFFile
from src.ldf_presenter import build_tree_nodes


class LDFTreeView(ttk.Frame):
    """A ttk.Treeview panel that shows an LDFFile structure."""

    def __init__(
        self,
        parent: tk.Widget,
        on_select: Optional[Callable[[dict], None]] = None,
        **kwargs,
    ) -> None:
        """Initialize the tree view and optional selection callback."""
        super().__init__(parent, **kwargs)
        self._on_select = on_select
        self._ldf: Optional[LDFFile] = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(self, ldf: LDFFile) -> None:
        """Populate the tree from *ldf*."""
        self._ldf = ldf
        self._tree.delete(*self._tree.get_children())
        self._populate(ldf)

    def clear(self) -> None:
        """Remove every tree item and forget the current LDF reference."""
        self._ldf = None
        self._tree.delete(*self._tree.get_children())

    def focus_tree(self) -> None:
        """Move keyboard focus to the tree for screen reader navigation."""
        self._tree.focus_set()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the tree widget and its scrollbars."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Treeview + scrollbars
        self._tree = ttk.Treeview(
            self,
            columns=("value", "key"),
            show="tree headings",
            selectmode="browse",
        )
        self._tree.heading("#0", text="Name", anchor="w")
        self._tree.heading("value", text="Value / Info", anchor="w")
        self._tree.heading("key", text="Key", anchor="w")
        self._tree.column("#0", width=220, minwidth=120)
        self._tree.column("value", width=260, minwidth=100)
        self._tree.column("key", width=1, stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _ins(
        self,
        parent: str,
        text: str,
        value: str = "",
        tag: str = "",
        open_: bool = False,
    ) -> str:
        """Insert one item into the tree widget."""
        return self._tree.insert(
            parent,
            "end",
            text=text,
            values=(value,),
            tags=(tag,) if tag else (),
            open=open_,
        )

    def _populate(self, ldf: LDFFile) -> None:
        """Render presenter-provided nodes into the tree widget."""
        tree = self._tree
        tree.tag_configure("section", foreground="#123a59")
        tree.tag_configure("leaf", foreground="#1d2731")

        id_map: dict[str, str] = {}
        for node in build_tree_nodes(ldf):
            parent = id_map.get(node.parent_key, "")
            item_id = tree.insert(
                parent,
                "end",
                text=node.label,
                values=(node.value, node.key),
                tags=("section",) if not node.parent_key else ("leaf",),
                open=node.parent_key == "",
            )
            id_map[node.key] = item_id

    # ------------------------------------------------------------------
    # Selection callback
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event: tk.Event) -> None:
        """Forward the selected tree item to the external callback."""
        if not self._on_select:
            return
        sel = self._tree.selection()
        if not sel:
            return
        item_id = sel[0]
        text = self._tree.item(item_id, "text").strip()
        values = self._tree.item(item_id, "values")
        parent_id = self._tree.parent(item_id)
        parent_text = self._tree.item(parent_id, "text").strip() if parent_id else ""

        info = {
            "id": item_id,
            "text": text,
            "value": values[0] if values else "",
            "key": values[1] if len(values) > 1 else "",
            "parent_text": parent_text,
        }

        self._on_select(info)

