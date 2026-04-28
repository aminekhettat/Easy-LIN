"""Deterministic tests for the refactored LINMaster schedule loop.

These tests replace ``time.monotonic`` and ``time.sleep`` with a fake clock
so that timing behavior of :py:meth:`src.lin_master.LINMaster._schedule_loop`
can be asserted without real wall-clock waits. Verifies:

* anchored deadlines (no drift across cycles),
* command/unknown slots are skipped (no transmit) but still consume time,
* stop event short-circuits both the wait and the slot iteration,
* per-cycle TX order matches the planned slot order.

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

from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.ldf_parser import LDFFile, LDFFrame, LDFScheduleEntry, LDFScheduleTable
from src.lin_master import LINMaster
from src.vector_xl_api import VectorXLApi, VectorXLError


# ---------------------------------------------------------------------------
# Fake clock
# ---------------------------------------------------------------------------


class FakeClock:
    """A monotonic clock whose value only advances when ``sleep`` is called.

    The schedule loop runs in a thread; the fake clock optionally records a
    "stop after N sleeps" trigger so tests can deterministically end the loop
    after a fixed amount of simulated time.
    """

    def __init__(self, *, stop_event=None, stop_after_seconds: Optional[float] = None) -> None:
        """Store initial state for the fake clock."""
        self.now: float = 0.0
        self.sleeps: List[float] = []
        self._stop_event = stop_event
        self._stop_after = stop_after_seconds

    def monotonic(self) -> float:
        """Return the current simulated monotonic time, in seconds."""
        return self.now

    def sleep(self, dt: float) -> None:
        """Advance simulated time by ``dt`` and trigger stop when due."""
        self.sleeps.append(dt)
        self.now += dt
        if self._stop_event is not None and self._stop_after is not None:
            if self.now >= self._stop_after:
                self._stop_event.set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ldf_with_frames(*specs: tuple[str, int, int]) -> LDFFile:
    """Build an LDF with the given ``(name, frame_id, frame_size)`` frames."""
    ldf = LDFFile(protocol_version="2.0", speed=19.2)
    ldf.frames = [
        LDFFrame(name=name, frame_id=fid, publisher="M", frame_size=size)
        for (name, fid, size) in specs
    ]
    ldf.build_lookups()
    return ldf


def _schedule(*entries: tuple[str, float]) -> LDFScheduleTable:
    """Build an ``LDFScheduleTable`` from ``(frame_name, delay_ms)`` tuples."""
    return LDFScheduleTable(
        name="Test",
        entries=[LDFScheduleEntry(frame_name=name, delay=delay) for (name, delay) in entries],
    )


def _mock_api() -> MagicMock:
    """Return a ``VectorXLApi`` mock suitable for ``LINMaster.connect``."""
    api = MagicMock(spec=VectorXLApi)
    api.open_port.return_value = (1, 1)
    api.receive.return_value = None
    return api


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScheduleLoopAnchored:
    @patch("src.lin_master.VectorXLApi")
    def test_two_cycles_no_drift(self, MockApi):
        """After 2 full cycles, the cycle anchor must not have drifted."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _ldf_with_frames(("F1", 0x10, 2), ("F2", 0x11, 2))
        sched = _schedule(("F1", 10.0), ("F2", 10.0))  # 20 ms cycle, 2 slots

        clock = FakeClock()
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=ldf)

        # Stop after the loop has fired exactly 4 sends (2 cycles).
        send_times: List[float] = []

        def record_and_maybe_stop(*_a, **_kw):
            send_times.append(clock.now)
            if len(send_times) >= 4:
                m._sched_stop.set()

        api.lin_send_request.side_effect = record_and_maybe_stop

        # Drive _schedule_loop synchronously (no thread) for determinism.
        m._sched_stop.clear()
        m._schedule_loop(sched)

        # Anchor at t=0 → expected fires at 0, 0.010, 0.020, 0.030 s.
        assert send_times == pytest.approx([0.0, 0.010, 0.020, 0.030], abs=1e-6)
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_command_slots_skip_send(self, MockApi):
        """Schedule entries with no matching frame must NOT call lin_send_request."""
        api = _mock_api()
        MockApi.return_value = api
        # Only F1 exists; "Cmd" is not in the LDF and resolves to frame_id=None.
        ldf = _ldf_with_frames(("F1", 0x10, 2))
        sched = _schedule(("F1", 10.0), ("Cmd", 10.0), ("F1", 10.0))

        clock = FakeClock()
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=ldf)

        send_times: List[float] = []

        def record_and_maybe_stop(*_a, **_kw):
            send_times.append(clock.now)
            if len(send_times) >= 2:
                m._sched_stop.set()

        api.lin_send_request.side_effect = record_and_maybe_stop

        m._sched_stop.clear()
        m._schedule_loop(sched)

        # F1 fires at 0 and 0.020 s; Cmd at 0.010 s does not transmit.
        assert send_times == pytest.approx([0.0, 0.020], abs=1e-6)
        assert api.lin_send_request.call_count == 2
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_stop_event_exits_loop(self, MockApi):
        """Setting the stop event must terminate the loop without further sends."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _ldf_with_frames(("F1", 0x10, 2))
        sched = _schedule(("F1", 50.0))

        # Stop after ~25 ms of simulated time -> before the first slot deadline (50 ms)
        # is met, but sleeps still occur.
        clock = FakeClock(stop_event=None, stop_after_seconds=None)
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=ldf)

        # Configure stop trigger now that the master exists.
        clock._stop_event = m._sched_stop
        clock._stop_after = 0.025

        m._sched_stop.clear()
        m._schedule_loop(sched)

        # The first slot has offset 0 so it fires at t=0 before any sleep;
        # the stop event then short-circuits the wait for the second cycle.
        assert api.lin_send_request.call_count == 1
        # We must have stopped at or just past 25 ms (well before the 50 ms wrap).
        assert 0.025 <= clock.now < 0.050
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_tx_order_matches_plan(self, MockApi):
        """Each cycle, sends must be in plan order (F1, F2, F3)."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _ldf_with_frames(("F1", 0x10, 2), ("F2", 0x11, 2), ("F3", 0x12, 2))
        sched = _schedule(("F1", 5.0), ("F2", 5.0), ("F3", 5.0))

        clock = FakeClock()
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=ldf)

        ids: List[int] = []

        def record_and_maybe_stop(_port, _mask, fid):
            ids.append(fid)
            if len(ids) >= 6:  # 2 full cycles
                m._sched_stop.set()

        api.lin_send_request.side_effect = record_and_maybe_stop

        m._sched_stop.clear()
        m._schedule_loop(sched)

        assert ids == [0x10, 0x11, 0x12, 0x10, 0x11, 0x12]
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_empty_plan_returns_immediately(self, MockApi):
        """An empty schedule must return without calling sleep or send."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _ldf_with_frames()
        sched = _schedule()  # no entries

        clock = FakeClock()
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=ldf)

        m._sched_stop.clear()
        m._schedule_loop(sched)

        assert clock.sleeps == []
        api.lin_send_request.assert_not_called()
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_no_ldf_fallback_skips_send(self, MockApi):
        """With no LDF, the loop times out the cycle but transmits nothing."""
        api = _mock_api()
        MockApi.return_value = api
        sched = _schedule(("X", 10.0), ("Y", 10.0))

        clock = FakeClock()
        m = LINMaster(clock=clock.monotonic, sleep=clock.sleep)
        m.connect(channel_mask=1, ldf=None)

        clock._stop_event = m._sched_stop
        clock._stop_after = 0.025  # stop midway through the second slot

        m._sched_stop.clear()
        m._schedule_loop(sched)

        api.lin_send_request.assert_not_called()
        assert clock.now >= 0.025
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_send_error_invokes_on_error(self, MockApi):
        """A VectorXLError during transmit calls on_error and continues."""
        api = _mock_api()
        api.lin_send_request.side_effect = VectorXLError("xlLinSendRequest", 0xAA)
        MockApi.return_value = api
        ldf = _ldf_with_frames(("F1", 0x10, 2))
        sched = _schedule(("F1", 10.0))

        errors: List[str] = []
        clock = FakeClock()
        m = LINMaster(
            on_error=lambda msg: errors.append(msg), clock=clock.monotonic, sleep=clock.sleep
        )
        m.connect(channel_mask=1, ldf=ldf)

        # Stop after the error handler has been called twice.
        original = m._on_error

        def stopping_on_error(msg):
            original(msg)
            if len(errors) >= 2:
                m._sched_stop.set()

        m._on_error = stopping_on_error

        m._sched_stop.clear()
        m._schedule_loop(sched)

        assert len(errors) >= 2
        m._connected = False
