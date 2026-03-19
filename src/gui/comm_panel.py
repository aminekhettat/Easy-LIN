"""LIN communication panel.

Provides UI controls for connecting to a LIN channel, sending frames, and
monitoring received or transmitted traffic.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from src.communication.vector_lin import VectorLINBus, LINFrame, LINError
from src.ldf_parser import LDFFile

logger = logging.getLogger(__name__)

# Maximum number of log rows kept in the UI table
_MAX_LOG_ROWS = 500


class CommunicationPanel(ttk.LabelFrame):
    """LIN communication control and monitor panel."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        """Initialize the communication panel state and child widgets."""
        kwargs.setdefault("text", "LIN Communication  (Vector CAN)")
        super().__init__(parent, **kwargs)
        self._ldf: Optional[LDFFile] = None
        self._bus: Optional[VectorLINBus] = None
        self._log_lock = threading.Lock()
        self._row_count = 0
        self._build_ui()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_ldf(self, ldf: LDFFile) -> None:
        """Update the known LDF so frame names can be shown in the log."""
        self._ldf = ldf
        self._refresh_frame_combo()

    def stop(self) -> None:
        """Disconnect if connected (call on application close)."""
        if self._bus and self._bus.is_connected:
            self._bus.stop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the connection bar, log table, and send controls."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_connection_bar()
        self._build_log_table()
        self._build_send_bar()

    def _build_connection_bar(self) -> None:
        """Create the connection controls and status area."""
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))

        ttk.Label(bar, text="Channel:").pack(side="left")
        self._channel_var = tk.IntVar(value=0)
        self._channel_spin = ttk.Spinbox(
            bar, from_=0, to=15, width=4, textvariable=self._channel_var
        )
        self._channel_spin.pack(side="left", padx=(2, 10))

        ttk.Label(bar, text="Bitrate (bps):").pack(side="left")
        self._bitrate_var = tk.StringVar(value="19200")
        bitrate_combo = ttk.Combobox(
            bar,
            textvariable=self._bitrate_var,
            values=["9600", "10417", "19200", "20000"],
            width=8,
            state="readonly",
        )
        bitrate_combo.pack(side="left", padx=(2, 10))

        self._connect_btn = ttk.Button(bar, text="Connect", command=self._on_connect)
        self._connect_btn.pack(side="left", padx=4)

        self._disconnect_btn = ttk.Button(
            bar, text="Disconnect", command=self._on_disconnect, state="disabled"
        )
        self._disconnect_btn.pack(side="left", padx=4)

        self._status_var = tk.StringVar(value="Disconnected")
        self._status_label = ttk.Label(
            bar, textvariable=self._status_var, foreground="#c0392b"
        )
        self._status_label.pack(side="left", padx=12)

        ttk.Button(bar, text="Clear Log", command=self._clear_log).pack(
            side="right", padx=4
        )

    def _build_log_table(self) -> None:
        """Create the scrolling traffic log table."""
        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("#", "Time", "Dir", "ID", "Data", "Name")
        self._log_tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        col_widths = {
            "#": 50,
            "Time": 100,
            "Dir": 40,
            "ID": 60,
            "Data": 200,
            "Name": 140,
        }
        for col in cols:
            self._log_tree.heading(col, text=col)
            self._log_tree.column(col, width=col_widths.get(col, 80), anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._log_tree.yview)
        self._log_tree.configure(yscrollcommand=vsb.set)

        self._log_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Colour tags for RX / TX / Error
        self._log_tree.tag_configure("TX", foreground="#1a5276")
        self._log_tree.tag_configure("RX", foreground="#117a65")
        self._log_tree.tag_configure("ERR", foreground="#c0392b")

    def _build_send_bar(self) -> None:
        """Create the manual frame transmission controls."""
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))

        ttk.Label(bar, text="Frame:").pack(side="left")
        self._send_frame_var = tk.StringVar()
        self._send_frame_combo = ttk.Combobox(
            bar, textvariable=self._send_frame_var, width=20, state="readonly"
        )
        self._send_frame_combo.pack(side="left", padx=(2, 10))
        self._send_frame_combo.bind("<<ComboboxSelected>>", self._on_frame_selected)

        ttk.Label(bar, text="  ID (hex):").pack(side="left")
        self._send_id_var = tk.StringVar(value="01")
        ttk.Entry(bar, textvariable=self._send_id_var, width=6).pack(
            side="left", padx=(2, 10)
        )

        ttk.Label(bar, text="Data (hex bytes):").pack(side="left")
        self._send_data_var = tk.StringVar(value="00 00 00 00")
        ttk.Entry(bar, textvariable=self._send_data_var, width=28).pack(
            side="left", padx=(2, 10)
        )

        self._send_btn = ttk.Button(
            bar, text="Send Frame", command=self._on_send, state="disabled"
        )
        self._send_btn.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_frame_combo(self) -> None:
        """Populate the frame dropdown from the currently loaded LDF."""
        names = []
        if self._ldf:
            names = sorted(
                f"{frm.name}  (0x{frm.frame_id:02X})" for frm in self._ldf.frames
            )
        self._send_frame_combo["values"] = names

    def _frame_name_for_id(self, frame_id: int) -> str:
        """Resolve a frame identifier to its LDF name when available."""
        if self._ldf:
            for frm in self._ldf.frames:
                if frm.frame_id == frame_id:
                    return frm.name
        return ""

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        """Connect to the selected Vector or simulation transport."""
        channel = self._channel_var.get()
        bitrate = int(self._bitrate_var.get())
        self._bus = VectorLINBus(channel=channel, bitrate=bitrate)
        self._bus.add_rx_callback(self._on_rx_frame)
        self._bus.add_tx_callback(self._on_tx_frame)
        try:
            self._bus.start()
        except Exception as exc:
            messagebox.showerror("Connection error", str(exc))
            return

        self._connect_btn.config(state="disabled")
        self._disconnect_btn.config(state="normal")
        self._send_btn.config(state="normal")
        if self._bus.is_simulation:
            self._status_var.set("Simulation mode active. No Vector hardware detected.")
            self._status_label.config(foreground="#d68910")
        else:
            self._status_var.set(f"Connected  ch={channel}  {bitrate} bps")
            self._status_label.config(foreground="#117a65")

    def _on_disconnect(self) -> None:
        """Disconnect the active transport and reset the widget state."""
        if self._bus:
            self._bus.stop()
            self._bus = None
        self._connect_btn.config(state="normal")
        self._disconnect_btn.config(state="disabled")
        self._send_btn.config(state="disabled")
        self._status_var.set("Disconnected")
        self._status_label.config(foreground="#c0392b")

    def _on_frame_selected(self, _event: tk.Event) -> None:
        """Pre-fill ID field when a frame is chosen from the dropdown."""
        if not self._ldf:
            return
        sel = self._send_frame_var.get()
        # Parse the '0xNN' part from the combo text
        import re

        m = re.search(r"0x([0-9A-Fa-f]+)", sel)
        if m:
            self._send_id_var.set(m.group(1).upper())
            # Pre-fill data with zeros matching the frame length
            frame_name = sel.split("  ")[0]
            frame = self._ldf.frame_by_name(frame_name)
            if frame:
                self._send_data_var.set(" ".join(["00"] * frame.frame_size))

    def _on_send(self) -> None:
        """Parse user-entered frame data and transmit it on the bus."""
        if not self._bus or not self._bus.is_connected:
            messagebox.showwarning("Not connected", "Please connect first.")
            return
        try:
            frame_id = int(self._send_id_var.get().strip(), 16)
            raw_data = self._send_data_var.get().strip()
            data = bytes(int(b, 16) for b in raw_data.split() if b)
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        try:
            self._bus.send_frame(LINFrame(frame_id=frame_id, data=data))
        except LINError as exc:
            messagebox.showerror("Send error", str(exc))

    def _on_rx_frame(self, frame: LINFrame) -> None:
        """Handle a received frame notification."""
        self._log_frame(frame)

    def _on_tx_frame(self, frame: LINFrame) -> None:
        """Handle a transmitted frame notification."""
        self._log_frame(frame)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def _log_frame(self, frame: LINFrame) -> None:
        """Append a frame to the log table (thread-safe)."""
        self.after(0, self._append_log_row, frame)

    def _append_log_row(self, frame: LINFrame) -> None:
        """Insert one formatted frame row into the visible traffic log."""
        with self._log_lock:
            self._row_count += 1
            row_num = self._row_count

        ts = time.strftime("%H:%M:%S", time.localtime(frame.timestamp))
        ms = int((frame.timestamp % 1) * 1000)
        time_str = f"{ts}.{ms:03d}"
        name = self._frame_name_for_id(frame.frame_id)
        tag = "ERR" if frame.is_error else frame.direction

        values = (
            row_num,
            time_str,
            frame.direction,
            f"0x{frame.frame_id:02X}",
            frame.data_hex,
            name,
        )
        self._log_tree.insert("", "end", values=values, tags=(tag,))

        # Trim old rows
        children = self._log_tree.get_children()
        if len(children) > _MAX_LOG_ROWS:
            self._log_tree.delete(children[0])

        # Auto-scroll
        self._log_tree.yview_moveto(1.0)

    def _clear_log(self) -> None:
        """Remove all rows from the traffic log and reset numbering."""
        self._log_tree.delete(*self._log_tree.get_children())
        with self._log_lock:
            self._row_count = 0
