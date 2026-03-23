"""LDF consistency checks based on LIN/LDF common rules.

The checks are intentionally practical and strict enough for engineering use,
while tolerating vendor-specific formatting accepted by the parser.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

from src.ldf_parser import LDFFile, LDFParseError, parse_ldf


@dataclass
class ConsistencyIssue:
    """A single consistency issue."""

    severity: str  # "error" or "warning"
    code: str
    message: str


@dataclass
class LDFConsistencyReport:
    """Validation report for one LDF file."""

    path: str
    parsed: bool
    issues: List[ConsistencyIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Return the number of error-severity issues in the report."""
        return sum(1 for item in self.issues if item.severity == "error")

    @property
    def warning_count(self) -> int:
        """Return the number of warning-severity issues in the report."""
        return sum(1 for item in self.issues if item.severity == "warning")

    @property
    def is_consistent(self) -> bool:
        """Return ``True`` when parsing succeeded and no errors were found."""
        return self.parsed and self.error_count == 0


def validate_ldf_file(path: str) -> LDFConsistencyReport:
    """Parse and validate one LDF file."""
    report = LDFConsistencyReport(path=path, parsed=False)
    try:
        ldf = parse_ldf(path)
    except FileNotFoundError as exc:
        report.issues.append(ConsistencyIssue("error", "FILE_NOT_FOUND", f"File not found: {exc}"))
        return report
    except LDFParseError as exc:
        report.issues.append(ConsistencyIssue("error", "PARSE_ERROR", f"LDF parse error: {exc}"))
        return report

    report.parsed = True
    report.issues.extend(validate_ldf(ldf))
    return report


