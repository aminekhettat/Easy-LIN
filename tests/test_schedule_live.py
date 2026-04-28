"""Live hardware-loopback test for the LIN scheduler timing.

Opens two LIN channels of the same Vector device (e.g. VN1630A): channel 1
acts as a master executing a small synthetic schedule, channel 2 acts as a
listener whose received frame timestamps are compared against the planned
slot offsets returned by :func:`src.lin_scheduler.build_plan`.

Skipped automatically when:

* ``EASYLIN_RUN_LIVE_HW_TESTS`` is not set to ``1``,
* the Vector XL DLL is not installed,
* fewer than two LIN-configurable channels are available on a single device,
* opening the channels fails for any reason.

Local run::

    $env:EASYLIN_RUN_LIVE_HW_TESTS = "1"
    python -m pytest tests/test_schedule_live.py -v

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

import os
import time

import pytest

if os.environ.get("EASYLIN_RUN_LIVE_HW_TESTS") != "1":
    pytest.skip(
        "Live Vector hardware tests are opt-in. Set EASYLIN_RUN_LIVE_HW_TESTS=1 to enable.",
        allow_module_level=True,
    )

try:
    from src.vector_xl_api import VectorXLApi, VectorXLDriverNotFoundError
except Exception as exc:  # noqa: BLE001
    pytest.skip(
        f"Cannot import VectorXLApi (driver bindings unavailable): {exc}",
        allow_module_level=True,
    )

from src.communication.hardware_discovery import HardwareDiscovery
from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFMaster,
    LDFNodes,
    LDFScheduleEntry,
    LDFScheduleTable,
)
from src.lin_master import LINMaster, ReceivedFrame
from src.lin_scheduler import build_plan, cycle_time_ms


def _two_channel_masks_or_skip() -> tuple[int, int]:
    """Return two channel masks on the same device, or skip the test."""
    try:
        api = VectorXLApi()
    except VectorXLDriverNotFoundError as exc:
        pytest.skip(f"Vector XL Driver not installed: {exc}")
    devices = HardwareDiscovery(api=api).scan_devices()
    for device in devices:
        lin_chs = [c for c in device.channels if c.lin_configurable]
        if len(lin_chs) >= 2:
            return lin_chs[0].channel_mask, lin_chs[1].channel_mask
    pytest.skip("Need a Vector device with at least 2 LIN-configurable channels.")


def _build_test_ldf() -> tuple[LDFFile, LDFScheduleTable]:
    """Build a 3-slot synthetic LDF for the loopback test."""
    ldf = LDFFile(
        protocol_version="2.1",
        language_version="2.1",
        speed=19.2,
        nodes=LDFNodes(
            master=LDFMaster(name="M", time_base=10.0, jitter=0.5),
            slaves=["S"],
        ),
        frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
            LDFFrame(name="F2", frame_id=0x11, publisher="M", frame_size=2),
            LDFFrame(name="F3", frame_id=0x12, publisher="M", frame_size=2),
        ],
        schedule_tables=[
            LDFScheduleTable(
                name="LiveSched",
                entries=[
                    LDFScheduleEntry(frame_name="F1", delay=50.0),
                    LDFScheduleEntry(frame_name="F2", delay=50.0),
                    LDFScheduleEntry(frame_name="F3", delay=50.0),
                ],
            )
        ],
    )
    ldf.build_lookups()
    return ldf, ldf.schedule_tables[0]


def test_schedule_loopback_inter_header_timing() -> None:
    """Plan offsets must match the inter-header timestamps observed on the bus."""
    master_mask, listener_mask = _two_channel_masks_or_skip()

    ldf, table = _build_test_ldf()
    plan = build_plan(ldf, table)
    cycle_ms = cycle_time_ms(table)

    received: list[ReceivedFrame] = []

    def on_rx(frame: ReceivedFrame) -> None:
        received.append(frame)

    master = LINMaster()
    listener = LINMaster(on_frame_received=on_rx)
    try:
        try:
            master.connect(channel_mask=master_mask, ldf=ldf)
            listener.connect(channel_mask=listener_mask, ldf=ldf)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Could not open both LIN channels for loopback: {exc}")

        master.run_schedule(table)
        # 4 cycles -> 12 frames; 4 * 150 ms = 600 ms; allow some slack.
        time.sleep((4 * cycle_ms / 1000.0) + 0.20)
        master.stop_schedule()
    finally:
        try:
            listener.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            master.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # We expect at least 3 cycles worth of frames captured by the listener.
    assert len(received) >= 9, f"Listener only captured {len(received)} frames."

    # Convert timestamps (ns) to ms relative to the first received frame.
    t0 = received[0].timestamp_ns
    rel_ms = [(f.timestamp_ns - t0) / 1_000_000.0 for f in received]

    # For each consecutive pair of headers in the plan, the observed
    # inter-header delta must be within +/- (time_base + jitter) of the
    # planned delay (50 ms).
    expected_delay = plan[1].delay_ms  # 50 ms
    tolerance_ms = ldf.nodes.master.time_base + ldf.nodes.master.jitter  # 10.5 ms

    deltas = [rel_ms[i + 1] - rel_ms[i] for i in range(len(rel_ms) - 1)]
    bad = [d for d in deltas if abs(d - expected_delay) > tolerance_ms]
    assert not bad, (
        f"Inter-header timing out of tolerance ({tolerance_ms:.1f} ms): "
        f"deltas={deltas} expected={expected_delay}"
    )

    # Cumulative drift over the whole capture must stay below 2 * time_base.
    total_drift = abs(rel_ms[-1] - expected_delay * (len(rel_ms) - 1))
    assert total_drift < 2 * ldf.nodes.master.time_base, (
        f"Cumulative drift {total_drift:.2f} ms over {len(rel_ms)} headers "
        f"exceeds 2*time_base ({2 * ldf.nodes.master.time_base:.1f} ms)."
    )
