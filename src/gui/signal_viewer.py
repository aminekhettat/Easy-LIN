"""
Signal / Frame detail viewer panel.

Displays detailed, human-readable information about a tree-selected item
(signal, frame, schedule table, encoding type).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.ldf.parser import (
    LDFFile,
    LDFSignal,
    LDFFrame,
    LDFScheduleTable,
    LDFEncodingType,
)


class DetailViewer(ttk.LabelFrame):
    """Displays detailed information about a selected LDF element."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault('text', 'Details')
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
        self._text.config(state='normal')
        self._text.delete('1.0', tk.END)

        item_type = info.get('type', '')
        data = info.get('data')

        if item_type == 'signal' and isinstance(data, LDFSignal):
            self._show_signal(data)
        elif item_type == 'frame' and isinstance(data, LDFFrame):
            self._show_frame(data)
        elif item_type == 'schedule_table' and isinstance(data, LDFScheduleTable):
            self._show_schedule_table(data)
        elif item_type == 'encoding_type' and isinstance(data, LDFEncodingType):
            self._show_encoding_type(data)
        else:
            self._writeln(info.get('text', ''), tag='title')
            if info.get('value'):
                self._writeln(info['value'])

        self._text.config(state='disabled')

    def clear(self) -> None:
        self._text.config(state='normal')
        self._text.delete('1.0', tk.END)
        self._text.config(state='disabled')
        self._ldf = None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._text = tk.Text(
            self,
            wrap='word',
            state='disabled',
            relief='flat',
            background='#fafafa',
            font=('Segoe UI', 10),
            padx=8,
            pady=6,
        )
        vsb = ttk.Scrollbar(self, orient='vertical', command=self._text.yview)
        self._text.configure(yscrollcommand=vsb.set)

        self._text.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        # Text tags for formatting
        self._text.tag_configure('title', font=('Segoe UI', 11, 'bold'), foreground='#1a5276')
        self._text.tag_configure('section', font=('Segoe UI', 10, 'bold'), foreground='#117a65')
        self._text.tag_configure('key', font=('Segoe UI', 10, 'bold'))
        self._text.tag_configure('value', font=('Segoe UI', 10))
        self._text.tag_configure('mono', font=('Courier New', 9))
        self._text.tag_configure('warn', foreground='#c0392b')

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def _writeln(self, text: str = '', tag: str = 'value') -> None:
        self._text.insert(tk.END, text + '\n', tag)

    def _kv(self, key: str, value: str) -> None:
        self._text.insert(tk.END, f'{key}: ', 'key')
        self._text.insert(tk.END, f'{value}\n', 'value')

    def _show_signal(self, sig: LDFSignal) -> None:
        self._writeln(f'Signal: {sig.name}', 'title')
        self._writeln()
        self._kv('Bit length', str(sig.bit_length))
        self._kv('Initial value', f'0x{sig.init_value:0{(sig.bit_length + 3) // 4}X}  ({sig.init_value})')
        self._kv('Publisher', sig.publisher)
        self._kv('Subscribers', ', '.join(sig.subscribers) if sig.subscribers else '—')

        if self._ldf:
            enc_name = self._ldf.signal_representations.get(sig.name, '')
            if enc_name:
                self._kv('Encoding type', enc_name)
                enc = self._ldf.encoding_types.get(enc_name)
                if enc:
                    self._writeln()
                    self._writeln('Encoding values:', 'section')
                    for v in enc.values:
                        if v.kind == 'logical':
                            self._writeln(
                                f'  0x{v.min_value:X}  →  {v.label}', 'mono'
                            )
                        elif v.kind == 'physical':
                            self._writeln(
                                f'  {v.min_value}..{v.max_value}  '
                                f'(×{v.scale} + {v.offset})'
                                + (f'  [{v.unit}]' if v.unit else ''),
                                'mono',
                            )
                        else:
                            self._writeln(f'  {v.kind}', 'mono')

            # Show frames that include this signal
            frames_using = [
                f for f in self._ldf.frames.values()
                if any(fs.signal_name == sig.name for fs in f.signals)
            ]
            if frames_using:
                self._writeln()
                self._writeln('Used in frames:', 'section')
                for frm in frames_using:
                    offset = next(
                        (fs.bit_offset for fs in frm.signals if fs.signal_name == sig.name),
                        None,
                    )
                    self._writeln(
                        f'  {frm.name}  (ID=0x{frm.frame_id:02X}  offset={offset} bit(s))',
                        'mono',
                    )

    def _show_frame(self, frm: LDFFrame) -> None:
        self._writeln(f'Frame: {frm.name}', 'title')
        self._writeln()
        self._kv('Frame ID', f'0x{frm.frame_id:02X}  ({frm.frame_id})')
        self._kv('Publisher', frm.publisher)
        self._kv('Length', f'{frm.length} byte(s)')
        self._writeln()

        if frm.signals:
            self._writeln('Signal layout:', 'section')
            for fs in sorted(frm.signals, key=lambda x: x.bit_offset):
                sig_detail = ''
                if self._ldf and fs.signal_name in self._ldf.signals:
                    s = self._ldf.signals[fs.signal_name]
                    sig_detail = f'  [{s.bit_length} bit(s)]'
                self._writeln(
                    f'  bit {fs.bit_offset:>3}  {fs.signal_name}{sig_detail}',
                    'mono',
                )

            # Byte layout diagram
            self._writeln()
            self._writeln('Byte layout:', 'section')
            byte_map: list[list[str]] = [
                ['·'] * 8 for _ in range(frm.length)
            ]
            if self._ldf:
                for fs in frm.signals:
                    sig = self._ldf.signals.get(fs.signal_name)
                    if sig is None:
                        continue
                    for bit_idx in range(sig.bit_length):
                        abs_bit = fs.bit_offset + bit_idx
                        byte_i, bit_i = divmod(abs_bit, 8)
                        if byte_i < frm.length:
                            byte_map[byte_i][7 - bit_i] = '█'
            self._writeln('       Bit 7 6 5 4 3 2 1 0', 'mono')
            for i, bits in enumerate(byte_map):
                self._writeln(f'  Byte {i}: {" ".join(bits)}', 'mono')

    def _show_schedule_table(self, tbl: LDFScheduleTable) -> None:
        self._writeln(f'Schedule Table: {tbl.name}', 'title')
        self._writeln()
        self._kv('Entries', str(len(tbl.entries)))
        self._writeln()
        self._writeln('Schedule:', 'section')
        for i, entry in enumerate(tbl.entries):
            self._writeln(
                f'  {i + 1:>3}. {entry.frame_name:<24} delay={entry.delay_ms} ms',
                'mono',
            )

    def _show_encoding_type(self, enc: LDFEncodingType) -> None:
        self._writeln(f'Encoding Type: {enc.name}', 'title')
        self._writeln()
        for v in enc.values:
            if v.kind == 'logical':
                self._writeln(
                    f'  logical   0x{v.min_value:X}  →  "{v.label}"', 'mono'
                )
            elif v.kind == 'physical':
                self._writeln(
                    f'  physical  {v.min_value}..{v.max_value}  '
                    f'scale={v.scale}  offset={v.offset}'
                    + (f'  [{v.unit}]' if v.unit else ''),
                    'mono',
                )
            else:
                self._writeln(f'  {v.kind}', 'mono')

        if self._ldf:
            sigs = [
                s for s, e in self._ldf.signal_representations.items()
                if e == enc.name
            ]
            if sigs:
                self._writeln()
                self._kv('Used by signals', ', '.join(sigs))
