"""Presentation helpers for accessible LDF rendering.

This module is UI-framework agnostic so it can be tested independently and used
by different GUI frontends.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ldf_parser import LDFEncodingType, LDFFile, LDFFrame, LDFSignal


@dataclass
class TreeNode:
    """Normalized tree node used by GUI layers."""

    key: str
    label: str
    value: str
    parent_key: str


def build_tree_nodes(ldf: LDFFile) -> list[TreeNode]:
    """Build a deterministic, screen-reader-friendly tree representation."""
    nodes: list[TreeNode] = []

    def add(key: str, label: str, value: str = "", parent_key: str = "") -> None:
        """Append one normalized tree node to the presentation list."""
        nodes.append(TreeNode(key=key, label=label, value=value, parent_key=parent_key))

    add("header", "Header")
    add("header.protocol", "Protocol version", ldf.protocol_version, "header")
    add("header.language", "Language version", ldf.language_version, "header")
    add("header.speed", "Bus speed", f"{ldf.speed} kbps", "header")
    add("header.channel", "Channel", ldf.channel_name or "Not defined", "header")

    add("nodes", "Nodes")
    if ldf.nodes:
        add(
            "nodes.master",
            f"Master: {ldf.nodes.master.name}",
            f"Time base {ldf.nodes.master.time_base} ms, jitter {ldf.nodes.master.jitter} ms",
            "nodes",
        )
        for index, slave in enumerate(ldf.nodes.slaves):
            add(f"nodes.slave.{index}", f"Slave: {slave}", "", "nodes")

    add("signals", "Signals", f"{len(ldf.signals)} signal(s)")
    for sig in ldf.signals:
        add(
            f"signal.{sig.name}",
            sig.name,
            f"{sig.size} bit, publisher {sig.publisher}",
            "signals",
        )

    add("frames", "Frames", f"{len(ldf.frames)} frame(s)")
    for frame in ldf.frames:
        add(
            f"frame.{frame.name}",
            frame.name,
            f"ID 0x{frame.frame_id:02X}, {frame.frame_size} byte(s)",
            "frames",
        )
        for fs in frame.signals:
            add(
                f"frame.{frame.name}.signal.{fs.signal_name}",
                fs.signal_name,
                f"Bit offset {fs.bit_offset}",
                f"frame.{frame.name}",
            )

    add("schedules", "Schedule tables", f"{len(ldf.schedule_tables)} table(s)")
    for table in ldf.schedule_tables:
        add(
            f"schedule.{table.name}",
            table.name,
            f"{len(table.entries)} entries",
            "schedules",
        )

    add("encodings", "Encoding types", f"{len(ldf.encoding_types)} type(s)")
    for enc in ldf.encoding_types:
        add(f"encoding.{enc.name}", enc.name, _encoding_summary(enc), "encodings")

    return nodes


def describe_key(ldf: LDFFile, key: str) -> str:
    """Return a textual explanation suitable for screen reader output."""
    if key.startswith("signal."):
        name = key.split(".", 1)[1]
        sig = ldf.signal(name)
        if sig is None:
            return f"Signal {name} was not found in the parsed file."
        return describe_signal(sig)

    if key.startswith("frame.") and ".signal." not in key:
        name = key.split(".", 1)[1]
        frame = ldf.frame_by_name(name)
        if frame is None:
            return f"Frame {name} was not found in the parsed file."
        return describe_frame(frame, ldf)

    if key.startswith("encoding."):
        name = key.split(".", 1)[1]
        encoding = next((item for item in ldf.encoding_types if item.name == name), None)
        if encoding is None:
            return f"Encoding type {name} was not found."
        return describe_encoding(encoding)

    if key.startswith("schedule."):
        name = key.split(".", 1)[1]
        table = next((item for item in ldf.schedule_tables if item.name == name), None)
        if table is None:
            return f"Schedule table {name} was not found."
        header = f"Schedule table {table.name}. It contains {len(table.entries)} entries."
        details = [
            f"{entry.frame_name} after {entry.delay} milliseconds" for entry in table.entries
        ]
        return header + "\n" + "\n".join(details)

    if key == "header":
        return (
            f"Protocol version {ldf.protocol_version}, language version {ldf.language_version}, "
            f"speed {ldf.speed} kilobits per second."
        )

    return "Select a frame, signal, schedule table, or encoding type to read detailed help."


def describe_signal(sig: LDFSignal) -> str:
    """Describe one signal in plain language for narrated output."""
    subscribers = ", ".join(sig.subscribers) if sig.subscribers else "no subscribers"
    return (
        f"Signal {sig.name}. Size {sig.size} bit. Initial value {sig.init_value}. "
        f"Publisher {sig.publisher}. Subscribers: {subscribers}."
    )


def describe_frame(frame: LDFFrame, ldf: LDFFile) -> str:
    """Describe one frame and its mapped signals in reading order."""
    lines = [
        f"Frame {frame.name}. Identifier 0x{frame.frame_id:02X}. "
        f"Publisher {frame.publisher}. Frame size {frame.frame_size} byte(s)."
    ]
    if not frame.signals:
        lines.append("No signals are mapped to this frame.")
    for sig_ref in sorted(frame.signals, key=lambda item: item.bit_offset):
        signal = ldf.signal(sig_ref.signal_name)
        width = signal.size if signal else "unknown"
        lines.append(
            "Signal "
            f"{sig_ref.signal_name} starts at bit {sig_ref.bit_offset} "
            f"and uses {width} bit(s)."
        )
    return "\n".join(lines)


def describe_encoding(encoding: LDFEncodingType) -> str:
    """Describe one encoding type in screen-reader-friendly text."""
    lines = [f"Encoding type {encoding.name}."]
    for logical in encoding.logical_values:
        lines.append(f"Logical value {logical.signal_value} means {logical.text}.")
    for physical in encoding.physical_ranges:
        lines.append(
            "Physical range "
            f"{physical.min_value} to {physical.max_value}, "
            f"scale {physical.scale}, offset {physical.offset}, unit {physical.unit or 'none'}."
        )
    if encoding.bcd:
        lines.append("BCD format is enabled.")
    if encoding.ascii:
        lines.append("ASCII format is enabled.")
    return "\n".join(lines)


def _encoding_summary(encoding: LDFEncodingType) -> str:
    """Build a short summary string for one encoding node."""
    logical_count = len(encoding.logical_values)
    physical_count = len(encoding.physical_ranges)
    flags: list[str] = []
    if encoding.bcd:
        flags.append("BCD")
    if encoding.ascii:
        flags.append("ASCII")
    suffix = f", formats: {', '.join(flags)}" if flags else ""
    return f"{logical_count} logical, {physical_count} physical{suffix}"