def validate_ldf(ldf: LDFFile) -> List[ConsistencyIssue]:
    """Validate logical consistency of a parsed LDF object."""
    issues: List[ConsistencyIssue] = []

    def error(code: str, message: str) -> None:
        """Record an error-level issue."""
        issues.append(ConsistencyIssue("error", code, message))

    def warning(code: str, message: str) -> None:
        """Record a warning-level issue."""
        issues.append(ConsistencyIssue("warning", code, message))

    # Global checks
    if not ldf.protocol_version:
        warning("GLOBAL_PROTOCOL_MISSING", "LIN_protocol_version is missing.")
    if not ldf.language_version:
        warning("GLOBAL_LANGUAGE_MISSING", "LIN_language_version is missing.")
    if not 1.0 <= ldf.speed <= 20.0:
        error("GLOBAL_SPEED_RANGE", f"LIN_speed {ldf.speed} kbps is outside 1..20 kbps.")

    # Nodes
    declared_nodes: Set[str] = set()
    if ldf.nodes is None:
        error("NODES_MISSING", "Nodes section is missing.")
    else:
        master_name = ldf.nodes.master.name
        if not master_name:
            error("MASTER_MISSING", "Master node name is missing.")
        declared_nodes.add(master_name)

        slave_seen: Set[str] = set()
        for slave in ldf.nodes.slaves:
            if slave == master_name:
                error("NODE_DUP_MASTER", f"Slave '{slave}' duplicates the master node.")
            if slave in slave_seen:
                error("NODE_DUP_SLAVE", f"Duplicate slave node '{slave}'.")
            slave_seen.add(slave)
            declared_nodes.add(slave)

    # Signals
    signal_by_name: Dict[str, object] = {}
    for sig in ldf.signals:
        if sig.name in signal_by_name:
            error("SIGNAL_DUP_NAME", f"Duplicate signal name '{sig.name}'.")
            continue
        signal_by_name[sig.name] = sig

        if sig.size < 1 or sig.size > 64:
            error(
                "SIGNAL_SIZE_RANGE",
                f"Signal '{sig.name}' size {sig.size} is outside 1..64 bits.",
            )

        max_value = (1 << sig.size) - 1 if sig.size < 63 else None
        if sig.init_value < 0:
            error(
                "SIGNAL_INIT_NEGATIVE",
                f"Signal '{sig.name}' has negative init value {sig.init_value}.",
            )
        elif max_value is not None and sig.init_value > max_value:
            error(
                "SIGNAL_INIT_RANGE",
                f"Signal '{sig.name}' init value {sig.init_value} exceeds {max_value} for {sig.size} bits.",
            )

        if declared_nodes and sig.publisher not in declared_nodes:
            error(
                "SIGNAL_PUBLISHER_UNKNOWN",
                f"Signal '{sig.name}' publisher '{sig.publisher}' is not a declared node.",
            )
        for sub in sig.subscribers:
            if declared_nodes and sub not in declared_nodes:
                error(
                    "SIGNAL_SUBSCRIBER_UNKNOWN",
                    f"Signal '{sig.name}' subscriber '{sub}' is not a declared node.",
                )

    # Frames
    frame_name_seen: Set[str] = set()
    frame_id_seen: Dict[int, str] = {}
    used_signals: Set[str] = set()

    for frame in ldf.frames:
        if frame.name in frame_name_seen:
            error("FRAME_DUP_NAME", f"Duplicate frame name '{frame.name}'.")
        frame_name_seen.add(frame.name)

        if frame.frame_id < 0 or frame.frame_id > 63:
            error(
                "FRAME_ID_RANGE",
                f"Frame '{frame.name}' ID {frame.frame_id} is outside LIN 6-bit range 0..63.",
            )
        elif frame.frame_id == 63:
            warning(
                "FRAME_ID_RESERVED",
                f"Frame '{frame.name}' uses ID 63 (reserved in LIN 2.x networks).",
            )

        if frame.frame_id in frame_id_seen:
            other = frame_id_seen[frame.frame_id]
            error(
                "FRAME_ID_DUP",
                f"Frame ID {frame.frame_id} is used by both '{other}' and '{frame.name}'.",
            )
        else:
            frame_id_seen[frame.frame_id] = frame.name

        if frame.frame_size < 1 or frame.frame_size > 8:
            error(
                "FRAME_SIZE_RANGE",
                f"Frame '{frame.name}' size {frame.frame_size} is outside 1..8 bytes.",
            )

        if frame.frame_id in (60, 61) and frame.frame_size != 8:
            error(
                "FRAME_DIAG_SIZE",
                f"Diagnostic frame '{frame.name}' (ID {frame.frame_id}) must be 8 bytes.",
            )

        if declared_nodes and frame.publisher not in declared_nodes:
            error(
                "FRAME_PUBLISHER_UNKNOWN",
                f"Frame '{frame.name}' publisher '{frame.publisher}' is not a declared node.",
            )

        bit_capacity = frame.frame_size * 8
        occupied = [False] * max(bit_capacity, 0)
        signal_name_seen_in_frame: Set[str] = set()

        for ref in frame.signals:
            if ref.signal_name in signal_name_seen_in_frame:
                warning(
                    "FRAME_SIGNAL_DUP_REF",
                    f"Frame '{frame.name}' references signal '{ref.signal_name}' multiple times.",
                )
            signal_name_seen_in_frame.add(ref.signal_name)

            sig = signal_by_name.get(ref.signal_name)
            if sig is None:
                error(
                    "FRAME_SIGNAL_UNKNOWN",
                    f"Frame '{frame.name}' references unknown signal '{ref.signal_name}'.",
                )
                continue

            used_signals.add(ref.signal_name)

            if ref.bit_offset < 0:
                error(
                    "FRAME_SIGNAL_OFFSET_NEGATIVE",
                    f"Frame '{frame.name}' signal '{ref.signal_name}' has negative bit offset {ref.bit_offset}.",
                )
                continue

            end_bit = ref.bit_offset + sig.size
            if end_bit > bit_capacity:
                error(
                    "FRAME_SIGNAL_FIT",
                    f"Frame '{frame.name}' signal '{ref.signal_name}' exceeds frame size ({end_bit}>{bit_capacity} bits).",
                )
                continue

            for bit in range(ref.bit_offset, end_bit):
                if occupied[bit]:
                    error(
                        "FRAME_SIGNAL_OVERLAP",
                        f"Frame '{frame.name}' has overlapping signals around bit {bit}.",
                    )
                    break
            else:
                for bit in range(ref.bit_offset, end_bit):
                    occupied[bit] = True

    for sig in ldf.signals:
        if sig.name not in used_signals:
            warning(
                "SIGNAL_UNUSED",
                f"Signal '{sig.name}' is defined but not placed in any frame.",
            )

    # Schedule tables
    schedule_names: Set[str] = set()
    frame_names = {frame.name for frame in ldf.frames}
    time_base = ldf.nodes.master.time_base if ldf.nodes else None
    allowed_schedule_commands = {
        "AssignNAD",
        "ConditionalChangeNAD",
        "DataDump",
        "FreeFormat",
        "AssignFrameId",
        "AssignFrameIdRange",
        "MasterReq",
        "SlaveResp",
    }

    for table in ldf.schedule_tables:
        if table.name in schedule_names:
            error("SCHEDULE_DUP_NAME", f"Duplicate schedule table '{table.name}'.")
        schedule_names.add(table.name)

        for entry in table.entries:
            if entry.delay <= 0:
                error(
                    "SCHEDULE_DELAY_POSITIVE",
                    f"Schedule '{table.name}' entry '{entry.frame_name}' has non-positive delay {entry.delay} ms.",
                )
            if (
                time_base is not None
                and time_base > 0
                and abs((entry.delay / time_base) - round(entry.delay / time_base)) > 1e-6
            ):
                warning(
                    "SCHEDULE_DELAY_MULTIPLE",
                    f"Schedule '{table.name}' delay {entry.delay} ms is not an integer multiple of time base {time_base} ms.",
                )

            if (
                entry.frame_name not in frame_names
                and entry.frame_name not in allowed_schedule_commands
            ):
                error(
                    "SCHEDULE_FRAME_UNKNOWN",
                    f"Schedule '{table.name}' references unknown frame/command '{entry.frame_name}'.",
                )

    # Encodings
    encoding_names: Set[str] = set()
    for encoding in ldf.encoding_types:
        if encoding.name in encoding_names:
            error("ENCODING_DUP_NAME", f"Duplicate encoding type '{encoding.name}'.")
        encoding_names.add(encoding.name)

        logical_values_seen: Set[int] = set()
        for item in encoding.logical_values:
            if item.signal_value in logical_values_seen:
                warning(
                    "ENCODING_LOGICAL_DUP",
                    f"Encoding '{encoding.name}' contains duplicated logical value {item.signal_value}.",
                )
            logical_values_seen.add(item.signal_value)

        for item in encoding.physical_ranges:
            if item.min_value > item.max_value:
                error(
                    "ENCODING_RANGE_ORDER",
                    f"Encoding '{encoding.name}' has invalid physical range {item.min_value}..{item.max_value}.",
                )
            if item.scale == 0:
                warning(
                    "ENCODING_SCALE_ZERO",
                    f"Encoding '{encoding.name}' has a physical range with scale 0.",
                )

    # Signal representations
    represented_signals: Set[str] = set()
    for item in ldf.signal_representations:
        if item.encoding_type not in encoding_names:
            error(
                "REPRESENTATION_ENCODING_UNKNOWN",
                f"Signal representation references unknown encoding '{item.encoding_type}'.",
            )
        for sig_name in item.signals:
            if sig_name not in signal_by_name:
                error(
                    "REPRESENTATION_SIGNAL_UNKNOWN",
                    f"Signal representation references unknown signal '{sig_name}'.",
                )
                continue
            if sig_name in represented_signals:
                warning(
                    "REPRESENTATION_SIGNAL_DUP",
                    f"Signal '{sig_name}' is mapped to multiple encodings.",
                )
            represented_signals.add(sig_name)

    # Node attributes
    node_attr_seen: Set[str] = set()
    slave_nodes = set(ldf.nodes.slaves) if ldf.nodes else set()
    for attr in ldf.node_attributes:
        if attr.node_name in node_attr_seen:
            warning(
                "NODE_ATTR_DUP",
                f"Duplicate Node_attributes block for '{attr.node_name}'.",
            )
        node_attr_seen.add(attr.node_name)

        if declared_nodes and attr.node_name not in declared_nodes:
            error(
                "NODE_ATTR_UNKNOWN_NODE",
                f"Node_attributes references unknown node '{attr.node_name}'.",
            )
        elif ldf.nodes and attr.node_name not in slave_nodes:
            warning(
                "NODE_ATTR_NOT_SLAVE",
                f"Node_attributes for '{attr.node_name}' is present but node is not listed as a slave.",
            )

        for nad_name, nad_value in (
            ("configured_NAD", attr.configured_nad),
            ("initial_NAD", attr.initial_nad),
        ):
            if nad_value < 0 or nad_value > 127:
                error(
                    "NODE_ATTR_NAD_RANGE",
                    f"Node '{attr.node_name}' has {nad_name}={nad_value}, outside 0..127.",
                )

        if attr.response_error and attr.response_error not in signal_by_name:
            error(
                "NODE_ATTR_RESPONSE_ERROR_UNKNOWN",
                f"Node '{attr.node_name}' response_error signal '{attr.response_error}' does not exist.",
            )

        for frame_name in attr.configurable_frames:
            # Many real-world files encode configurable frames as triplets:
            # <FrameName> = <hex-id> ;
            # The tolerant parser stores raw tokens, so skip assignment/operator
            # helper tokens here.
            if frame_name == "=":
                continue
            if re.fullmatch(r"0[xX][0-9A-Fa-f]+", frame_name):
                continue
            if re.fullmatch(r"\d+", frame_name):
                continue
            if frame_name not in frame_names:
                error(
                    "NODE_ATTR_CONFIG_FRAME_UNKNOWN",
                    f"Node '{attr.node_name}' configurable frame '{frame_name}' does not exist.",
                )

    return issues


def format_report(report: LDFConsistencyReport) -> str:
    """Render a human-readable report string."""
    header = f"{report.path}: "
    if not report.parsed:
        header += "PARSE FAILED"
    elif report.error_count == 0 and report.warning_count == 0:
        header += "CONSISTENT (no issues)"
    elif report.error_count == 0:
        header += f"CONSISTENT WITH WARNINGS ({report.warning_count} warning(s))"
    else:
        header += f"INCONSISTENT ({report.error_count} error(s), {report.warning_count} warning(s))"

    lines = [header]
    for issue in report.issues:
        lines.append(f"  [{issue.severity.upper()}] {issue.code}: {issue.message}")
    return "\n".join(lines)


def validate_workspace_ldf_files(root_dir: str) -> List[LDFConsistencyReport]:
    """Validate every .ldf file under a root directory."""
    root = Path(root_dir)
    reports: List[LDFConsistencyReport] = []
    for path in sorted(root.rglob("*.ldf")):
        rel = path.relative_to(root).as_posix()
        report = validate_ldf_file(str(path))
        report.path = rel
        reports.append(report)
    return reports

