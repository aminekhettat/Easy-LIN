"""Tests for src.communication.hardware_discovery."""

from unittest.mock import MagicMock

import pytest

from src.communication.hardware_discovery import HardwareDiscovery, LINChannel


class TestHardwareDiscovery:
    def _channel(self, name, hw_type, hw_index, hw_channel, mask, lin_cap=True):
        ch = MagicMock()
        ch.name = name.encode("ascii") + b"\x00"
        ch.hwType = hw_type
        ch.hwIndex = hw_index
        ch.hwChannel = hw_channel
        ch.channelIndex = hw_channel
        ch.channelMask = mask
        ch.channelBusCapabilities = 0x00000200 if lin_cap else 0
        return ch

    def test_scan_devices_returns_all_devices(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("VN1610 CH0", 57, 0, 0, 0x1)
        ch1 = self._channel("VN1610 CH1", 57, 0, 1, 0x2)
        ch2 = self._channel("VN1600 CH0", 55, 1, 0, 0x4)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0, ch1, ch2]

        d = HardwareDiscovery(api=api)
        devices = d.scan_devices()

        assert len(devices) == 2
        assert devices[0].channels
        assert devices[1].channels

    def test_scan_devices_no_device_returns_empty(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        assert d.scan_devices() == []

    def test_get_lin_channels_filters_correctly(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x1)
        ch1 = self._channel("B", 57, 0, 1, 0x2)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0, ch1]

        d = HardwareDiscovery(api=api)
        channels = d.get_lin_channels()

        assert len(channels) == 2
        assert all(isinstance(c, LINChannel) for c in channels)

    def test_get_channel_info_returns_match(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x1)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0]

        d = HardwareDiscovery(api=api)
        info = d.get_channel_info(57, 0, 0)

        assert info.hw_type == 57
        assert info.hw_channel == 0

    def test_get_channel_info_raises_when_missing(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        with pytest.raises(LookupError):
            d.get_channel_info(57, 0, 0)

    def test_is_device_available_true(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x1)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0]

        d = HardwareDiscovery(api=api)
        assert d.is_device_available("057-000") is True

    def test_is_device_available_false_when_in_use(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        assert d.is_device_available("057-000") is False

    def test_scan_devices_deduplicates_channels(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("VN1610 CH0", 57, 0, 0, 0x1)
        # Duplicate same identity/channel index should be collapsed
        ch0_dup = self._channel("VN1610 CH0", 57, 0, 0, 0x1)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0, ch0_dup]

        d = HardwareDiscovery(api=api)
        devices = d.scan_devices()

        assert len(devices) == 1
        assert len(devices[0].channels) == 1

    def test_get_channel_by_index(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x1)
        ch1 = self._channel("B", 57, 0, 1, 0x2)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0, ch1]

        d = HardwareDiscovery(api=api)
        c = d.get_channel_by_index(1)
        assert c.hw_channel == 1

    def test_get_channel_by_index_missing_raises(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        with pytest.raises(LookupError):
            d.get_channel_by_index(99)

    def test_get_channel_by_mask(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x10)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0]

        d = HardwareDiscovery(api=api)
        c = d.get_channel_by_mask(0x10)
        assert c.hw_channel == 0

    def test_get_channel_by_mask_missing_raises(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        with pytest.raises(LookupError):
            d.get_channel_by_mask(0x20)

    def test_get_channels_for_device(self):
        api = MagicMock()
        cfg = MagicMock()
        ch0 = self._channel("A", 57, 0, 0, 0x1)
        ch1 = self._channel("B", 57, 0, 1, 0x2)
        ch2 = self._channel("C", 55, 1, 0, 0x4)
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch0, ch1, ch2]

        d = HardwareDiscovery(api=api)
        channels = d.get_channels_for_device(57, 0)
        assert len(channels) == 2
        assert all(c.hw_type == 57 and c.hw_index == 0 for c in channels)

    def test_get_channels_for_device_missing_raises(self):
        api = MagicMock()
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = []

        d = HardwareDiscovery(api=api)
        with pytest.raises(LookupError):
            d.get_channels_for_device(57, 0)
