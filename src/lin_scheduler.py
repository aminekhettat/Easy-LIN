"""LIN schedule-table validation and execution-plan builder.

Pure functions that take an :class:`~src.ldf_parser.LDFFile` and a
:class:`~src.ldf_parser.LDFScheduleTable` and produce:

* a list of :class:`ScheduleIssue` (validation problems found), and
* a list of :class:`PlannedSlot` (deterministic per-cycle execution plan)

without performing any I/O or hardware access. The generated plan is the
single source of truth used by both unit tests (against a fake clock) and
the real :class:`~src.lin_master.LINMaster` background scheduler.

Reference: LIN Specification Package 2.2A, sections 2.4 ("Bit rate"),
2.3.2.4 ("Frame transfer time") and 2.5 ("Schedule table").

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.10.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from src.ldf_parser import LDFFile, LDFScheduleTable
from src.lin_timing import frame_time_ms

# Reserved schedule commands that LDFs may use instead of a frame name.
# They are recognised so the validator does not flag them as unknown frames.
_SCHEDULE_COMMANDS = {
    "AssignFrameId",
    "AssignFrameIdRange",
    "AssignNAD",
    "ConditionalChangeNAD",
    "DataDump",
    "FreeFormat",
    "MasterReq",
    "SaveConfiguration",
    "SlaveResp",
    "UnassignFrameId",
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleIssue:
    """One problem found while validating a schedule table.

    Attributes:
        code: Stable machine-readable identifier (e.g.
            ``"DELAY_NOT_MULTIPLE_OF_TIME_BASE"``).
        entry_index: Position of the offending entry in the table, or
            ``None`` for table-level issues.
        message: Human-readable description suitable for end users.
    """

    code: str
    entry_index: Optional[int]
    message: str


@dataclass(frozen=True)
class PlannedSlot:
    """One executable slot in a schedule cycle.

    Attributes:
        index: Position of the originating entry in the LDF table.
        offset_ms: Slot start time inside the cycle, in milliseconds, with
            ``0`` for the first entry. Subsequent offsets equal the running
            sum of the previous entry delays.
        delay_ms: Configured delay of the entry (== next-slot duration).
        frame_name: Name of the frame or schedule command at this slot.
        frame_id: Frame ID resolved from the LDF, or ``None`` for schedule
            commands and unknown frames.
        data_length: Frame payload length in bytes, or ``None`` when the
            frame is unknown / a schedule command.
    """

    index: int
    offset_ms: float
    delay_ms: float
    frame_name: str
    frame_id: Optional[int]
    data_length: Optional[int]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def baudrate_from_ldf(ldf: LDFFile) -> int:
    """Return the LIN baud rate (bits per second) declared in ``ldf``.

    The LDF stores ``LIN_speed`` in **kbps** (e.g. ``19.2``). This helper
    converts it to integer bps for downstream consumers and clamps it to
    the closest integer.
    """
    return int(round(float(ldf.speed) * 1000.0))


def is_multiple_of(value: float, base: float, *, tolerance: float = 1e-6) -> bool:
    """Return True when ``value`` is an integer multiple of ``base``."""
    if base <= 0:
        return False
    ratio = value / base
    return abs(ratio - round(ratio)) <= tolerance


def validate_schedule(ldf: LDFFile, table: LDFScheduleTable) -> List[ScheduleIssue]:
    """Validate one schedule table against the LDF and the LIN protocol.

    Checks performed:

    * the LDF declares a baud rate inside the LIN range,
    * the master node defines a strictly positive ``time_base``,
    * every entry has a strictly positive delay,
    * every delay is an integer multiple of the master ``time_base``,
    * every frame name resolves to a known LDF frame *or* one of the
      reserved schedule commands,
    * for resolvable frames, the entry delay is at least the maximum frame
      slot time at the configured baud rate (header + response with the
      40 % LIN slack budget),
    * the cycle time is positive.

    Returns:
        One :class:`ScheduleIssue` per violation. An empty list means the
        table is fully consistent for the configured network.
    """
    issues: List[ScheduleIssue] = []

    baudrate = baudrate_from_ldf(ldf)
    if baudrate < 1_000 or baudrate > 20_000:
        issues.append(
            ScheduleIssue(
                "BAUDRATE_OUT_OF_RANGE",
                None,
                f"LDF baud rate {baudrate} bps outside LIN range [1000, 20000].",
            )
        )

    time_base = float(getattr(ldf.nodes.master, "time_base", 0.0)) if ldf.nodes else 0.0
    if time_base <= 0.0:
        issues.append(
            ScheduleIssue(
                "MASTER_TIME_BASE_INVALID",
                None,
                f"Master time base {time_base} ms must be strictly positive.",
            )
        )

    if not table.entries:
        issues.append(
            ScheduleIssue(
                "SCHEDULE_EMPTY",
                None,
                f"Schedule table '{table.name}' has no entries.",
            )
        )
        return issues

    for index, entry in enumerate(table.entries):
        if entry.delay <= 0:
            issues.append(
                ScheduleIssue(
                    "DELAY_NOT_POSITIVE",
                    index,
                    f"Entry '{entry.frame_name}' has non-positive delay {entry.delay} ms.",
                )
            )
        elif time_base > 0 and not is_multiple_of(entry.delay, time_base):
            issues.append(
                ScheduleIssue(
                    "DELAY_NOT_MULTIPLE_OF_TIME_BASE",
                    index,
                    f"Entry '{entry.frame_name}' delay {entry.delay} ms is "
                    f"not an integer multiple of the master time base "
                    f"{time_base} ms.",
                )
            )

        frame = ldf.frame_by_name(entry.frame_name)
        if frame is None:
            if entry.frame_name not in _SCHEDULE_COMMANDS:
                issues.append(
                    ScheduleIssue(
                        "FRAME_UNKNOWN",
                        index,
                        f"Entry '{entry.frame_name}' references no known "
                        f"frame and is not a reserved LIN schedule command.",
                    )
                )
            continue

        if 1_000 <= baudrate <= 20_000 and 1 <= frame.frame_size <= 8:
            slot_max_ms = frame_time_ms(baudrate, frame.frame_size, with_slack=True)
            if entry.delay + 1e-6 < slot_max_ms:
                issues.append(
                    ScheduleIssue(
                        "DELAY_BELOW_FRAME_SLOT",
                        index,
                        f"Entry '{entry.frame_name}' delay {entry.delay} ms "
                        f"is shorter than the worst-case slot "
                        f"{slot_max_ms:.3f} ms required for an "
                        f"{frame.frame_size}-byte frame at {baudrate} bps.",
                    )
                )

    return issues


def build_plan(ldf: LDFFile, table: LDFScheduleTable) -> List[PlannedSlot]:
    """Build the deterministic per-cycle execution plan for ``table``.

    The plan keeps the original LDF order. Slot ``i`` is scheduled to start
    at the running sum of the previous entry delays; the entry's own
    ``delay_ms`` is the slot duration consumed before moving to slot
    ``i + 1``. The cycle time of the table is therefore::

        cycle_ms = sum(entry.delay for entry in table.entries)

    Frame ID and data length are resolved from the LDF when possible. They
    are ``None`` for entries pointing at a reserved schedule command or at
    a frame that the LDF does not declare.
    """
    plan: List[PlannedSlot] = []
    offset = 0.0
    for index, entry in enumerate(table.entries):
        frame = ldf.frame_by_name(entry.frame_name)
        plan.append(
            PlannedSlot(
                index=index,
                offset_ms=offset,
                delay_ms=float(entry.delay),
                frame_name=entry.frame_name,
                frame_id=frame.frame_id if frame is not None else None,
                data_length=frame.frame_size if frame is not None else None,
            )
        )
        offset += float(entry.delay)
    return plan


def cycle_time_ms(table: LDFScheduleTable) -> float:
    """Return the total cycle time of ``table`` (sum of entry delays, ms)."""
    return float(sum(entry.delay for entry in table.entries))


def bus_load_ratio(ldf: LDFFile, table: LDFScheduleTable) -> float:
    """Return the bus load ratio (0.0 - 1.0) for ``table`` at the LDF baud.

    Defined as the sum of the worst-case slot times for every resolvable
    frame entry divided by the cycle time. Reserved schedule commands and
    unknown frames are skipped (cannot be sized). Returns ``0.0`` when the
    cycle time is zero.
    """
    cycle = cycle_time_ms(table)
    if cycle <= 0:
        return 0.0
    baudrate = baudrate_from_ldf(ldf)
    if baudrate < 1_000 or baudrate > 20_000:
        return 0.0
    busy = 0.0
    for entry in table.entries:
        frame = ldf.frame_by_name(entry.frame_name)
        if frame is None or not (1 <= frame.frame_size <= 8):
            continue
        busy += frame_time_ms(baudrate, frame.frame_size, with_slack=True)
    return min(1.0, busy / cycle) if not math.isnan(busy) else 0.0
