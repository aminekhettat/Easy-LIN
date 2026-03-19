"""LDF viewer widget for the preserved PyQt frontend.

Displays the parsed content of an LDF file across multiple sub-tabs covering
protocol metadata, signals, frames, schedules, and encodings.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from PyQt5.QtWidgets import (
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QGroupBox,
    QHeaderView,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from src.ldf_parser import LDFFile


# ---------------------------------------------------------------------------
# Helper: create read-only table item
# ---------------------------------------------------------------------------


def _item(
    text: str, align: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignVCenter
) -> QTableWidgetItem:
    """Create a read-only table item with the requested alignment."""
    it = QTableWidgetItem(str(text))
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    it.setTextAlignment(align)
    return it


def _bold(text: str) -> QTableWidgetItem:
    """Create a read-only table item with bold text."""
    it = _item(text)
    f = it.font()
    f.setBold(True)
    it.setFont(f)
    return it


# ---------------------------------------------------------------------------
# Overview tab
# ---------------------------------------------------------------------------


class _OverviewTab(QWidget):
    """Overview tab showing protocol metadata, nodes, and summary counts."""

    def __init__(self, ldf: LDFFile, parent=None):
        """Build the overview tab showing network metadata and node summary."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # --- Protocol info ---
        proto_box = QGroupBox("Protocol Information")
        proto_layout = QVBoxLayout(proto_box)
        table = QTableWidget(4, 2)
        table.setHorizontalHeaderLabels(["Property", "Value"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        rows = [
            ("LIN Protocol Version", ldf.protocol_version),
            ("LIN Language Version", ldf.language_version),
            ("Bus Speed", f"{ldf.speed} kbps"),
            ("Channel Name", ldf.channel_name or "—"),
        ]
        for i, (k, v) in enumerate(rows):
            table.setItem(i, 0, _bold(k))
            table.setItem(i, 1, _item(v))
        table.setFixedHeight(
            table.rowHeight(0) * 4 + table.horizontalHeader().height() + 4
        )
        proto_layout.addWidget(table)
        layout.addWidget(proto_box)

        # --- Nodes ---
        if ldf.nodes:
            node_box = QGroupBox("Nodes")
            node_layout = QVBoxLayout(node_box)
            tree = QTreeWidget()
            tree.setHeaderLabels(["Name", "Role", "Details"])
            tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            tree.setAlternatingRowColors(True)
            m = ldf.nodes.master
            master_item = QTreeWidgetItem(
                [
                    m.name,
                    "Master",
                    f"Time base: {m.time_base} ms  |  Jitter: {m.jitter} ms",
                ]
            )
            master_item.setForeground(0, QColor("#005B9F"))
            tree.addTopLevelItem(master_item)
            for slave in ldf.nodes.slaves:
                slave_item = QTreeWidgetItem([slave, "Slave", ""])
                slave_item.setForeground(0, QColor("#3A7D44"))
                tree.addTopLevelItem(slave_item)
            tree.expandAll()
            node_layout.addWidget(tree)
            layout.addWidget(node_box)

        # --- Summary numbers ---
        stats_box = QGroupBox("Network Summary")
        stats_layout = QHBoxLayout(stats_box)
        for label, value in [
            ("Signals", str(len(ldf.signals))),
            ("Frames", str(len(ldf.frames))),
            ("Schedule Tables", str(len(ldf.schedule_tables))),
            ("Encoding Types", str(len(ldf.encoding_types))),
        ]:
            cell = QWidget()
            cell_vl = QVBoxLayout(cell)
            cell_vl.setContentsMargins(8, 4, 8, 4)
            num_label = QLabel(value)
            num_font = QFont()
            num_font.setPointSize(20)
            num_font.setBold(True)
            num_label.setFont(num_font)
            num_label.setAlignment(Qt.AlignCenter)
            num_label.setStyleSheet("color: #005B9F;")
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignCenter)
            cell_vl.addWidget(num_label)
            cell_vl.addWidget(lbl)
            stats_layout.addWidget(cell)
        layout.addWidget(stats_box)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Signals tab
# ---------------------------------------------------------------------------


class _SignalsTab(QWidget):
    """Signals tab showing the flat signal table."""

    def __init__(self, ldf: LDFFile, parent=None):
        """Build the signals table tab."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        cols = ["Signal Name", "Size (bits)", "Init Value", "Publisher", "Subscribers"]
        table = QTableWidget(len(ldf.signals), len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)

        for row, sig in enumerate(ldf.signals):
            table.setItem(row, 0, _item(sig.name))
            table.setItem(
                row, 1, _item(str(sig.size), Qt.AlignCenter | Qt.AlignVCenter)
            )
            table.setItem(
                row,
                2,
                _item(
                    f"0x{sig.init_value:X} ({sig.init_value})",
                    Qt.AlignCenter | Qt.AlignVCenter,
                ),
            )
            table.setItem(row, 3, _item(sig.publisher))
            table.setItem(row, 4, _item(", ".join(sig.subscribers)))

        layout.addWidget(table)


# ---------------------------------------------------------------------------
# Frames tab
# ---------------------------------------------------------------------------


class _FramesTab(QWidget):
    """Frames tab showing frames and their nested signal placements."""

    def __init__(self, ldf: LDFFile, parent=None):
        """Build the frames tab and nested signal tree."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        tree = QTreeWidget()
        tree.setHeaderLabels(
            ["Name / Signal", "Frame ID", "Publisher", "Size", "Bit Offset"]
        )
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            tree.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        tree.setAlternatingRowColors(True)

        for frame in ldf.frames:
            top = QTreeWidgetItem(
                [
                    frame.name,
                    f"0x{frame.frame_id:02X}  ({frame.frame_id})",
                    frame.publisher,
                    f"{frame.frame_size} byte{'s' if frame.frame_size != 1 else ''}",
                    "",
                ]
            )
            top.setFont(0, _bold_font())
            top.setBackground(0, QColor("#EEF4FB"))
            for sig_ref in frame.signals:
                child = QTreeWidgetItem(
                    [
                        f"  ↳ {sig_ref.signal_name}",
                        "",
                        "",
                        "",
                        str(sig_ref.bit_offset),
                    ]
                )
                child.setForeground(0, QColor("#3A7D44"))
                top.addChild(child)
            tree.addTopLevelItem(top)

        tree.expandAll()
        layout.addWidget(tree)


# ---------------------------------------------------------------------------
# Schedules tab
# ---------------------------------------------------------------------------


class _SchedulesTab(QWidget):
    """Schedules tab showing schedule tables and referenced frames."""

    def __init__(self, ldf: LDFFile, parent=None):
        """Build the schedule tables tab."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Schedule / Frame", "Delay (ms)", "Frame ID"])
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2):
            tree.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        tree.setAlternatingRowColors(True)

        for sched in ldf.schedule_tables:
            top = QTreeWidgetItem([sched.name, "", ""])
            top.setFont(0, _bold_font())
            top.setBackground(0, QColor("#EEF4FB"))
            for entry in sched.entries:
                frame = ldf.frame_by_name(entry.frame_name)
                fid = f"0x{frame.frame_id:02X}" if frame else "—"
                child = QTreeWidgetItem(
                    [
                        f"  ↳ {entry.frame_name}",
                        str(entry.delay),
                        fid,
                    ]
                )
                top.addChild(child)
            tree.addTopLevelItem(top)

        tree.expandAll()
        layout.addWidget(tree)


# ---------------------------------------------------------------------------
# Encodings tab
# ---------------------------------------------------------------------------


class _EncodingsTab(QWidget):
    """Encodings tab showing encoding types and signal representations."""

    def __init__(self, ldf: LDFFile, parent=None):
        """Build the encoding types and signal representation tab."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Encoding Type / Entry", "Details"])
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        tree.setAlternatingRowColors(True)

        for enc in ldf.encoding_types:
            top = QTreeWidgetItem([enc.name, ""])
            top.setFont(0, _bold_font())
            top.setBackground(0, QColor("#EEF4FB"))
            for lv in enc.logical_values:
                child = QTreeWidgetItem(
                    [
                        f"  logical: {lv.signal_value}",
                        f'"{lv.text}"',
                    ]
                )
                child.setForeground(0, QColor("#8B4513"))
                top.addChild(child)
            for pr in enc.physical_ranges:
                child = QTreeWidgetItem(
                    [
                        f"  physical: [{pr.min_value}–{pr.max_value}]",
                        f"× {pr.scale} + {pr.offset}  [{pr.unit}]",
                    ]
                )
                child.setForeground(0, QColor("#005B9F"))
                top.addChild(child)
            if enc.bcd:
                top.addChild(QTreeWidgetItem(["  BCD", ""]))
            if enc.ascii:
                top.addChild(QTreeWidgetItem(["  ASCII", ""]))
            tree.addTopLevelItem(top)

        # Signal representations
        if ldf.signal_representations:
            sep = QTreeWidgetItem(["── Signal Representations ──", ""])
            sep.setFlags(Qt.NoItemFlags)
            tree.addTopLevelItem(sep)
            for rep in ldf.signal_representations:
                top = QTreeWidgetItem([rep.encoding_type, ""])
                top.setFont(0, _bold_font())
                for sig_name in rep.signals:
                    top.addChild(QTreeWidgetItem([f"  ↳ {sig_name}", ""]))
                tree.addTopLevelItem(top)

        tree.expandAll()
        layout.addWidget(tree)


