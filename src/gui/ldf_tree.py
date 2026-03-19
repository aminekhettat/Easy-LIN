"""
LDF Tree View widget.

Displays the contents of an :class:`~src.ldf.parser.LDFFile` in a
hierarchical ``ttk.Treeview``.  Selecting a node fires the
``on_select`` callback with a dict describing the selected item.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.ldf.parser import LDFFile


class LDFTreeView(ttk.Frame):
    """A ttk.Treeview panel that shows an LDFFile structure."""

    def __init__(
        self,
        parent: tk.Widget,
        on_select: Optional[Callable[[dict], None]] = None,
        **kwargs,
    ) -> None:
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
        self._ldf = None
        self._tree.delete(*self._tree.get_children())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Treeview + scrollbars
        self._tree = ttk.Treeview(
            self,
            columns=('value',),
            show='tree headings',
            selectmode='browse',
        )
        self._tree.heading('#0', text='Name', anchor='w')
        self._tree.heading('value', text='Value / Info', anchor='w')
        self._tree.column('#0', width=220, minwidth=120)
        self._tree.column('value', width=260, minwidth=100)

        vsb = ttk.Scrollbar(self, orient='vertical', command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient='horizontal', command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        self._tree.bind('<<TreeviewSelect>>', self._on_tree_select)

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _ins(
        self,
        parent: str,
        text: str,
        value: str = '',
        tag: str = '',
        open_: bool = False,
    ) -> str:
        return self._tree.insert(
            parent, 'end',
            text=text,
            values=(value,),
            tags=(tag,) if tag else (),
            open=open_,
        )

    def _populate(self, ldf: LDFFile) -> None:  # noqa: PLR0912
        tree = self._tree

        # Colour tags
        tree.tag_configure('header', foreground='#1a5276')
        tree.tag_configure('section', foreground='#117a65')
        tree.tag_configure('leaf', foreground='#2c3e50')

        # ── Header ──────────────────────────────────────────────────────
        h = self._ins('', '📄 LDF Header', tag='header', open_=True)
        self._ins(h, 'Protocol version', ldf.protocol_version, 'leaf')
        self._ins(h, 'Language version', ldf.language_version, 'leaf')
        self._ins(h, 'LIN speed', f'{ldf.speed_kbps} kbps', 'leaf')
        if ldf.channel_name:
            self._ins(h, 'Channel name', ldf.channel_name, 'leaf')

        # ── Nodes ────────────────────────────────────────────────────────
        nodes_node = self._ins('', '🔌 Nodes', tag='section', open_=True)
        if ldf.master:
            m = ldf.master
            mn = self._ins(
                nodes_node, f'⭐ {m.name} (Master)',
                f'timebase={m.timebase_ms} ms  jitter={m.jitter_ms} ms',
                'header',
            )
            tree.item(mn, tags=('header',))
        for slave in ldf.slaves:
            self._ins(nodes_node, f'  {slave.name}', 'Slave', 'leaf')

        # ── Signals ──────────────────────────────────────────────────────
        if ldf.signals:
            sig_root = self._ins(
                '', f'📡 Signals  ({len(ldf.signals)})', tag='section', open_=True
            )
            for sig in ldf.signals.values():
                enc = ldf.signal_representations.get(sig.name, '')
                info = (
                    f'{sig.bit_length} bit(s)  '
                    f'init=0x{sig.init_value:X}  '
                    f'pub={sig.publisher}'
                    + (f'  enc={enc}' if enc else '')
                )
                sn = self._ins(sig_root, sig.name, info, 'leaf')
                if sig.subscribers:
                    self._ins(sn, 'Subscribers', ', '.join(sig.subscribers), 'leaf')

        # ── Frames ───────────────────────────────────────────────────────
        if ldf.frames:
            frm_root = self._ins(
                '', f'📦 Frames  ({len(ldf.frames)})', tag='section', open_=True
            )
            for frm in ldf.frames.values():
                fn = self._ins(
                    frm_root,
                    frm.name,
                    f'ID=0x{frm.frame_id:02X}  len={frm.length}  pub={frm.publisher}',
                    'header',
                )
                for fs in frm.signals:
                    self._ins(
                        fn,
                        f'  {fs.signal_name}',
                        f'offset={fs.bit_offset} bit(s)',
                        'leaf',
                    )

        # ── Schedule tables ──────────────────────────────────────────────
        if ldf.schedule_tables:
            sch_root = self._ins(
                '', f'📅 Schedule Tables  ({len(ldf.schedule_tables)})',
                tag='section', open_=False
            )
            for tbl in ldf.schedule_tables.values():
                tn = self._ins(
                    sch_root, tbl.name,
                    f'{len(tbl.entries)} entries', 'header'
                )
                for entry in tbl.entries:
                    self._ins(
                        tn,
                        entry.frame_name,
                        f'delay={entry.delay_ms} ms',
                        'leaf',
                    )

        # ── Signal encoding types ────────────────────────────────────────
        if ldf.encoding_types:
            enc_root = self._ins(
                '', f'🔢 Encoding Types  ({len(ldf.encoding_types)})',
                tag='section', open_=False
            )
            for enc in ldf.encoding_types.values():
                en = self._ins(
                    enc_root, enc.name,
                    f'{len(enc.values)} value(s)', 'header'
                )
                for v in enc.values:
                    if v.kind == 'logical':
                        self._ins(en, f'  0x{v.min_value:X}', v.label, 'leaf')
                    elif v.kind == 'physical':
                        self._ins(
                            en,
                            f'  {v.min_value}..{v.max_value}',
                            f'scale={v.scale}  offset={v.offset}  {v.unit}',
                            'leaf',
                        )
                    else:
                        self._ins(en, f'  {v.kind}', '', 'leaf')

        # ── Node attributes ──────────────────────────────────────────────
        if ldf.node_attributes:
            na_root = self._ins(
                '', f'⚙ Node Attributes  ({len(ldf.node_attributes)})',
                tag='section', open_=False
            )
            for attr in ldf.node_attributes.values():
                an = self._ins(na_root, attr.name, '', 'header')
                if attr.lin_protocol:
                    self._ins(an, 'LIN protocol', attr.lin_protocol, 'leaf')
                if attr.configured_nad:
                    self._ins(
                        an, 'Configured NAD',
                        f'0x{attr.configured_nad:02X}', 'leaf'
                    )

    # ------------------------------------------------------------------
    # Selection callback
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event: tk.Event) -> None:
        if not self._on_select:
            return
        sel = self._tree.selection()
        if not sel:
            return
        item_id = sel[0]
        text = self._tree.item(item_id, 'text').strip()
        values = self._tree.item(item_id, 'values')
        parent_id = self._tree.parent(item_id)
        parent_text = self._tree.item(parent_id, 'text').strip() if parent_id else ''

        info = {
            'id': item_id,
            'text': text,
            'value': values[0] if values else '',
            'parent_text': parent_text,
        }

        # Enrich with parsed data when applicable
        if self._ldf:
            name = text.lstrip('⭐ ').lstrip('  ')
            if name in self._ldf.signals:
                info['type'] = 'signal'
                info['data'] = self._ldf.signals[name]
            elif name in self._ldf.frames:
                info['type'] = 'frame'
                info['data'] = self._ldf.frames[name]
            elif name in self._ldf.schedule_tables:
                info['type'] = 'schedule_table'
                info['data'] = self._ldf.schedule_tables[name]
            elif name in self._ldf.encoding_types:
                info['type'] = 'encoding_type'
                info['data'] = self._ldf.encoding_types[name]

        self._on_select(info)
