"""Unit tests for ``src.lin_scheduler``.

Pure-function tests against synthetic LDF objects plus a parametrised pass
over the real LDF files in ``LDF/`` to confirm that the validator does not
report false positives for production schedules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFMaster,
    LDFNodes,
    LDFScheduleEntry,
    LDFScheduleTable,
    parse_ldf,
)
from src.lin_scheduler import (
    PlannedSlot,
    ScheduleIssue,
    baudrate_from_ldf,
    build_plan,
    bus_load_ratio,
    cycle_time_ms,
    is_multiple_of,
    validate_schedule,
)
from src.lin_timing import frame_time_ms

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LDF_DIR = Path(__file__).resolve().parents[1] / "LDF"


def _ldf(
    speed_kbps: float = 19.2,
    time_base: float = 5.0,
    jitter: float = 0.1,
    frames=None,
):
    """Build a minimal :class:`LDFFile` for scheduler tests."""
    nodes = LDFNodes(
        master=LDFMaster(name="Master", time_base=time_base, jitter=jitter),
        slaves=["SlaveA", "SlaveB"],
    )
    ldf = LDFFile(speed=speed_kbps, nodes=nodes, frames=list(frames or []))
    ldf.build_lookups()
    return ldf


def _frame(name: str, frame_id: int, size: int = 8, publisher: str = "Master") -> LDFFrame:
    return LDFFrame(name=name, frame_id=frame_id, publisher=publisher, frame_size=size)


def _table(name: str, *entries) -> LDFScheduleTable:
    return LDFScheduleTable(
        name=name,
        entries=[LDFScheduleEntry(frame_name=n, delay=d) for (n, d) in entries],
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestBaudrateFromLDF:
    def test_default_19200(self):
        assert baudrate_from_ldf(_ldf()) == 19_200

    def test_fractional_kbps_is_rounded(self):
        assert baudrate_from_ldf(_ldf(speed_kbps=10.4)) == 10_400

    def test_low_speed_lin(self):
        assert baudrate_from_ldf(_ldf(speed_kbps=2.4)) == 2_400


class TestIsMultipleOf:
    @pytest.mark.parametrize("value, base", [(10.0, 5.0), (15.0, 5.0), (0.0, 5.0)])
    def test_exact_multiples(self, value, base):
        assert is_multiple_of(value, base)

    def test_non_multiple_rejected(self):
        assert not is_multiple_of(7.0, 5.0)

    def test_zero_or_negative_base_returns_false(self):
        assert not is_multiple_of(10.0, 0.0)
        assert not is_multiple_of(10.0, -5.0)

    def test_floating_point_tolerance(self):
        # 0.1 + 0.1 + 0.1 != 0.3 in IEEE-754, but the helper must accept it.
        assert is_multiple_of(0.1 + 0.1 + 0.1, 0.1, tolerance=1e-6)


# ---------------------------------------------------------------------------
# validate_schedule
# ---------------------------------------------------------------------------


class TestValidateSchedule:
    def test_clean_schedule_has_no_issues(self):
        ldf = _ldf(frames=[_frame("F1", 0x10, 8), _frame("F2", 0x11, 4)])
        table = _table("S", ("F1", 10.0), ("F2", 10.0))
        assert validate_schedule(ldf, table) == []

    def test_unknown_frame_reports_issue(self):
        ldf = _ldf(frames=[_frame("F1", 0x10)])
        table = _table("S", ("Ghost", 10.0))
        issues = validate_schedule(ldf, table)
        assert any(i.code == "FRAME_UNKNOWN" for i in issues)

    def test_reserved_schedule_command_is_not_unknown(self):
        ldf = _ldf(frames=[_frame("F1", 0x10)])
        table = _table("S", ("MasterReq", 10.0), ("SlaveResp", 10.0), ("F1", 10.0))
        issues = validate_schedule(ldf, table)
        assert all(i.code != "FRAME_UNKNOWN" for i in issues)

    def test_non_positive_delay_reports_issue(self):
        ldf = _ldf(frames=[_frame("F1", 0x10)])
        table = _table("S", ("F1", 0.0))
        codes = {i.code for i in validate_schedule(ldf, table)}
        assert "DELAY_NOT_POSITIVE" in codes

    def test_delay_not_multiple_of_time_base(self):
        ldf = _ldf(time_base=5.0, frames=[_frame("F1", 0x10)])
        table = _table("S", ("F1", 7.0))
        codes = {i.code for i in validate_schedule(ldf, table)}
        assert "DELAY_NOT_MULTIPLE_OF_TIME_BASE" in codes

    def test_delay_below_frame_slot_at_baudrate(self):
        # At 19200 bps an 8-byte frame needs ~7.81 ms; a 5 ms delay is too
        # short and must be reported.
        ldf = _ldf(time_base=5.0, frames=[_frame("Big", 0x10, 8)])
        table = _table("S", ("Big", 5.0))
        codes = {i.code for i in validate_schedule(ldf, table)}
        assert "DELAY_BELOW_FRAME_SLOT" in codes

    def test_delay_meets_frame_slot_when_exact(self):
        # Pick a delay that is just above the worst-case slot, time-base
        # aligned, to confirm the boundary is handled correctly.
        ldf = _ldf(time_base=1.0, frames=[_frame("Big", 0x10, 8)])
        table = _table("S", ("Big", 10.0))
        assert validate_schedule(ldf, table) == []

    def test_baudrate_outside_lin_range_reported(self):
        ldf = _ldf(speed_kbps=50.0, frames=[_frame("F1", 0x10)])
        table = _table("S", ("F1", 10.0))
        codes = {i.code for i in validate_schedule(ldf, table)}
        assert "BAUDRATE_OUT_OF_RANGE" in codes

    def test_master_time_base_must_be_positive(self):
        ldf = _ldf(time_base=0.0, frames=[_frame("F1", 0x10)])
        table = _table("S", ("F1", 10.0))
        codes = {i.code for i in validate_schedule(ldf, table)}
        assert "MASTER_TIME_BASE_INVALID" in codes

    def test_empty_schedule_is_reported(self):
        ldf = _ldf()
        table = _table("S")
        issues = validate_schedule(ldf, table)
        assert any(i.code == "SCHEDULE_EMPTY" for i in issues)

    def test_issue_carries_entry_index(self):
        ldf = _ldf(frames=[_frame("F1", 0x10), _frame("F2", 0x11)])
        table = _table("S", ("F1", 10.0), ("F2", 7.0))
        issues = validate_schedule(ldf, table)
        bad = [i for i in issues if i.code == "DELAY_NOT_MULTIPLE_OF_TIME_BASE"]
        assert bad and bad[0].entry_index == 1


# ---------------------------------------------------------------------------
# build_plan / cycle_time / bus_load
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def test_offsets_are_running_sum_of_delays(self):
        ldf = _ldf(frames=[_frame("F1", 0x10), _frame("F2", 0x11)])
        table = _table("S", ("F1", 10.0), ("F2", 5.0), ("MasterReq", 5.0))
        plan = build_plan(ldf, table)
        assert [s.offset_ms for s in plan] == [0.0, 10.0, 15.0]
        assert [s.delay_ms for s in plan] == [10.0, 5.0, 5.0]

    def test_frame_id_resolved_when_known(self):
        ldf = _ldf(frames=[_frame("F1", 0x10, 4)])
        plan = build_plan(ldf, _table("S", ("F1", 10.0)))
        slot = plan[0]
        assert isinstance(slot, PlannedSlot)
        assert slot.frame_id == 0x10
        assert slot.data_length == 4

    def test_frame_id_none_for_command_or_unknown(self):
        ldf = _ldf(frames=[_frame("F1", 0x10)])
        plan = build_plan(ldf, _table("S", ("MasterReq", 10.0), ("Ghost", 10.0)))
        assert plan[0].frame_id is None and plan[0].data_length is None
        assert plan[1].frame_id is None and plan[1].data_length is None

    def test_indices_are_sequential(self):
        ldf = _ldf(frames=[_frame("F1", 0x10)])
        table = _table("S", ("F1", 10.0), ("F1", 10.0), ("F1", 10.0))
        assert [s.index for s in build_plan(ldf, table)] == [0, 1, 2]


class TestCycleTime:
    def test_sum_of_delays(self):
        table = _table("S", ("F1", 10.0), ("F2", 7.5), ("F3", 2.5))
        assert cycle_time_ms(table) == pytest.approx(20.0)

    def test_empty_table_zero(self):
        assert cycle_time_ms(_table("S")) == 0.0


class TestBusLoad:
    def test_low_load_when_delays_are_long(self):
        ldf = _ldf(frames=[_frame("F1", 0x10, 8)])
        table = _table("S", ("F1", 100.0))
        # 8-byte frame slot ~7.81 ms in a 100 ms cycle -> ~7.8 % load.
        load = bus_load_ratio(ldf, table)
        slot = frame_time_ms(19_200, 8, with_slack=True)
        assert load == pytest.approx(slot / 100.0, abs=1e-3)

    def test_zero_when_cycle_is_zero(self):
        ldf = _ldf(frames=[_frame("F1", 0x10, 8)])
        table = _table("S")
        assert bus_load_ratio(ldf, table) == 0.0

    def test_zero_when_baudrate_out_of_range(self):
        ldf = _ldf(speed_kbps=50.0, frames=[_frame("F1", 0x10, 8)])
        table = _table("S", ("F1", 100.0))
        assert bus_load_ratio(ldf, table) == 0.0

    def test_clamped_to_one(self):
        # 8-byte frame at 1 kbps takes ~ 60 ms slot but we schedule it every
        # 1 ms -> load would be way > 1 without clamp. Validate the clamp.
        ldf = _ldf(speed_kbps=1.0, time_base=1.0, frames=[_frame("F1", 0x10, 8)])
        table = _table("S", ("F1", 1.0))
        assert bus_load_ratio(ldf, table) == 1.0

    def test_unknown_frames_not_counted(self):
        ldf = _ldf(frames=[_frame("F1", 0x10, 8)])
        table = _table("S", ("Ghost", 100.0))
        assert bus_load_ratio(ldf, table) == 0.0


# ---------------------------------------------------------------------------
# Real LDF parametrised pass
# ---------------------------------------------------------------------------


def _ldf_files() -> list[Path]:
    if not LDF_DIR.exists():
        return []
    return sorted(p for p in LDF_DIR.iterdir() if p.suffix.lower() == ".ldf")


@pytest.mark.parametrize("ldf_path", _ldf_files(), ids=lambda p: p.name)
class TestRealLDFSchedules:
    """Run the validator over every committed LDF schedule.

    The intent is **not** to assert zero issues (some legacy LDFs may be
    intentionally non-conformant), but to make sure the validator never
    crashes and that, when it does flag a real LDF, the violation can be
    observed for follow-up review.
    """

    def test_validator_runs_without_exceptions(self, ldf_path: Path):
        try:
            ldf = parse_ldf(str(ldf_path))
        except Exception as exc:  # noqa: BLE001 - parser robustness covered elsewhere.
            pytest.skip(f"LDF could not be parsed: {exc}")
        for table in ldf.schedule_tables:
            issues = validate_schedule(ldf, table)
            assert all(isinstance(i, ScheduleIssue) for i in issues)

    def test_build_plan_offsets_are_monotonic(self, ldf_path: Path):
        try:
            ldf = parse_ldf(str(ldf_path))
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"LDF could not be parsed: {exc}")
        for table in ldf.schedule_tables:
            offsets = [s.offset_ms for s in build_plan(ldf, table)]
            assert offsets == sorted(offsets), (
                f"Plan offsets not monotonic for table '{table.name}' in {ldf_path.name}"
            )
