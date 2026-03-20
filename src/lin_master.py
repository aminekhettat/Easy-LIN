"""High-level LIN master built on top of :mod:`src.vector_xl_api`.

Responsibilities include hardware lifecycle management, LIN channel setup,
frame transmission, schedule execution, and receive callback dispatch.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
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

    __slots__ = ("frame_id", "data", "timestamp_ns", "crc_error")

    def __init__(
        self,
        frame_id: int,
        data: bytes,
        timestamp_ns: int,
        crc_error: bool = False,
    ) -> None:
        """Store the parsed contents of one received LIN frame."""
        self.frame_id = frame_id
        self.data = data
        self.timestamp_ns = timestamp_ns
        self.crc_error = crc_error

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
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize the master controller and its background-thread state."""
        self._on_frame_received = on_frame_received
        self._on_error = on_error

        self._api: Optional[VectorXLApi] = None
        self._port_handle: int = -1
        self._access_mask: int = 0
        self._connected: bool = False
        self._ldf: Optional[LDFFile] = None

        self._rx_thread: Optional[threading.Thread] = None
        self._rx_stop = threading.Event()

        self._sched_thread: Optional[threading.Thread] = None
        self._sched_stop = threading.Event()

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

    # ------------------------------------------------------------------
    # Hardware enumeration (static helper)
    # ------------------------------------------------------------------

    @staticmethod
    def list_lin_channels() -> List[dict]:
        """Return a list of available LIN channels as plain dicts.

        Each dict has keys: ``name``, ``channel_index``, ``channel_mask``.
        Returns an empty list if the Vector driver is not installed.
        """
        try:
            api = VectorXLApi()
            api.open_driver()
            cfg = api.get_driver_config()
            channels = api.lin_channels(cfg)
            api.close_driver()
            return [
                {
                    "name": ch.name.decode("ascii", errors="replace").strip("\x00"),
                    "channel_index": ch.channelIndex,
                    "channel_mask": ch.channelMask,
                }
                for ch in channels
            ]
        except VectorXLDriverNotFoundError:
            return []
        except Exception as exc:
            log.warning("Could not enumerate LIN channels: %s", exc)
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
                    msg = evt.lin_msg
                    frame = ReceivedFrame(
                        frame_id=msg.id & 0x3F,
                        data=bytes(msg.data[: msg.dlc]),
                        timestamp_ns=evt.timeStamp,
                        crc_error=bool(msg.flags & 0x08),
                    )
                    if self._on_frame_received:
                        try:
                            self._on_frame_received(frame)
                        except Exception:
                            log.exception("Error in on_frame_received callback.")
            except VectorXLError as exc:
                log.warning("RX error: %s", exc)
                if self._on_error:
                    self._on_error(str(exc))
                time.sleep(0.010)
            except Exception:
                log.exception("Unexpected error in RX loop.")
                time.sleep(0.010)

    def _schedule_loop(self, schedule: LDFScheduleTable) -> None:
        """Background thread: execute the schedule table repeatedly."""
        ldf = self._ldf
        while not self._sched_stop.is_set():
            for entry in schedule.entries:
                if self._sched_stop.is_set():
                    break
                # Resolve frame ID from LDF (if available)
                frame_id: Optional[int] = None
                if ldf is not None:
                    frame = ldf.frame_by_name(entry.frame_name)
                    if frame is not None:
                        frame_id = frame.frame_id
                if frame_id is not None:
                    try:
                        self._api.lin_send_request(self._port_handle, self._access_mask, frame_id)
                    except VectorXLError as exc:
                        log.warning("Schedule TX error: %s", exc)
                        if self._on_error:
                            self._on_error(str(exc))
                # Sleep for the specified delay
                deadline = time.monotonic() + entry.delay / 1000.0
                while time.monotonic() < deadline and not self._sched_stop.is_set():
                    time.sleep(0.001)

