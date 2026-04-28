"""Vector hardware discovery helpers.

Scans local Vector XL driver configuration and returns LIN-capable channels.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
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
    article_number: int = 0
    transceiver_name: str = ""
    bus_capabilities: int = 0
    lin_configurable: bool = False


@dataclass(frozen=True)
class VectorDevice:
    """Describes one Vector hardware unit and its LIN channels."""

    hw_type: int
    hw_index: int
    device_serial: str
    channels: List[LINChannel]
    article_number: int = 0


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
        # ``xlGetDriverConfig`` only enumerates real hardware after
        # ``xlOpenDriver`` has been called. Without it the driver returns a
        # placeholder virtual channel, hiding any connected device.
        opened = False
        if hasattr(self._api, "open_driver"):
            try:
                self._api.open_driver()
                opened = True
            except Exception:  # noqa: BLE001 - tolerate test doubles / already-open
                opened = False
        try:
            cfg = self._api.get_driver_config()
            channels = self._api.lin_channels(cfg)
        finally:
            if opened and hasattr(self._api, "close_driver"):
                try:
                    self._api.close_driver()
                except Exception:  # noqa: BLE001
                    pass
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
            try:
                raw_serial = int(getattr(ch, "serialNumber", 0) or 0)
            except (TypeError, ValueError):
                raw_serial = 0
            if raw_serial:
                serial = f"{raw_serial}"
            else:
                serial = f"{int(ch.hwType):03d}-{int(ch.hwIndex):03d}"
            try:
                article_number = int(getattr(ch, "articleNumber", 0) or 0)
            except (TypeError, ValueError):
                article_number = 0
            transceiver_raw = getattr(ch, "transceiverName", b"") or b""
            if isinstance(transceiver_raw, (bytes, bytearray)):
                transceiver_name = transceiver_raw.decode("ascii", errors="replace").strip("\x00")
            else:
                transceiver_name = str(transceiver_raw)
            try:
                bus_caps = int(getattr(ch, "channelBusCapabilities", 0) or 0)
            except (TypeError, ValueError):
                bus_caps = 0
            lin_configurable = VectorXLApi.is_lin_configurable(ch)
            lin_channel = LINChannel(
                name=ch.name.decode("ascii", errors="replace").strip("\x00"),
                hw_type=int(ch.hwType),
                hw_index=int(ch.hwIndex),
                hw_channel=int(ch.hwChannel),
                channel_index=int(ch.channelIndex),
                channel_mask=int(ch.channelMask),
                device_serial=serial,
                article_number=article_number,
                transceiver_name=transceiver_name,
                bus_capabilities=bus_caps,
                lin_configurable=lin_configurable,
            )
            by_device.setdefault((lin_channel.hw_type, lin_channel.hw_index), []).append(
                lin_channel
            )

        devices: List[VectorDevice] = []
        for (hw_type, hw_index), dev_channels in by_device.items():
            serial = dev_channels[0].device_serial
            article = dev_channels[0].article_number
            devices.append(
                VectorDevice(
                    hw_type=hw_type,
                    hw_index=hw_index,
                    device_serial=serial,
                    channels=sorted(dev_channels, key=lambda c: (c.hw_channel, c.channel_index)),
                    article_number=article,
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

    def auto_assign_application(
        self, app_name: str = "EasyLIN", bus_type: int = 0x00000002
    ) -> List[dict]:
        """Register every detected LIN channel as an application channel.

        For each LIN channel returned by :meth:`get_lin_channels` this method
        ensures that the named Vector application has a matching application
        channel in Vector Hardware Manager. Channels that are already assigned
        to the same hardware are left untouched.

        Args:
            app_name: Vector application name to register (must match the name
                later passed to :func:`xlOpenPort`).
            bus_type: Vector bus type to register the application channel for.
                Defaults to ``XL_BUS_TYPE_LIN``.

        Returns:
            One dict per LIN channel describing the resulting assignment with
            keys ``app_channel``, ``hw_type``, ``hw_index``, ``hw_channel``
            and ``action`` (``"created"``, ``"updated"`` or ``"kept"``).
        """
        results: List[dict] = []
        channels = self.get_lin_channels()
        if not channels:
            return results
        opened = False
        if hasattr(self._api, "open_driver"):
            try:
                self._api.open_driver()
                opened = True
            except Exception:  # noqa: BLE001 - tolerate already-open / mock api
                opened = False
        try:
            app_channel = 0
            for channel in channels:
                if not channel.lin_configurable:
                    # Skip channels that are LIN-compatible at the silicon
                    # level but cannot currently be activated as LIN
                    # (missing piggyback, unlicensed feature, etc.).
                    results.append(
                        {
                            "app_channel": None,
                            "hw_type": channel.hw_type,
                            "hw_index": channel.hw_index,
                            "hw_channel": channel.hw_channel,
                            "channel_mask": channel.channel_mask,
                            "name": channel.name,
                            "action": "skipped-not-configurable",
                        }
                    )
                    continue
                action = "kept"
                try:
                    current = self._api.get_appl_config(app_name, app_channel, bus_type)
                except Exception:  # noqa: BLE001
                    current = (0, 0, 0)
                desired = (channel.hw_type, channel.hw_index, channel.hw_channel)
                if current != desired:
                    try:
                        self._api.set_appl_config(
                            app_name,
                            app_channel,
                            channel.hw_type,
                            channel.hw_index,
                            channel.hw_channel,
                            bus_type,
                        )
                        action = "created" if current == (0, 0, 0) else "updated"
                    except Exception:  # noqa: BLE001 - missing export / driver
                        action = "skipped"
                results.append(
                    {
                        "app_channel": app_channel,
                        "hw_type": channel.hw_type,
                        "hw_index": channel.hw_index,
                        "hw_channel": channel.hw_channel,
                        "channel_mask": channel.channel_mask,
                        "name": channel.name,
                        "action": action,
                    }
                )
                app_channel += 1
        finally:
            if opened and hasattr(self._api, "close_driver"):
                try:
                    self._api.close_driver()
                except Exception:  # noqa: BLE001
                    pass
        return results
