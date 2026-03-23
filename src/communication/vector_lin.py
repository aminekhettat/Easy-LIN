"""Vector CAN/LIN communication module.

Wraps :mod:`python-can` with the Vector XL-driver backend to provide a clean
LIN master interface. Falls back to a software simulation mode when Vector
hardware is not present so the application remains usable without hardware.

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

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import python-can; define a stub if unavailable.
# ---------------------------------------------------------------------------
try:
    import can

    _CAN_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on runtime environment
    can = None  # type: ignore[assignment]
    _CAN_AVAILABLE = False


class LINError(Exception):
    """Raised when a LIN communication error occurs."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LINFrame:
    """A single LIN bus frame (data payload + metadata)."""

    frame_id: int
    data: bytes = b""
    timestamp: float = field(default_factory=time.time)
    direction: str = "TX"  # 'TX' or 'RX'
    is_error: bool = False
    error_description: str = ""

    @property
    def frame_id_hex(self) -> str:
        """Return the frame identifier formatted as hexadecimal text."""
        return f"0x{self.frame_id:02X}"

    @property
    def data_hex(self) -> str:
        """Return the payload bytes formatted as hexadecimal text."""
        return " ".join(f"{b:02X}" for b in self.data)

    def __str__(self) -> str:
        """Return a short human-readable representation of the frame."""
        return f"[{self.direction}] ID={self.frame_id_hex} Data=[{self.data_hex}]"


# ---------------------------------------------------------------------------
# Simulation bus (used when Vector hardware is absent)
# ---------------------------------------------------------------------------


class _SimBus:
    """
    A minimal LIN bus simulation.

    Received frames echo the transmitted data back after a short delay.
    This allows the application to be tested without physical hardware.
    """

    def __init__(self) -> None:
        """Initialize the in-process simulation bus state."""
        self._running = False
        self._rx_callbacks: list[Callable[[LINFrame], None]] = []
        self._lock = threading.Lock()
        logger.info("LIN simulation bus initialised (no Vector hardware detected).")

    def send(self, frame: LINFrame) -> None:
        """Simulate sending a LIN frame by echoing it as RX after 5 ms."""

        def _echo():
            """Echo the transmitted frame back to registered RX callbacks."""
            time.sleep(0.005)
            rx = LINFrame(
                frame_id=frame.frame_id,
                data=frame.data,
                direction="RX",
            )
            with self._lock:
                for cb in self._rx_callbacks:
                    try:
                        cb(rx)
                    except Exception:
                        logger.exception("Error in RX callback")

        threading.Thread(target=_echo, daemon=True).start()

    def add_rx_callback(self, callback: Callable[[LINFrame], None]) -> None:
        """Register a simulation receive callback."""
        with self._lock:
            self._rx_callbacks.append(callback)

    def shutdown(self) -> None:
        """Stop the simulation bus."""
        self._running = False
        logger.info("LIN simulation bus shut down.")


# ---------------------------------------------------------------------------
# Vector LIN bus wrapper
# ---------------------------------------------------------------------------


