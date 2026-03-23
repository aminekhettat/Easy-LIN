"""Vector hardware discovery helpers.

Scans local Vector XL driver configuration and returns LIN-capable channels.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:date: 2026-03-23
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.vector_xl_api import VectorXLApi


@dataclass(frozen=True)
class LINChannel:
    """Describes one LIN-capable Vector channel."""

    name: str
    hw_type: int
    hw_index: int
    hw_channel: int
    channel_index: int
    channel_mask: int
    device_serial: str


@dataclass(frozen=True)
class VectorDevice:
    """Describes one Vector hardware unit and its LIN channels."""

    hw_type: int
    hw_index: int
    device_serial: str
    channels: List[LINChannel]


class HardwareDiscovery:
    """Auto-detect connected Vector devices and LIN-capable channels."""

    def __init__(self, api: VectorXLApi | None = None) -> None:
        """Create discovery helper.

        Args:
            api: Optional pre-configured API instance for dependency injection.
        """
        self._api = api or VectorXLApi()

    def scan_devices(self) -> List[VectorDevice]:
        """Scan all detected Vector devices.

        Returns:
            List of unique hardware devices with their LIN channels.
        """
        cfg = self._api.get_driver_config()
        channels = self._api.lin_channels(cfg)
        by_device: Dict[tuple[int, int], List[LINChannel]] = {}
        seen_keys: set[tuple[int, int, int, int]] = set()
        for ch in channels:
            key = (
                int(ch.hwType),
                int(ch.hwIndex),
                int(ch.hwChannel),
                int(ch.channelIndex),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            serial = f"{int(ch.hwType):03d}-{int(ch.hwIndex):03d}"
            lin_channel = LINChannel(
                name=ch.name.decode("ascii", errors="replace").strip("\x00"),
                hw_type=int(ch.hwType),
                hw_index=int(ch.hwIndex),
                hw_channel=int(ch.hwChannel),
                channel_index=int(ch.channelIndex),
                channel_mask=int(ch.channelMask),
                device_serial=serial,
            )
            by_device.setdefault((lin_channel.hw_type, lin_channel.hw_index), []).append(
                lin_channel
            )

        devices: List[VectorDevice] = []
        for (hw_type, hw_index), dev_channels in by_device.items():
            serial = f"{hw_type:03d}-{hw_index:03d}"
            devices.append(
                VectorDevice(
                    hw_type=hw_type,
                    hw_index=hw_index,
                    device_serial=serial,
                    channels=sorted(dev_channels, key=lambda c: (c.hw_channel, c.channel_index)),
                )
            )
        return sorted(devices, key=lambda d: (d.hw_type, d.hw_index))

    def get_lin_channels(self) -> List[LINChannel]:
        """Return all LIN-capable channels from all devices."""
        out: List[LINChannel] = []
        for device in self.scan_devices():
            out.extend(device.channels)
        return out

    def get_channel_info(self, hw_type: int, hw_index: int, hw_channel: int) -> LINChannel:
        """Return complete information for one specific LIN channel.

        Args:
            hw_type: Vector hardware type.
            hw_index: Device index.
            hw_channel: Channel index on the device.

        Returns:
            Matching LIN channel.

        Raises:
            LookupError: If no matching channel is found.
        """
        for channel in self.get_lin_channels():
            if (
                channel.hw_type == hw_type
                and channel.hw_index == hw_index
                and channel.hw_channel == hw_channel
            ):
                return channel
        raise LookupError("LIN channel not found")

    def get_channel_by_index(self, channel_index: int) -> LINChannel:
        """Return one channel by global Vector channel index."""
        for channel in self.get_lin_channels():
            if channel.channel_index == channel_index:
                return channel
        raise LookupError("LIN channel index not found")

    def get_channel_by_mask(self, channel_mask: int) -> LINChannel:
        """Return one channel by global Vector channel mask."""
        for channel in self.get_lin_channels():
            if channel.channel_mask == channel_mask:
                return channel
        raise LookupError("LIN channel mask not found")

    def get_channels_for_device(self, hw_type: int, hw_index: int) -> List[LINChannel]:
        """Return all channels for one device identity."""
        channels = [
            channel
            for channel in self.get_lin_channels()
            if channel.hw_type == hw_type and channel.hw_index == hw_index
        ]
        if not channels:
            raise LookupError("LIN device not found")
        return channels

    def is_device_available(self, device_serial: str) -> bool:
        """Check whether a device is visible in current driver configuration."""
        return any(device.device_serial == device_serial for device in self.scan_devices())
