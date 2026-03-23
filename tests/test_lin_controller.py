"""Tests for src.communication.lin_controller."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from src.communication.exceptions import LINError
from src.communication.hardware_discovery import LINChannel
from src.communication.lin_controller import (
    BUSStatistics,
    ChecksumMode,
    LINController,
    LINFrame,
    LINMode,
    ScheduleEntry,
)


def _channel() -> LINChannel:
    return LINChannel(
        name="VN1610 CH0",
        hw_type=57,
        hw_index=0,
        hw_channel=0,
        channel_index=0,
        channel_mask=0x1,
        device_serial="057-000",
    )


class TestLINController:  # pylint: disable=too-many-public-methods
    def test_connect_master_mode_success(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)

        api.open_driver.assert_called_once()
        api.activate_channel.assert_called_once()

    def test_connect_slave_mode_success(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.SLAVE)

        api.open_driver.assert_called_once()
        api.activate_channel.assert_called_once()

    def test_connect_no_hardware_raises(self):
        api = MagicMock()
        api.get_channel_mask.side_effect = RuntimeError("no hw")

        c = LINController(api=api)
        with pytest.raises(LINError):
            c.connect(_channel(), 19200, LINMode.MASTER)

    def test_connect_when_already_connected_raises(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        with pytest.raises(LINError):
            c.connect(_channel(), 19200, LINMode.MASTER)

    def test_disconnect_cleans_up_properly(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        c.disconnect()

        api.deactivate_channel.assert_called_once()
        api.close_port.assert_called_once()
        api.close_driver.assert_called()

    def test_disconnect_without_connect_raises(self):
        c = LINController(api=MagicMock())
        with pytest.raises(LINError):
            c.disconnect()

    def test_send_master_request_when_connected(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)

        c.send_master_request(0x10)

        api.lin_send_request.assert_called_once()

    def test_send_master_request_when_disconnected_raises(self):
        c = LINController(api=MagicMock())
        with pytest.raises(LINError):
            c.send_master_request(0x10)

    def test_send_slave_response_valid(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)

        c.send_slave_response(0x10, [1, 2, 3])

        api.lin_send_response.assert_called_once()

    def test_send_slave_response_wrong_dlc_raises(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)

        with pytest.raises(LINError):
            c.send_slave_response(0x10, [0] * 9)

    def test_receive_frame_returns_frame(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        evt = MagicMock()
        evt.tag = 14
        evt.timeStamp = 123
        msg = MagicMock()
        msg.id = 0x10
        msg.dlc = 2
        msg.data = [0xAA, 0xBB, 0, 0, 0, 0, 0, 0]
        evt.lin_msg = msg
        api.receive_event.side_effect = [evt]

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        frame = c.receive_frame(10)

        assert isinstance(frame, LINFrame)
        assert frame.frame_id == 0x10

    def test_receive_frame_ignores_non_lin_tag(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        evt = MagicMock()
        evt.tag = 99

        calls = {"count": 0}

        def _receive_event(_handle):
            if calls["count"] == 0:
                calls["count"] += 1
                return evt
            return None

        api.receive_event.side_effect = _receive_event

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        frame = c.receive_frame(5)

        assert frame is None

    def test_receive_frame_timeout_returns_none(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1
        api.receive_event.return_value = None

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        frame = c.receive_frame(5)

        assert frame is None

    def test_start_scheduler_sends_all_entries(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)

        schedule = [
            ScheduleEntry(frame_id=0x10, dlc=0, data=[]),
            ScheduleEntry(frame_id=0x11, dlc=2, data=[1, 2]),
        ]
        c.start_scheduler(schedule, 1)
        time.sleep(0.01)
        c.stop_scheduler()

        assert api.lin_send_request.called or api.lin_send_response.called

    def test_stop_scheduler_stops_thread(self):
        c = LINController(api=MagicMock())
        c._sched_thread = threading.Thread(target=lambda: None)
        c._sched_thread.start()
        c.stop_scheduler()
        assert c._sched_thread is None

    def test_scheduler_loop_master_request_branch(self):
        c = LINController(api=MagicMock())
        calls = {"count": 0}

        def _send_master_request(_frame_id):
            calls["count"] += 1
            c._sched_stop.set()

        c.send_master_request = _send_master_request
        c._sched_stop.clear()
        c._scheduler_loop([ScheduleEntry(frame_id=0x10, dlc=0, data=[])], 1)

        assert calls["count"] == 1

    def test_scheduler_loop_wait_sleep_branch(self, monkeypatch):
        c = LINController(api=MagicMock())
        c.send_master_request = MagicMock()
        c._sched_stop.clear()

        def _sleep(_seconds):
            c._sched_stop.set()

        monkeypatch.setattr("src.communication.lin_controller.time.sleep", _sleep)
        c._scheduler_loop([ScheduleEntry(frame_id=0x10, dlc=0, data=[])], 2)

        c.send_master_request.assert_called_once_with(0x10)

    def test_set_checksum_classic(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        c.set_checksum_mode(0x10, ChecksumMode.CLASSIC)
        api.lin_set_checksum_info.assert_called()

    def test_set_checksum_enhanced(self):
        api = MagicMock()
        api.open_port.return_value = (10, 1)
        api.get_channel_mask.return_value = 1

        c = LINController(api=api)
        c.connect(_channel(), 19200, LINMode.MASTER)
        c.set_checksum_mode(0x10, ChecksumMode.ENHANCED)
        api.lin_set_checksum_info.assert_called()

    def test_set_checksum_invalid_id_raises(self):
        c = LINController(api=MagicMock())
        with pytest.raises(LINError):
            c.set_checksum_mode(64, ChecksumMode.CLASSIC)

    def test_get_bus_statistics(self):
        c = LINController(api=MagicMock())
        stats = c.get_bus_statistics()
        assert isinstance(stats, BUSStatistics)
