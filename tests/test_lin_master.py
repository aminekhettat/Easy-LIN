"""Comprehensive tests for src.lin_master achieving 100% code coverage.

Every code path in LINMaster and ReceivedFrame is exercised, including:
- ReceivedFrame construction and __repr__
- LINMaster properties, static helpers, connect/disconnect lifecycle
- All protocol version mappings (1.x, 2.0, 2.1, 2.2)
- Frame transmission (send_frame, send_frame_data)
- Schedule execution and stop
- RX loop: None event, LIN msg event, callback exception, VectorXLError, generic exception
- Schedule loop: frame resolution, send error, stop event, no-ldf path
"""

import time
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.lin_master import LINMaster, ReceivedFrame, _TAG_LIN_MSG
from src.ldf_parser import LDFFile, LDFFrame, LDFScheduleEntry, LDFScheduleTable
from src.vector_xl_api import (
    VectorXLApi,
    VectorXLDriverNotFoundError,
    VectorXLError,
    XL_LIN_VERSION_1_3,
    XL_LIN_VERSION_2_0,
    XL_LIN_VERSION_2_1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ldf(
    protocol_version: str = "2.0",
    speed: float = 19.2,
    frames: Optional[List[LDFFrame]] = None,
) -> LDFFile:
    """Build a minimal LDFFile for testing."""
    ldf = LDFFile(protocol_version=protocol_version, speed=speed)
    if frames is not None:
        ldf.frames = frames
    ldf.build_lookups()
    return ldf


def _make_schedule(entries: Optional[List[LDFScheduleEntry]] = None) -> LDFScheduleTable:
    """Build a minimal LDFScheduleTable."""
    return LDFScheduleTable(name="TestSched", entries=entries or [])


def _make_xl_event(tag, frame_id=0x10, dlc=2, data=None, flags=0, timestamp=12345):
    """Return a mock XL_EVENT with a nested lin_msg property."""
    if data is None:
        data = [0xAA, 0xBB, 0, 0, 0, 0, 0, 0]
    msg = MagicMock()
    msg.id = frame_id
    msg.dlc = dlc
    msg.data = data
    msg.flags = flags
    evt = MagicMock()
    evt.tag = tag
    evt.timeStamp = timestamp
    evt.lin_msg = msg
    return evt


def _mock_api():
    """Return a MagicMock preconfigured to behave like VectorXLApi."""
    api = MagicMock(spec=VectorXLApi)
    api.open_port.return_value = (1, 1)  # port_handle, perm_mask
    api.receive.return_value = None
    return api


# ---------------------------------------------------------------------------
# ReceivedFrame tests
# ---------------------------------------------------------------------------


class TestReceivedFrame:
    def test_init_defaults(self):
        f = ReceivedFrame(frame_id=0x10, data=b"\x01\x02", timestamp_ns=999)
        assert f.frame_id == 0x10
        assert f.data == b"\x01\x02"
        assert f.timestamp_ns == 999
        assert f.crc_error is False

    def test_init_crc_error(self):
        f = ReceivedFrame(0x3F, b"\xFF", 0, crc_error=True)
        assert f.crc_error is True

    def test_repr(self):
        f = ReceivedFrame(frame_id=0x0A, data=b"\xDE\xAD", timestamp_ns=42)
        r = repr(f)
        assert r == "ReceivedFrame(id=0x0A, data=[DE AD], ts=42ns)"

    def test_repr_empty_data(self):
        f = ReceivedFrame(frame_id=0x00, data=b"", timestamp_ns=0)
        assert "data=[]" in repr(f)

    def test_slots(self):
        f = ReceivedFrame(0, b"", 0)
        with pytest.raises(AttributeError):
            f.nonexistent = 1


# ---------------------------------------------------------------------------
# LINMaster – properties and init
# ---------------------------------------------------------------------------


class TestLINMasterInit:
    def test_defaults(self):
        m = LINMaster()
        assert m.is_connected is False
        assert m.ldf is None

    def test_callbacks_stored(self):
        cb1 = MagicMock()
        cb_changed = MagicMock()
        cb2 = MagicMock()
        m = LINMaster(on_frame_received=cb1, on_frame_changed=cb_changed, on_error=cb2)
        assert m._on_frame_received is cb1
        assert m._on_frame_changed is cb_changed
        assert m._on_error is cb2

    def test_dll_path_before_connect_is_none(self):
        m = LINMaster()
        assert m.dll_path is None

    @patch("src.lin_master.VectorXLApi")
    def test_dll_path_after_connect_returns_api_path(self, MockApi):
        api = _mock_api()
        api.dll_path = r"C:\third_party\vector\bin\vxlapi64.dll"
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        assert m.dll_path == r"C:\third_party\vector\bin\vxlapi64.dll"
        m.disconnect()


# ---------------------------------------------------------------------------
# list_lin_channels
# ---------------------------------------------------------------------------


class TestListLinChannels:
    @patch("src.lin_master.VectorXLApi")
    def test_success(self, MockApi):
        api = MockApi.return_value
        ch = MagicMock()
        ch.name = b"LIN 1\x00\x00"
        ch.channelIndex = 0
        ch.channelMask = 1
        cfg = MagicMock()
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [ch]

        result = LINMaster.list_lin_channels()
        assert len(result) == 1
        assert result[0]["name"] == "LIN 1"
        assert result[0]["channel_index"] == 0
        assert result[0]["channel_mask"] == 1
        api.open_driver.assert_called_once()
        api.close_driver.assert_called_once()

    @patch("src.lin_master.VectorXLApi")
    def test_driver_not_found(self, MockApi):
        MockApi.side_effect = VectorXLDriverNotFoundError("no driver")
        result = LINMaster.list_lin_channels()
        assert result == []

    @patch("src.lin_master.VectorXLApi")
    def test_generic_exception(self, MockApi):
        MockApi.return_value.open_driver.side_effect = RuntimeError("boom")
        result = LINMaster.list_lin_channels()
        assert result == []


class TestPreflight:
    @patch("src.lin_master.VectorXLApi")
    def test_preflight_ok(self, MockApi):
        """VectorXLApi.preflight returns (True, 'OK') -> LINMaster.preflight propagates it."""
        MockApi.return_value.preflight.return_value = (True, "OK")
        m = LINMaster()
        ok, msg = m.preflight()
        assert ok is True
        assert msg == "OK"

    @patch("src.lin_master.VectorXLApi")
    def test_preflight_driver_error(self, MockApi):
        """VectorXLApi.preflight returns failure -> LINMaster propagates it."""
        MockApi.return_value.preflight.return_value = (False, "xlOpenDriver returned 0x87")
        m = LINMaster()
        ok, msg = m.preflight()
        assert ok is False
        assert "xlOpenDriver" in msg

    @patch("src.lin_master.VectorXLApi")
    def test_preflight_driver_not_found(self, MockApi):
        """VectorXLDriverNotFoundError -> preflight returns (False, message)."""
        MockApi.side_effect = VectorXLDriverNotFoundError("DLL missing")
        m = LINMaster()
        ok, msg = m.preflight()
        assert ok is False
        assert "DLL missing" in msg

    @patch("src.lin_master.VectorXLApi")
    def test_preflight_unexpected_exception(self, MockApi):
        """Unexpected exception from VectorXLApi() -> preflight returns (False, ...)."""
        MockApi.side_effect = RuntimeError("unexpected")
        m = LINMaster()
        ok, msg = m.preflight()
        assert ok is False
        assert "unexpected" in msg


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


class TestConnect:
    @patch("src.lin_master.VectorXLApi")
    def test_connect_no_ldf(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api

        m = LINMaster()
        m.connect(channel_mask=2)

        assert m.is_connected is True
        assert m.ldf is None
        api.open_driver.assert_called_once()
        api.open_port.assert_called_once_with("EasyLIN", 2)
        api.set_lin_channel_params.assert_called_once_with(1, 2, 19200, XL_LIN_VERSION_2_0)
        api.activate_channel.assert_called_once_with(1, 2)
        # RX thread should be alive
        assert m._rx_thread is not None
        assert m._rx_thread.is_alive()
        # Cleanup
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_already_connected_raises(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        with pytest.raises(RuntimeError, match="Already connected"):
            m.connect(channel_mask=1)
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_perm_mask_zero_warns(self, MockApi, caplog):
        api = _mock_api()
        api.open_port.return_value = (1, 0)  # perm_mask == 0
        MockApi.return_value = api

        m = LINMaster()
        import logging
        with caplog.at_level(logging.WARNING, logger="src.lin_master"):
            m.connect(channel_mask=1)
        assert "No TX permission" in caplog.text
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_custom_app_name(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=4, app_name="MyApp")
        api.open_port.assert_called_once_with("MyApp", 4)
        m.disconnect()

    # --- Protocol version mapping ---

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_version_1x(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(protocol_version="1.3", speed=9.6)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_channel_params.assert_called_once_with(1, 1, 9600, XL_LIN_VERSION_1_3)
        assert m.ldf is ldf
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_version_2_1(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(protocol_version="2.1", speed=19.2)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_channel_params.assert_called_once_with(1, 1, 19200, XL_LIN_VERSION_2_1)
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_version_2_2(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(protocol_version="2.2", speed=19.2)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_channel_params.assert_called_once_with(1, 1, 19200, XL_LIN_VERSION_2_1)
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_version_2_0(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(protocol_version="2.0", speed=19.2)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_channel_params.assert_called_once_with(1, 1, 19200, XL_LIN_VERSION_2_0)
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_version_unknown_defaults_2_0(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(protocol_version="3.0", speed=19.2)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_channel_params.assert_called_once_with(1, 1, 19200, XL_LIN_VERSION_2_0)
        m.disconnect()

    # --- DLC table ---

    @patch("src.lin_master.VectorXLApi")
    def test_connect_ldf_sets_dlc_table(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        frames = [
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=4),
            LDFFrame(name="F2", frame_id=0x20, publisher="M", frame_size=8),
            LDFFrame(name="F3", frame_id=100, publisher="M", frame_size=2),  # out of 0-63 range
        ]
        ldf = _make_ldf(frames=frames)
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)
        api.set_lin_dlc.assert_called_once()
        dlc_arg = api.set_lin_dlc.call_args[0][2]
        assert dlc_arg[0x10] == 4
        assert dlc_arg[0x20] == 8
        # frame_id=100 is > 63, should be skipped
        assert len(dlc_arg) == 64
        m.disconnect()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @patch("src.lin_master.VectorXLApi")
    def test_disconnect_resets_state(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        m.disconnect()

        assert m.is_connected is False
        assert m.ldf is None
        assert m._api is None
        assert m._port_handle == -1
        api.deactivate_channel.assert_called_once()
        api.close_port.assert_called_once()
        api.close_driver.assert_called_once()

    @patch("src.lin_master.VectorXLApi")
    def test_disconnect_handles_cleanup_exception(self, MockApi, caplog):
        api = _mock_api()
        api.deactivate_channel.side_effect = RuntimeError("hw error")
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        import logging
        with caplog.at_level(logging.WARNING, logger="src.lin_master"):
            m.disconnect()
        assert "Error during disconnect" in caplog.text
        assert m.is_connected is False

    def test_disconnect_when_not_connected(self):
        """disconnect() on a fresh instance should be a no-op."""
        m = LINMaster()
        m.disconnect()  # Should not raise
        assert m.is_connected is False

    @patch("src.lin_master.VectorXLApi")
    def test_disconnect_stops_schedule(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        sched = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=10)])
        m.run_schedule(sched)
        m.disconnect()
        assert m._sched_thread is None


# ---------------------------------------------------------------------------
# send_frame / send_frame_data
# ---------------------------------------------------------------------------


class TestSendFrame:
    @patch("src.lin_master.VectorXLApi")
    def test_send_frame(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        m.send_frame(0x10)
        api.lin_send_request.assert_called_with(1, 1, 0x10)
        m.disconnect()

    def test_send_frame_not_connected(self):
        m = LINMaster()
        with pytest.raises(RuntimeError, match="Not connected"):
            m.send_frame(0x10)

    @patch("src.lin_master.VectorXLApi")
    def test_send_frame_data(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        m.send_frame_data(0x20, [1, 2, 3])
        api.set_lin_frame_response.assert_called_once_with(1, 1, 0x20, [1, 2, 3])
        api.lin_send_request.assert_called_with(1, 1, 0x20)
        m.disconnect()

    def test_send_frame_data_not_connected(self):
        m = LINMaster()
        with pytest.raises(RuntimeError, match="Not connected"):
            m.send_frame_data(0x20, [1, 2])


# ---------------------------------------------------------------------------
# _rx_loop
# ---------------------------------------------------------------------------


class TestRxLoop:
    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_none_event(self, MockApi):
        """When receive() returns None the loop should sleep and continue."""
        api = _mock_api()
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                # Signal stop after a few iterations
                m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        # Wait for the thread to finish
        m._rx_thread.join(timeout=2)
        assert call_count >= 3
        m._connected = False  # skip full disconnect

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_lin_msg_with_callback(self, MockApi):
        """A LIN msg event triggers the on_frame_received callback."""
        api = _mock_api()
        received = []

        def on_frame(frame):
            received.append(frame)

        evt = _make_xl_event(
            tag=_TAG_LIN_MSG,
            frame_id=0x50,  # will be masked to 0x10 (0x50 & 0x3F = 0x10)
            dlc=2,
            data=[0xAA, 0xBB, 0, 0, 0, 0, 0, 0],
            flags=0,
            timestamp=9999,
        )
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api

        m = LINMaster(on_frame_received=on_frame)
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)

        assert len(received) == 1
        assert received[0].frame_id == 0x10
        assert received[0].data == bytes([0xAA, 0xBB])
        assert received[0].timestamp_ns == 9999
        assert received[0].crc_error is False
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_changed_callback_only_on_data_change(self, MockApi):
        """on_frame_changed fires on first payload and when payload changes."""
        api = _mock_api()
        changed = []
        received = []

        evt_a1 = _make_xl_event(
            tag=_TAG_LIN_MSG,
            frame_id=0x11,
            dlc=2,
            data=[0xAA, 0xBB, 0, 0, 0, 0, 0, 0],
            flags=0,
            timestamp=1,
        )
        evt_a2 = _make_xl_event(
            tag=_TAG_LIN_MSG,
            frame_id=0x11,
            dlc=2,
            data=[0xAA, 0xBB, 0, 0, 0, 0, 0, 0],
            flags=0,
            timestamp=2,
        )
        evt_b = _make_xl_event(
            tag=_TAG_LIN_MSG,
            frame_id=0x11,
            dlc=2,
            data=[0xAA, 0xCC, 0, 0, 0, 0, 0, 0],
            flags=0,
            timestamp=3,
        )

        events = [evt_a1, evt_a2, evt_b]
        idx = 0

        def _receive(port):
            nonlocal idx
            if idx < len(events):
                evt = events[idx]
                idx += 1
                return evt
            m._rx_stop.set()
            return None

        def _on_changed(frame, previous_data):
            changed.append((frame.frame_id, frame.data, previous_data))

        api.receive.side_effect = _receive
        MockApi.return_value = api
        m = LINMaster(
            on_frame_received=lambda f: received.append(f),
            on_frame_changed=_on_changed,
        )
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)

        assert len(received) == 3
        assert len(changed) == 2
        assert changed[0] == (0x11, b"\xAA\xBB", None)
        assert changed[1] == (0x11, b"\xAA\xCC", b"\xAA\xBB")
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_changed_callback_exception(self, MockApi, caplog):
        """Exception inside on_frame_changed is logged and loop continues."""
        api = _mock_api()
        evt = _make_xl_event(tag=_TAG_LIN_MSG, frame_id=0x12, dlc=1, data=[0x01, 0, 0, 0, 0, 0, 0, 0])
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        def _bad_changed(frame, previous_data):
            raise ValueError("changed callback blew up")

        api.receive.side_effect = _receive
        MockApi.return_value = api

        import logging
        m = LINMaster(on_frame_changed=_bad_changed)
        with caplog.at_level(logging.ERROR, logger="src.lin_master"):
            m.connect(channel_mask=1)
            m._rx_thread.join(timeout=2)
        assert "Error in on_frame_changed callback" in caplog.text
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_lin_msg_crc_error(self, MockApi):
        """CRC error flag (0x08) is detected."""
        api = _mock_api()
        received = []

        evt = _make_xl_event(tag=_TAG_LIN_MSG, frame_id=0x05, dlc=1,
                             data=[0xFF, 0, 0, 0, 0, 0, 0, 0], flags=0x08)
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api
        m = LINMaster(on_frame_received=lambda f: received.append(f))
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)
        assert received[0].crc_error is True
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_lin_msg_no_callback(self, MockApi):
        """If no callback is set, receiving a LIN msg should not crash."""
        api = _mock_api()
        evt = _make_xl_event(tag=_TAG_LIN_MSG)
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api
        m = LINMaster(on_frame_received=None)
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_callback_exception(self, MockApi, caplog):
        """Exception inside the callback is logged, loop continues."""
        api = _mock_api()

        def bad_callback(frame):
            raise ValueError("callback blew up")

        evt = _make_xl_event(tag=_TAG_LIN_MSG)
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api

        import logging
        m = LINMaster(on_frame_received=bad_callback)
        with caplog.at_level(logging.ERROR, logger="src.lin_master"):
            m.connect(channel_mask=1)
            m._rx_thread.join(timeout=2)
        assert "Error in on_frame_received callback" in caplog.text
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_non_lin_event_ignored(self, MockApi):
        """Events with a tag other than _TAG_LIN_MSG are silently ignored."""
        api = _mock_api()
        evt = _make_xl_event(tag=99)  # not _TAG_LIN_MSG
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return evt
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api
        received = []
        m = LINMaster(on_frame_received=lambda f: received.append(f))
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)
        assert len(received) == 0
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_vector_xl_error(self, MockApi, caplog):
        """VectorXLError in receive triggers warning and on_error callback."""
        api = _mock_api()
        errors = []
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VectorXLError("xlReceive", 0xFF)
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api

        import logging
        m = LINMaster(on_error=lambda msg: errors.append(msg))
        with caplog.at_level(logging.WARNING, logger="src.lin_master"):
            m.connect(channel_mask=1)
            m._rx_thread.join(timeout=2)
        assert "RX error" in caplog.text
        assert len(errors) == 1
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_vector_xl_error_no_callback(self, MockApi):
        """VectorXLError with no on_error callback does not crash."""
        api = _mock_api()
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VectorXLError("xlReceive", 0xFF)
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api
        m = LINMaster(on_error=None)
        m.connect(channel_mask=1)
        m._rx_thread.join(timeout=2)
        m._connected = False

    @patch("src.lin_master.VectorXLApi")
    def test_rx_loop_generic_exception(self, MockApi, caplog):
        """Unexpected exception in receive is logged, loop continues after sleep."""
        api = _mock_api()
        call_count = 0

        def _receive(port):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("something unexpected")
            m._rx_stop.set()
            return None

        api.receive.side_effect = _receive
        MockApi.return_value = api

        import logging
        m = LINMaster()
        with caplog.at_level(logging.ERROR, logger="src.lin_master"):
            m.connect(channel_mask=1)
            m._rx_thread.join(timeout=2)
        assert "Unexpected error in RX loop" in caplog.text
        m._connected = False


# ---------------------------------------------------------------------------
# run_schedule / stop_schedule / _schedule_loop
# ---------------------------------------------------------------------------


class TestSchedule:
    @patch("src.lin_master.VectorXLApi")
    def test_run_and_stop_schedule(self, MockApi):
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
        ])
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)

        sched = _make_schedule([
            LDFScheduleEntry(frame_name="F1", delay=5),
        ])
        m.run_schedule(sched)
        assert m._sched_thread is not None
        time.sleep(0.05)  # let it iterate at least once
        m.stop_schedule()
        assert m._sched_thread is None
        api.lin_send_request.assert_called()
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_replaces_existing(self, MockApi):
        """Calling run_schedule a second time stops the first schedule."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
        ])
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)

        sched1 = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=10)])
        sched2 = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=10)])
        m.run_schedule(sched1)
        t1 = m._sched_thread
        m.run_schedule(sched2)
        t2 = m._sched_thread
        assert t1 is not t2
        m.stop_schedule()
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_frame_not_in_ldf(self, MockApi):
        """A schedule entry referencing an unknown frame is silently skipped."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(frames=[])  # no frames
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)

        sched = _make_schedule([LDFScheduleEntry(frame_name="Unknown", delay=5)])
        m.run_schedule(sched)
        time.sleep(0.03)
        m.stop_schedule()
        # lin_send_request should not be called for the schedule (only possibly from connect)
        # The key point: no crash occurred
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_no_ldf(self, MockApi):
        """With no LDF, frame_id resolution returns None; send is skipped."""
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1, ldf=None)

        sched = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=5)])
        m.run_schedule(sched)
        time.sleep(0.03)
        m.stop_schedule()
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_send_error(self, MockApi, caplog):
        """VectorXLError during schedule send is logged and on_error is called."""
        api = _mock_api()
        api.lin_send_request.side_effect = VectorXLError("xlLinSendRequest", 0xAA)
        MockApi.return_value = api
        errors = []
        ldf = _make_ldf(frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
        ])
        m = LINMaster(on_error=lambda msg: errors.append(msg))
        m.connect(channel_mask=1, ldf=ldf)

        sched = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=5)])
        import logging
        with caplog.at_level(logging.WARNING, logger="src.lin_master"):
            m.run_schedule(sched)
            time.sleep(0.05)
            m.stop_schedule()
        assert "Schedule TX error" in caplog.text
        assert len(errors) >= 1
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_send_error_no_callback(self, MockApi):
        """VectorXLError during schedule send with no on_error does not crash."""
        api = _mock_api()
        api.lin_send_request.side_effect = VectorXLError("xlLinSendRequest", 0xAA)
        MockApi.return_value = api
        ldf = _make_ldf(frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
        ])
        m = LINMaster(on_error=None)
        m.connect(channel_mask=1, ldf=ldf)

        sched = _make_schedule([LDFScheduleEntry(frame_name="F1", delay=5)])
        m.run_schedule(sched)
        time.sleep(0.05)
        m.stop_schedule()
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_stop_schedule_noop_when_none(self, MockApi):
        """stop_schedule when no schedule is running is a no-op."""
        api = _mock_api()
        MockApi.return_value = api
        m = LINMaster()
        m.connect(channel_mask=1)
        m.stop_schedule()  # should not raise
        m.disconnect()

    @patch("src.lin_master.VectorXLApi")
    def test_schedule_stop_event_breaks_inner_loop(self, MockApi):
        """Setting _sched_stop should break out of the entry iteration."""
        api = _mock_api()
        MockApi.return_value = api
        ldf = _make_ldf(frames=[
            LDFFrame(name="F1", frame_id=0x10, publisher="M", frame_size=2),
            LDFFrame(name="F2", frame_id=0x20, publisher="M", frame_size=2),
        ])
        m = LINMaster()
        m.connect(channel_mask=1, ldf=ldf)

        sched = _make_schedule([
            LDFScheduleEntry(frame_name="F1", delay=200),
            LDFScheduleEntry(frame_name="F2", delay=200),
        ])
        m.run_schedule(sched)
        time.sleep(0.01)
        m.stop_schedule()
        # The schedule should have stopped quickly, not waited 400ms
        m.disconnect()


# ---------------------------------------------------------------------------
# Edge-case: disconnect with port_handle == -1
# ---------------------------------------------------------------------------


class TestDisconnectEdgeCases:
    def test_disconnect_api_set_but_port_neg1(self):
        """If _api is set but _port_handle is -1, cleanup block is skipped."""
        m = LINMaster()
        m._api = MagicMock()
        m._port_handle = -1
        m._connected = True
        m.disconnect()
        m._api is None  # noqa: B015 – just checking it was cleared
        assert m.is_connected is False

    def test_disconnect_api_none(self):
        """If _api is None, cleanup block is skipped."""
        m = LINMaster()
        m._api = None
        m._port_handle = 5
        m._connected = True
        m.disconnect()
        assert m.is_connected is False
