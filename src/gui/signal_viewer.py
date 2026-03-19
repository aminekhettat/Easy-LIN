"""
Accessible detail viewer panel.

Displays detailed human-readable information about a selected tree item.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.ldf_parser import LDFFile
from src.ldf_presenter import describe_key


class DetailViewer(ttk.LabelFrame):
    """Displays detailed information about a selected LDF element."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("text", "Details")
        super().__init__(parent, **kwargs)
        self._ldf: Optional[LDFFile] = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_ldf(self, ldf: LDFFile) -> None:
        self._ldf = ldf

    def show(self, info: dict) -> None:
        """Display information for the item described by *info*."""
        self._text.config(state="normal")
        self._text.delete("1.0", tk.END)

        item_key = info.get("key", "")
        if self._ldf and item_key:
            description = describe_key(self._ldf, item_key)
            self._writeln(info.get("text", ""), tag="title")
            self._writeln()
            self._writeln(description)
        else:
            self._writeln(info.get("text", ""), tag="title")
            if info.get("value"):
                self._writeln(info["value"])

        self._text.config(state="disabled")

    def clear(self) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.config(state="disabled")
        self._ldf = None

    def focus_text(self) -> None:
        """Move keyboard focus to the detail text area."""
        self._text.focus_set()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._text = tk.Text(
            self,
            wrap="word",
            state="disabled",
            relief="flat",
            background="#fafafa",
            font=("Segoe UI", 10),
            padx=8,
            pady=6,
        )
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)

        self._text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Text tags for formatting
        self._text.tag_configure(
            "title", font=("Segoe UI", 11, "bold"), foreground="#1a5276"
        )
        self._text.tag_configure(
            "section", font=("Segoe UI", 10, "bold"), foreground="#117a65"
        )
        self._text.tag_configure("key", font=("Segoe UI", 10, "bold"))
        self._text.tag_configure("value", font=("Segoe UI", 10))
        self._text.tag_configure("mono", font=("Courier New", 9))
        self._text.tag_configure("warn", foreground="#c0392b")

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def _writeln(self, text: str = "", tag: str = "value") -> None:
        self._text.insert(tk.END, text + "\n", tag)

    def _kv(self, key: str, value: str) -> None:
        self._text.insert(tk.END, f"{key}: ", "key")
        self._text.insert(tk.END, f"{value}\n", "value")