class VectorLINBus:
    """
    High-level interface to a LIN bus via Vector hardware (XL-driver).

    Usage::

        bus = VectorLINBus(channel=0, bitrate=19200)
        bus.add_rx_callback(lambda frame: print(frame))
        bus.start()
        bus.send_frame(LINFrame(frame_id=0x01, data=bytes([0x11, 0x22])))
        bus.stop()

    If no Vector hardware is found the class falls back to simulation mode
    automatically.
    """

    def __init__(
        self,
        channel: int = 0,
        bitrate: int = 19200,
        app_name: str = "Easy-LIN",
    ) -> None:
        """Initialize a Vector-backed or simulated LIN bus wrapper."""
        self.channel = channel
        self.bitrate = bitrate
        self.app_name = app_name
        self._simulation = False
        self._bus: Optional[object] = None
        self._sim_bus: Optional[_SimBus] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self._rx_callbacks: list[Callable[[LINFrame], None]] = []
        self._tx_callbacks: list[Callable[[LINFrame], None]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def is_simulation(self) -> bool:
        """True when running in software simulation mode (no hardware)."""
        return self._simulation

    @property
    def is_connected(self) -> bool:
        """Return ``True`` when the bus has been started."""
        return self._running

    @staticmethod
    def list_vector_channels() -> list[dict]:
        """
        Return a list of available Vector channel descriptors.

        Returns an empty list when no Vector hardware / driver is found.
        """
        if not _CAN_AVAILABLE:
            return []
        try:
            cfg = can.detect_available_configs(interfaces=["vector"])
            return list(cfg)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the LIN bus and start the background RX thread."""
        if self._running:
            return
        self._try_open_vector()
        self._running = True
        if not self._simulation:
            self._rx_thread = threading.Thread(
                target=self._rx_loop, daemon=True, name="LIN-RX"
            )
            self._rx_thread.start()

    def stop(self) -> None:
        """Stop the RX thread and close the bus."""
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=2.0)
        if self._bus:
            try:
                self._bus.shutdown()  # type: ignore[union-attr]
            except Exception:
                pass
        if self._sim_bus:
            self._sim_bus.shutdown()
        logger.info("VectorLINBus stopped.")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def add_rx_callback(self, callback: Callable[[LINFrame], None]) -> None:
        """Register a callback invoked for every received LIN frame."""
        with self._lock:
            self._rx_callbacks.append(callback)
        if self._sim_bus:
            self._sim_bus.add_rx_callback(callback)

    def add_tx_callback(self, callback: Callable[[LINFrame], None]) -> None:
        """Register a callback invoked for every transmitted LIN frame."""
        with self._lock:
            self._tx_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Frame transmission
    # ------------------------------------------------------------------

    def send_frame(self, frame: LINFrame) -> None:
        """
        Transmit a :class:`LINFrame` on the LIN bus.

        Raises :class:`LINError` if the bus is not started.
        """
        if not self._running:
            raise LINError("Bus is not started.  Call start() first.")
        frame.direction = "TX"
        frame.timestamp = time.time()
        self._notify_tx(frame)

        if self._simulation and self._sim_bus:
            self._sim_bus.send(frame)
        else:
            self._send_via_can(frame)

    def send_frame_by_id(self, frame_id: int, data: bytes | list[int]) -> LINFrame:
        """Convenience wrapper: send a frame given *frame_id* and *data*."""
        if isinstance(data, list):
            data = bytes(data)
        frame = LINFrame(frame_id=frame_id, data=data)
        self.send_frame(frame)
        return frame

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_open_vector(self) -> None:
        """Open the Vector backend or fall back to the simulation bus."""
        if not _CAN_AVAILABLE:
            logger.warning(
                "python-can is not installed â€“ switching to simulation mode."
            )
            self._simulation = True
            self._sim_bus = _SimBus()
            with self._lock:
                callbacks = list(self._rx_callbacks)
            for callback in callbacks:
                self._sim_bus.add_rx_callback(callback)
            return

        try:
            self._bus = can.interface.Bus(
                bustype="vector",
                channel=self.channel,
                bitrate=self.bitrate,
                app_name=self.app_name,
                lin_type="LIN",
            )
            logger.info(
                "Opened Vector LIN channel %d at %d bps.",
                self.channel,
                self.bitrate,
            )
        except Exception as exc:
            logger.warning(
                "Could not open Vector hardware (%s) â€“ switching to simulation mode.",
                exc,
            )
            self._simulation = True
            self._sim_bus = _SimBus()
            with self._lock:
                callbacks = list(self._rx_callbacks)
            for callback in callbacks:
                self._sim_bus.add_rx_callback(callback)

    def _rx_loop(self) -> None:
        """Background thread: receive frames from python-can and dispatch."""
        while self._running:
            try:
                msg = self._bus.recv(timeout=0.1)  # type: ignore[union-attr]
                if msg is not None:
                    frame = LINFrame(
                        frame_id=msg.arbitration_id & 0x3F,
                        data=bytes(msg.data),
                        timestamp=msg.timestamp,
                        direction="RX",
                    )
                    self._notify_rx(frame)
            except Exception:
                if self._running:
                    logger.exception("Error in RX loop")

    def _send_via_can(self, frame: LINFrame) -> None:
        """Send a frame through the active :mod:`python-can` bus."""
        if self._bus is None:
            return
        try:
            msg = can.Message(  # type: ignore[union-attr]
                arbitration_id=frame.frame_id,
                data=list(frame.data),
                is_extended_id=False,
            )
            self._bus.send(msg)  # type: ignore[union-attr]
        except Exception as exc:
            raise LINError(f"Send failed: {exc}") from exc

    def _notify_rx(self, frame: LINFrame) -> None:
        """Dispatch one received frame to all registered RX callbacks."""
        with self._lock:
            callbacks = list(self._rx_callbacks)
        for cb in callbacks:
            try:
                cb(frame)
            except Exception:
                logger.exception("Error in RX callback")

    def _notify_tx(self, frame: LINFrame) -> None:
        """Dispatch one transmitted frame to all registered TX callbacks."""
        with self._lock:
            callbacks = list(self._tx_callbacks)
        for cb in callbacks:
            try:
                cb(frame)
            except Exception:
                logger.exception("Error in TX callback")

