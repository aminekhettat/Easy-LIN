"""High-level LIN master built on top of :mod:`src.vector_xl_api`.

Responsibilities include hardware lifecycle management, LIN channel setup,
frame transmission, schedule execution, and receive callback dispatch.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.10.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import logging
import threading
import time
from typing import Callable, List, Optional

from src.ldf_parser import LDFFile, LDFScheduleTable
from src.lin_scheduler import PlannedSlot, build_plan, cycle_time_ms
from src.vector_xl_api import (
    VectorXLApi,
    VectorXLDriverNotFoundError,
    VectorXLError,
    XL_LIN_VERSION_1_3,
    XL_LIN_VERSION_2_0,
    XL_LIN_VERSION_2_1,
)

log = logging.getLogger(__name__)

# XL_EVENT tag value for LIN messages (defined in vxlapi.h)
_TAG_LIN_MSG = 14


# ---------------------------------------------------------------------------
# Received frame DTO
# ---------------------------------------------------------------------------


class ReceivedFrame:
    """Represents one LIN frame received from the bus."""

    __slots__ = ("frame_id", "data", "timestamp_ns", "crc_error", "checksum")

    def __init__(
        self,
        frame_id: int,
        data: bytes,
        timestamp_ns: int,
        crc_error: bool = False,
        checksum: Optional[int] = None,
    ) -> None:
        """Store the parsed contents of one received LIN frame."""
        self.frame_id = frame_id
        self.data = data
        self.timestamp_ns = timestamp_ns
        self.crc_error = crc_error
        self.checksum = checksum

    def __repr__(self) -> str:
        """Return a compact diagnostic representation of the received frame."""
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return (
            f"ReceivedFrame(id=0x{self.frame_id:02X}, data=[{hex_data}], ts={self.timestamp_ns}ns)"
        )


# ---------------------------------------------------------------------------
# LIN Master
# ---------------------------------------------------------------------------


class LINMaster:
    """
    Manages a single LIN channel on a Vector VN16xx device.

    Parameters
    ----------
    on_frame_received:
        Callable invoked (from a background thread) whenever a LIN frame
        is received.  Signature: ``(frame: ReceivedFrame) -> None``.
    on_error:
        Callable invoked when a hardware or communication error occurs.
        Signature: ``(msg: str) -> None``.
    """

    def __init__(
        self,
        on_frame_received: Optional[Callable[[ReceivedFrame], None]] = None,
        on_frame_changed: Optional[Callable[[ReceivedFrame, Optional[bytes]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the master controller and its background-thread state.

        ``clock`` and ``sleep`` are injection points used by deterministic
        unit tests; production code keeps the defaults (``time.monotonic`` /
        ``time.sleep``).
        """
        self._on_frame_received = on_frame_received
        self._on_frame_changed = on_frame_changed
        self._on_error = on_error
        self._clock = clock
        self._sleep = sleep

        self._api: Optional[VectorXLApi] = None
        self._port_handle: int = -1
        self._access_mask: int = 0
        self._connected: bool = False
        self._ldf: Optional[LDFFile] = None

        self._rx_thread: Optional[threading.Thread] = None
        self._rx_stop = threading.Event()

        self._sched_thread: Optional[threading.Thread] = None
        self._sched_stop = threading.Event()

        # Last payload observed for each frame ID (used by changed-frame callback).
        self._last_frame_data: dict[int, bytes] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return ``True`` when hardware access is currently active."""
        return self._connected

    @property
    def ldf(self) -> Optional[LDFFile]:
        """Return the currently loaded LDF associated with the connection."""
        return self._ldf

    @property
    def dll_path(self) -> Optional[str]:
        """Return the DLL path from the active API connection, or None."""
        return getattr(self._api, "dll_path", None)

    def preflight(self) -> tuple[bool, str]:
        """Verify the Vector XL DLL is callable before a live connection attempt.

        Returns:
            ``(True, 'OK')`` when the DLL can execute ``xlOpenDriver`` successfully.
            ``(False, <reason>)`` if the driver is missing, not licensed, or otherwise
            non-functional.
        """
        try:
            api = VectorXLApi()
            return api.preflight()
        except VectorXLDriverNotFoundError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ------------------------------------------------------------------
    # Hardware enumeration (static helper)
    # ------------------------------------------------------------------

    @staticmethod
    def list_lin_channels() -> List[dict]:
        """Return a list of available LIN channels as plain dicts.

        Each dict has keys: ``name``, ``channel_index``, ``channel_mask``,
        and (when reported by the driver) ``hw_type``, ``hw_index``,
        ``hw_channel``, ``device_serial``, ``article_number`` and
        ``transceiver_name``.
        Returns an empty list if the Vector driver is not installed.
        """
        try:
            api = VectorXLApi()
            api.open_driver()
            cfg = api.get_driver_config()
            channels = api.lin_channels(cfg)
            api.close_driver()
            result: List[dict] = []
            for ch in channels:
                try:
                    serial_raw = int(getattr(ch, "serialNumber", 0) or 0)
                except (TypeError, ValueError):
                    serial_raw = 0
                hw_type = int(getattr(ch, "hwType", 0) or 0)
                hw_index = int(getattr(ch, "hwIndex", 0) or 0)
                if serial_raw:
                    serial = str(serial_raw)
                else:
                    serial = f"{hw_type:03d}-{hw_index:03d}"
                try:
                    article = int(getattr(ch, "articleNumber", 0) or 0)
                except (TypeError, ValueError):
                    article = 0
                xcvr_raw = getattr(ch, "transceiverName", b"") or b""
                if isinstance(xcvr_raw, (bytes, bytearray)):
                    xcvr = xcvr_raw.decode("ascii", errors="replace").strip("\x00")
                else:
                    xcvr = str(xcvr_raw)
                try:
                    bus_caps = int(getattr(ch, "channelBusCapabilities", 0) or 0)
                except (TypeError, ValueError):
                    bus_caps = 0
                lin_configurable = VectorXLApi.is_lin_configurable(ch)
                result.append(
                    {
                        "name": ch.name.decode("ascii", errors="replace").strip("\x00"),
                        "channel_index": ch.channelIndex,
                        "channel_mask": ch.channelMask,
                        "hw_type": hw_type,
                        "hw_index": hw_index,
                        "hw_channel": int(getattr(ch, "hwChannel", 0) or 0),
                        "device_serial": serial,
                        "article_number": article,
                        "transceiver_name": xcvr,
                        "bus_capabilities": bus_caps,
                        "lin_configurable": lin_configurable,
                    }
                )
            return result
        except VectorXLDriverNotFoundError:
            return []
        except Exception as exc:
            log.warning("Could not enumerate LIN channels: %s", exc)
            return []

    @staticmethod
    def auto_assign_lin_channels(app_name: str = "EasyLIN") -> List[dict]:
        """Register every detected LIN channel with the Vector driver under
        ``app_name`` so the application appears pre-configured in Vector
        Hardware Manager (no manual channel assignment required).

        Returns the list of resulting assignments, or an empty list if the
        Vector driver is not installed.
        """
        try:
            from src.communication.hardware_discovery import HardwareDiscovery

            return HardwareDiscovery().auto_assign_application(app_name=app_name)
        except VectorXLDriverNotFoundError:
            return []
        except Exception as exc:
            log.warning("Auto channel assignment failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    def connect(
        self,
        channel_mask: int,
        ldf: Optional[LDFFile] = None,
        app_name: str = "EasyLIN",
    ) -> None:
        """Connect to a LIN channel and start the RX listener thread.

        Parameters
        ----------
        channel_mask:
            Bit-mask of the channel to open (from :meth:`list_lin_channels`).
        ldf:
            Optional parsed LDF file.  When supplied the baud rate and
            per-frame DLC table are configured automatically.
        app_name:
            Name registered with the Vector XL Driver.
        """
        if self._connected:
            raise RuntimeError("Already connected â€” call disconnect() first.")

        self._api = VectorXLApi()
        self._api.open_driver()
        self._access_mask = channel_mask

        port_handle, perm_mask = self._api.open_port(app_name, channel_mask)
        self._port_handle = port_handle

        if perm_mask == 0:
            log.warning("No TX permission granted for the selected channel.")

        # Determine baud rate from LDF (default 19200)
        baudrate = 19200
        lin_version = XL_LIN_VERSION_2_0
        if ldf is not None:
            baudrate = int(ldf.speed * 1000)
            v = ldf.protocol_version
            if v.startswith("1"):
                lin_version = XL_LIN_VERSION_1_3
            elif v.startswith("2.1") or v.startswith("2.2"):
                lin_version = XL_LIN_VERSION_2_1
            else:
                lin_version = XL_LIN_VERSION_2_0
            self._ldf = ldf

        self._api.set_lin_channel_params(port_handle, channel_mask, baudrate, lin_version)

        # Configure DLC table from LDF
        if ldf is not None:
            dlc_table = [0] * 64
            for frame in ldf.frames:
                if 0 <= frame.frame_id <= 63:
                    dlc_table[frame.frame_id] = frame.frame_size
            self._api.set_lin_dlc(port_handle, channel_mask, dlc_table)

        self._api.activate_channel(port_handle, channel_mask)
        self._connected = True
        self._last_frame_data.clear()

        # Start RX thread
        self._rx_stop.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            name="LINMaster-RX",
            daemon=True,
        )
        self._rx_thread.start()
        log.info("LIN master connected (baud=%d, version=%d)", baudrate, lin_version)

    def disconnect(self) -> None:
        """Stop schedule (if running), stop RX thread, and release hardware."""
        self.stop_schedule()

        self._rx_stop.set()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=2.0)
            self._rx_thread = None

        if self._api is not None and self._port_handle != -1:
            try:
                self._api.deactivate_channel(self._port_handle, self._access_mask)
                self._api.close_port(self._port_handle)
                self._api.close_driver()
            except Exception as exc:
                log.warning("Error during disconnect: %s", exc)

        self._api = None
        self._port_handle = -1
        self._connected = False
        self._ldf = None
        self._last_frame_data.clear()
        log.info("LIN master disconnected.")

    # ------------------------------------------------------------------
    # Frame transmission
    # ------------------------------------------------------------------

    def send_frame(self, frame_id: int) -> None:
        """Send a LIN master request (header) for the given frame ID.

        The slave that owns the matching ID will respond with data bytes.
        Received data will be delivered via the ``on_frame_received`` callback.
        """
        if not self._connected:
            raise RuntimeError("Not connected.")
        self._api.lin_send_request(self._port_handle, self._access_mask, frame_id)

    def send_frame_data(self, frame_id: int, data: List[int]) -> None:
        """Pre-load data and send a master-response frame (unconditional frame).

        Use this when the master itself is the publisher of the frame.
        """
        if not self._connected:
            raise RuntimeError("Not connected.")
        self._api.set_lin_frame_response(self._port_handle, self._access_mask, frame_id, data)
        self._api.lin_send_request(self._port_handle, self._access_mask, frame_id)

    # ------------------------------------------------------------------
    # Schedule table execution
    # ------------------------------------------------------------------

    def run_schedule(self, schedule: LDFScheduleTable) -> None:
        """Start executing a schedule table in a background thread.

        Each entry in the table is sent at the specified delay interval.
        An already-running schedule is stopped before starting the new one.
        """
        self.stop_schedule()
        self._sched_stop.clear()
        self._sched_thread = threading.Thread(
            target=self._schedule_loop,
            args=(schedule,),
            name="LINMaster-Sched",
            daemon=True,
        )
        self._sched_thread.start()
        log.info("Started schedule '%s'.", schedule.name)

    def stop_schedule(self) -> None:
        """Stop the currently running schedule (no-op if none running)."""
        self._sched_stop.set()
        if self._sched_thread is not None:
            self._sched_thread.join(timeout=2.0)
            self._sched_thread = None

    # ------------------------------------------------------------------
    # Internal threads
    # ------------------------------------------------------------------

    def _rx_loop(self) -> None:
        """Background thread: poll for received XL events."""
        while not self._rx_stop.is_set():
            try:
                evt = self._api.receive(self._port_handle)
                if evt is None:
                    time.sleep(0.001)  # 1 ms poll interval
                    continue
                if evt.tag == _TAG_LIN_MSG:
                    self._handle_rx_lin_event(evt)
            except VectorXLError as exc:
                log.warning("RX error: %s", exc)
                if self._on_error:
                    self._on_error(str(exc))
                time.sleep(0.010)
            except Exception:
                log.exception("Unexpected error in RX loop.")
                time.sleep(0.010)

    def _handle_rx_lin_event(self, evt) -> None:
        """Build a received frame from one XL event and dispatch callbacks."""
        msg = evt.lin_msg
        frame = ReceivedFrame(
            frame_id=msg.id & 0x3F,
            data=bytes(msg.data[: msg.dlc]),
            timestamp_ns=evt.timeStamp,
            crc_error=bool(msg.flags & 0x08),
            checksum=int(msg.crc),
        )
        if self._on_frame_received:
            try:
                self._on_frame_received(frame)
            except Exception:
                log.exception("Error in on_frame_received callback.")

        previous_data = self._last_frame_data.get(frame.frame_id)
        if previous_data == frame.data:
            return

        self._last_frame_data[frame.frame_id] = frame.data
        if self._on_frame_changed:
            try:
                self._on_frame_changed(frame, previous_data)
            except Exception:
                log.exception("Error in on_frame_changed callback.")

    def _schedule_loop(self, schedule: LDFScheduleTable) -> None:
        """Background thread: execute the schedule table repeatedly.

        Uses :func:`src.lin_scheduler.build_plan` to compute a deterministic
        per-cycle plan (frame name, frame id, offset, delay) once, then
        anchors all transmit deadlines to a single ``cycle_anchor`` value so
        that drift does not accumulate across cycles. When no LDF is
        available, falls back to a minimal in-place plan based on schedule
        entry delays (no frame_id resolution, no transmit).
        """
        ldf = self._ldf
        if ldf is not None:
            plan: List[PlannedSlot] = build_plan(ldf, schedule)
            cycle_ms = cycle_time_ms(schedule)
        else:
            # Build a degraded plan so the loop still observes timing.
            offset = 0.0
            plan = []
            for idx, entry in enumerate(schedule.entries):
                plan.append(
                    PlannedSlot(
                        index=idx,
                        offset_ms=offset,
                        delay_ms=float(entry.delay),
                        frame_name=entry.frame_name,
                        frame_id=None,
                        data_length=None,
                    )
                )
                offset += float(entry.delay)
            cycle_ms = offset

        if not plan or cycle_ms <= 0.0:
            return

        cycle_anchor = self._clock()
        cycle_idx = 0
        while not self._sched_stop.is_set():
            for slot in plan:
                if self._sched_stop.is_set():
                    break
                target = cycle_anchor + (cycle_idx * cycle_ms + slot.offset_ms) / 1000.0
                self._wait_until(target)
                if self._sched_stop.is_set():
                    break
                if slot.frame_id is None:
                    continue
                try:
                    self._api.lin_send_request(self._port_handle, self._access_mask, slot.frame_id)
                except VectorXLError as exc:
                    log.warning("Schedule TX error: %s", exc)
                    if self._on_error:
                        self._on_error(str(exc))
            cycle_idx += 1

    def _wait_until(self, target: float) -> None:
        """Sleep in ~1 ms increments until ``target`` (monotonic seconds)."""
        while not self._sched_stop.is_set():
            now = self._clock()
            remaining = target - now
            if remaining <= 0:
                return
            self._sleep(min(remaining, 0.001))
