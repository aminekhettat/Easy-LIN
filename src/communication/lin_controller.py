"""High-level LIN controller built on the Vector XL ctypes wrapper.

Provides connection lifecycle, frame TX/RX, checksum management and optional
scheduler execution.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:date: 2026-03-23
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from src.communication.exceptions import LINError
from src.communication.hardware_discovery import LINChannel
from src.vector_xl_api import (
    VectorXLApi,
    XL_LIN_CHECKSUM_CLASSIC,
    XL_LIN_CHECKSUM_ENHANCED,
    XL_LIN_MASTER,
    XL_LIN_SLAVE,
)


class LINMode(Enum):
    """Operating mode of the local LIN node."""

    MASTER = XL_LIN_MASTER
    SLAVE = XL_LIN_SLAVE


class ChecksumMode(Enum):
    """LIN checksum strategy for one frame ID."""

    CLASSIC = XL_LIN_CHECKSUM_CLASSIC
    ENHANCED = XL_LIN_CHECKSUM_ENHANCED


@dataclass(frozen=True)
class LINFrame:
    """One LIN frame received from the bus."""

    frame_id: int
    dlc: int
    data: bytes
    timestamp_ns: int


@dataclass(frozen=True)
class ScheduleEntry:
    """One periodic scheduler entry."""

    frame_id: int
    dlc: int
    data: List[int]


@dataclass(frozen=True)
class BUSStatistics:
    """Simple bus activity counters for UI/reporting usage."""

    tx_count: int
    rx_count: int


class LINController:
    """Manage LIN communication using VectorXLApi only."""

    def __init__(self, api: VectorXLApi | None = None) -> None:
        """Create controller with optional API dependency injection."""
        self._api = api or VectorXLApi()
        self._connected = False
        self._port_handle: Optional[int] = None
        self._access_mask: Optional[int] = None
        self._checksum_table: List[int] = [XL_LIN_CHECKSUM_ENHANCED] * 64
        self._tx_count = 0
        self._rx_count = 0

        self._sched_thread: Optional[threading.Thread] = None
        self._sched_stop = threading.Event()

    def connect(self, channel: LINChannel, baudrate: int, mode: LINMode) -> None:
        """Connect to one LIN channel and configure protocol settings.

        Args:
            channel: Target channel selected from discovery.
            baudrate: LIN bitrate in bit/s.
            mode: Master or slave mode.

        Raises:
            LINError: If already connected or setup fails.
        """
        if self._connected:
            raise LINError("Controller already connected")
        try:
            self._api.open_driver()
            access_mask = self._api.get_channel_mask(
                channel.hw_type,
                channel.hw_index,
                channel.hw_channel,
            )
            port_handle, _perm = self._api.open_port("Easy-LIN", access_mask)
            self._api.set_timer_rate(port_handle, 1000)
            self._api.set_lin_channel_params(
                port_handle,
                access_mask,
                baudrate=baudrate,
                lin_version=0x20,
            )
            if mode == LINMode.MASTER:
                self._api.set_lin_dlc(port_handle, access_mask, [8] * 64)
            self._api.lin_set_checksum_info(port_handle, access_mask, self._checksum_table)
            self._api.activate_channel(port_handle, access_mask)
        except Exception as exc:  # pragma: no cover - wrapped and validated by tests
            try:
                self._api.close_driver()
            except Exception:
                pass
            raise LINError(f"Unable to connect LIN controller: {exc}") from exc

        self._port_handle = port_handle
        self._access_mask = access_mask
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect and release all Vector XL resources."""
        if not self._connected or self._port_handle is None or self._access_mask is None:
            raise LINError("Controller is not connected")

        self.stop_scheduler()
        self._api.deactivate_channel(self._port_handle, self._access_mask)
        self._api.close_port(self._port_handle)
        self._api.close_driver()

        self._connected = False
        self._port_handle = None
        self._access_mask = None

    def send_master_request(self, frame_id: int) -> None:
        """Send one LIN master request header."""
        self._require_connected()
        self._api.lin_send_request(self._port_handle, self._access_mask, frame_id)
        self._tx_count += 1

    def send_slave_response(self, frame_id: int, data: List[int]) -> None:
        """Send one data response frame as master-published response."""
        self._require_connected()
        if len(data) > 8:
            raise LINError("DLC cannot exceed 8 bytes")
        self._api.lin_send_response(
            self._port_handle,
            self._access_mask,
            frame_id,
            len(data),
            data,
        )
        self._tx_count += 1

    def receive_frame(self, timeout_ms: int) -> Optional[LINFrame]:
        """Receive one frame event from the bus.

        Args:
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            LINFrame if one message event is received, else None.
        """
        self._require_connected()
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            evt = self._api.receive_event(self._port_handle)
            if evt is None:
                time.sleep(0.001)
                continue
            if getattr(evt, "tag", -1) != 14:
                continue
            msg = evt.lin_msg
            frame = LINFrame(
                frame_id=int(msg.id & 0x3F),
                dlc=int(msg.dlc),
                data=bytes(msg.data[: msg.dlc]),
                timestamp_ns=int(evt.timeStamp),
            )
            self._rx_count += 1
            return frame
        return None

    def start_scheduler(self, schedule: List[ScheduleEntry], interval_ms: int) -> None:
        """Start periodic scheduler loop over a list of schedule entries."""
        self._require_connected()
        self.stop_scheduler()
        self._sched_stop.clear()
        self._sched_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(schedule, interval_ms),
            daemon=True,
            name="LINController-Scheduler",
        )
        self._sched_thread.start()

    def stop_scheduler(self) -> None:
        """Stop scheduler loop if currently running."""
        self._sched_stop.set()
        if self._sched_thread is not None:
            self._sched_thread.join(timeout=2.0)
            self._sched_thread = None

    def set_checksum_mode(self, frame_id: int, mode: ChecksumMode) -> None:
        """Set checksum mode for one frame ID and push it if connected."""
        if frame_id < 0 or frame_id > 63:
            raise LINError("frame_id must be in range 0..63")
        self._checksum_table[frame_id] = mode.value
        if self._connected:
            self._api.lin_set_checksum_info(
                self._port_handle,
                self._access_mask,
                self._checksum_table,
            )

    def get_bus_statistics(self) -> BUSStatistics:
        """Return cumulative transmit/receive counters."""
        return BUSStatistics(tx_count=self._tx_count, rx_count=self._rx_count)

    def _scheduler_loop(self, schedule: List[ScheduleEntry], interval_ms: int) -> None:
        """Internal scheduler worker thread."""
        interval_s = max(1, interval_ms) / 1000.0
        while not self._sched_stop.is_set():
            for entry in schedule:
                if self._sched_stop.is_set():
                    break
                if entry.data:
                    self.send_slave_response(entry.frame_id, entry.data[: entry.dlc])
                else:
                    self.send_master_request(entry.frame_id)
                end = time.monotonic() + interval_s
                while time.monotonic() < end and not self._sched_stop.is_set():
                    time.sleep(0.001)

    def _require_connected(self) -> None:
        """Validate controller connection state before bus operations."""
        if not self._connected or self._port_handle is None or self._access_mask is None:
            raise LINError("Controller is not connected")