# ---------------------------------------------------------------------------
# Public widget
# ---------------------------------------------------------------------------


def _bold_font() -> QFont:
    """Return a reusable bold font for section headers."""
    f = QFont()
    f.setBold(True)
    return f


class LDFViewer(QTabWidget):
    """
    A tab widget that displays every section of a parsed :class:`LDFFile`.

    Usage::

        viewer = LDFViewer(ldf)
        main_window.setCentralWidget(viewer)
    """

    def __init__(self, ldf: LDFFile, parent=None):
        """Initialize the tab widget for a parsed LDF file."""
        super().__init__(parent)
        self._ldf = ldf
        self._build_tabs()

    def _build_tabs(self) -> None:
        """Populate tabs from the currently loaded parsed LDF."""
        ldf = self._ldf
        self.addTab(_OverviewTab(ldf), "📋 Overview")
        self.addTab(_SignalsTab(ldf), f"〜 Signals ({len(ldf.signals)})")
        self.addTab(_FramesTab(ldf), f"▤ Frames ({len(ldf.frames)})")
        self.addTab(_SchedulesTab(ldf), f"⏱ Schedules ({len(ldf.schedule_tables)})")
        if ldf.encoding_types or ldf.signal_representations:
            self.addTab(_EncodingsTab(ldf), "⚙ Encodings")

    def refresh(self, ldf: LDFFile) -> None:
        """Reload the viewer with a new LDF file."""
        while self.count():
            self.removeTab(0)
        self._ldf = ldf
        self._build_tabs()
