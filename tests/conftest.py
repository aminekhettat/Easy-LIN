"""Shared pytest fixtures for communication backend tests.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:date: 2026-03-23
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.communication.hardware_discovery import LINChannel
from src.communication.lin_controller import LINController


@pytest.fixture
def mock_vxlapi():
    """Return a full mock of the Vector XL API wrapper."""
    api = MagicMock()
    api.receive_event.return_value = None
    return api


@pytest.fixture
def mock_driver_config():
    """Return a mocked XL driver config with two LIN channels."""
    cfg = MagicMock()
    cfg.channelCount = 2

    ch0 = MagicMock()
    ch0.name = b"VN1610 CH0\x00"
    ch0.hwType = 57
    ch0.hwIndex = 0
    ch0.hwChannel = 0
    ch0.channelIndex = 0
    ch0.channelMask = 0x1
    ch0.channelBusCapabilities = 0x00000200

    ch1 = MagicMock()
    ch1.name = b"VN1610 CH1\x00"
    ch1.hwType = 57
    ch1.hwIndex = 0
    ch1.hwChannel = 1
    ch1.channelIndex = 1
    ch1.channelMask = 0x2
    ch1.channelBusCapabilities = 0x00000200

    cfg.channel = [ch0, ch1]
    return cfg


@pytest.fixture
def mock_lin_channel() -> LINChannel:
    """Return a pre-configured LIN channel object for tests."""
    return LINChannel(
        name="VN1610 CH0",
        hw_type=57,
        hw_index=0,
        hw_channel=0,
        channel_index=0,
        channel_mask=0x1,
        device_serial="057-000",
    )


@pytest.fixture
def lin_controller(mock_vxlapi) -> LINController:
    """Return a LINController using a mocked Vector API."""
    return LINController(api=mock_vxlapi)
