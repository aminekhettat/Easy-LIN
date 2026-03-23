"""Comprehensive tests for src/vector_xl_api.py.

Achieves 100% code-path coverage by mocking platform.system, ctypes.WinDLL,
and ctypes.util.find_library so that the test suite runs on any OS without
the Vector XL Driver DLL installed.

:author: Amine Khettat
:company: BLIND SYSTEMS
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import helpers -- ensure the src/ directory is on sys.path before anything
# else so that ``import vector_xl_api`` resolves correctly.
# ---------------------------------------------------------------------------

import sys
import os

# Ensure the src/ directory is importable
_src = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src",
)
if _src not in sys.path:
    sys.path.insert(0, _src)


# ---------------------------------------------------------------------------
# Helpers -- build a fake DLL that every VectorXLApi method can call
# ---------------------------------------------------------------------------


class FakeDLL:
    """Simulates the vxlapi64.dll / vxlapi.dll surface used by VectorXLApi.

    Every XL function is a MagicMock whose return_value defaults to 0
    (XL_SUCCESS).  Individual tests can override return values to exercise
    error paths.
    """

    def __init__(self):
        self.xlOpenDriver = MagicMock(return_value=0)
        self.xlCloseDriver = MagicMock(return_value=0)
        self.xlGetDriverConfig = MagicMock(return_value=0)
        self.xlOpenPort = MagicMock(return_value=0)
        self.xlClosePort = MagicMock(return_value=0)
        self.xlActivateChannel = MagicMock(return_value=0)
        self.xlDeactivateChannel = MagicMock(return_value=0)
        self.xlLinSetChannelParams = MagicMock(return_value=0)
        self.xlLinSetDLC = MagicMock(return_value=0)
        self.xlLinSetFrameResponse = MagicMock(return_value=0)
        self.xlLinSendRequest = MagicMock(return_value=0)
        self.xlReceive = MagicMock(return_value=0)
        self.xlSetNotification = MagicMock(return_value=0)
        self.xlSetTimerRate = MagicMock(return_value=0)
        self.xlLinSetChecksum = MagicMock(return_value=0)
        self.xlGetErrorString = MagicMock(return_value=b"OK")


def _make_api(fake_dll=None):
    """Construct a VectorXLApi with the DLL loading completely bypassed.

    Bypasses __init__ (which would call _load_dll) by using __new__, then
    directly assigns the FakeDLL and calls _setup_prototypes.  The prototype
    setup only does ``getattr(dll, name).restype = ...`` which works fine
    on MagicMock attributes.
    """
    if fake_dll is None:
        fake_dll = FakeDLL()
    import vector_xl_api as mod
    api = mod.VectorXLApi.__new__(mod.VectorXLApi)
    api._dll = fake_dll
    api._setup_prototypes()
    return api, fake_dll

import vector_xl_api as vxl  # noqa: E402
from vector_xl_api import (  # noqa: E402
    VectorXLApi,
    VectorXLDriverNotFoundError,
    VectorXLError,
    XL_BUS_TYPE_LIN,
    XL_CHANNEL_CONFIG,
    XL_CONFIG_MAX_CHANNELS,
    XL_DRIVER_CONFIG,
    XL_ERR_WRONG_PARAMETER,
    XL_ERR_NO_LICENSE,
    XL_ERR_QUEUE_IS_EMPTY,
    XL_EVENT,
    XL_HARDWARE_NOT_PRESENT,
    XL_LIN_MASTER,
    XL_LIN_CHECKSUM_CLASSIC,
    XL_LIN_CHECKSUM_ENHANCED,
    XL_LIN_MSG,
    XL_LIN_STAT_PARAM,
    XL_LIN_VERSION_2_0,
    XL_PENDING,
    XL_SUCCESS,
)


# ===================================================================
# 1. Constants
# ===================================================================


class TestConstants:
    def test_xl_success(self):
        assert XL_SUCCESS == 0

    def test_xl_pending(self):
        assert XL_PENDING == 1

    def test_xl_err_queue_is_empty(self):
        assert XL_ERR_QUEUE_IS_EMPTY == 10

    def test_xl_err_no_license(self):
        assert XL_ERR_NO_LICENSE == 135

    def test_xl_hardware_not_present(self):
        assert XL_HARDWARE_NOT_PRESENT == 129

    def test_xl_bus_type_lin(self):
        assert XL_BUS_TYPE_LIN == 0x00000200

    def test_xl_lin_master(self):
        assert XL_LIN_MASTER == 1

    def test_lin_version_2_0(self):
        assert XL_LIN_VERSION_2_0 == 0x20

    def test_checksum_constants(self):
        assert XL_LIN_CHECKSUM_CLASSIC == 0
        assert XL_LIN_CHECKSUM_ENHANCED == 1


# ===================================================================
# 2. Structures
# ===================================================================


class TestStructures:
    def test_xl_lin_stat_param_fields(self):
        p = XL_LIN_STAT_PARAM(LINMode=1, baudrate=19200, LINVersion=0x20, reserved=0)
        assert p.LINMode == 1
        assert p.baudrate == 19200
        assert p.LINVersion == 0x20

    def test_xl_lin_msg_fields(self):
        msg = XL_LIN_MSG()
        msg.id = 0x10
        msg.dlc = 4
        msg.data[0] = 0xAA
        assert msg.id == 0x10
        assert msg.dlc == 4
        assert msg.data[0] == 0xAA

    def test_xl_channel_config_instantiation(self):
        ch = XL_CHANNEL_CONFIG()
        ch.channelBusCapabilities = XL_BUS_TYPE_LIN
        assert ch.channelBusCapabilities == XL_BUS_TYPE_LIN

    def test_xl_driver_config_instantiation(self):
        cfg = XL_DRIVER_CONFIG()
        cfg.channelCount = 2
        assert cfg.channelCount == 2
        assert len(cfg.channel) == XL_CONFIG_MAX_CHANNELS

    def test_xl_event_basic(self):
        evt = XL_EVENT()
        evt.tag = 5
        evt.chanIndex = 1
        assert evt.tag == 5
        assert evt.chanIndex == 1


class TestXLEventLinMsg:
    """Cover the XL_EVENT.lin_msg property."""

    def test_lin_msg_property_returns_xl_lin_msg(self):
        evt = XL_EVENT()
        # Write a known id byte at offset 0 of _raw (matches XL_LIN_MSG.id)
        evt._raw[0] = 0x3C
        # dlc at offset 1
        evt._raw[1] = 8
        lin = evt.lin_msg
        assert isinstance(lin, XL_LIN_MSG)
        assert lin.id == 0x3C
        assert lin.dlc == 8

    def test_lin_msg_data_bytes(self):
        evt = XL_EVENT()
        # XL_LIN_MSG layout (pack=1): id(1) dlc(1) flags(2) data(8)
        for i in range(8):
            evt._raw[4 + i] = i + 1
        lin = evt.lin_msg
        for i in range(8):
            assert lin.data[i] == i + 1


# ===================================================================
# 3. Exception classes
# ===================================================================


class TestVectorXLDriverNotFoundError:
    def test_is_runtime_error(self):
        err = VectorXLDriverNotFoundError("missing")
        assert isinstance(err, RuntimeError)
        assert "missing" in str(err)


class TestVectorXLError:
    def test_stores_func_name_and_status(self):
        err = VectorXLError("xlOpenDriver", 0x87)
        assert err.func_name == "xlOpenDriver"
        assert err.status == 0x87

    def test_message_format(self):
        err = VectorXLError("xlFoo", 42)
        assert "xlFoo" in str(err)
        assert "42" in str(err) or "0x2a" in str(err)

    def test_is_runtime_error(self):
        assert issubclass(VectorXLError, RuntimeError)


# ===================================================================
# 4. _load_dll -- DLL discovery logic
# ===================================================================


class TestLoadDll:
    """Test the static _load_dll method with various platform / discovery scenarios."""

    def test_non_windows_raises(self):
        with patch.object(vxl.platform, "system", return_value="Linux"):
            with pytest.raises(VectorXLDriverNotFoundError, match="only available on Windows"):
                VectorXLApi._load_dll()

    def test_find_library_returns_path_64bit(self):
        sentinel = MagicMock(name="loaded_dll")
        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", return_value="C:\\vxlapi64.dll"), \
             patch.object(vxl.ctypes, "WinDLL", return_value=sentinel) as win_dll:
            result = VectorXLApi._load_dll()
            assert result is sentinel
            win_dll.assert_called_once()
            called_path = win_dll.call_args.args[0].lower()
            assert called_path.endswith("vxlapi64.dll")

    def test_find_library_first_fails_second_succeeds(self):
        """vxlapi64 not found by find_library, vxlapi found."""
        sentinel = MagicMock(name="dll32")

        def fake_find(name):
            if name == "vxlapi64":
                return None
            return "C:\\vxlapi.dll"

        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", side_effect=fake_find), \
             patch.object(vxl.ctypes, "WinDLL", return_value=sentinel):
            result = VectorXLApi._load_dll()
            assert result is sentinel

    def test_find_library_path_but_windll_raises(self):
        """find_library returns a path but WinDLL raises OSError -- fall through."""
        sentinel = MagicMock(name="fallback_dll")
        call_count = {"n": 0}

        def fake_find(name):
            return f"C:\\{name}.dll"

        def fake_windll(path):
            call_count["n"] += 1
            # First two calls (find_library paths) fail, then a fallback path works
            if call_count["n"] <= 2:
                raise OSError("cannot load")
            return sentinel

        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", side_effect=fake_find), \
             patch.object(vxl.ctypes, "WinDLL", side_effect=fake_windll):
            result = VectorXLApi._load_dll()
            assert result is sentinel

    def test_fallback_paths_tried_when_find_library_returns_none(self):
        """find_library returns None, fallback installation paths are tried."""
        sentinel = MagicMock(name="fallback")

        def fake_find(name):
            return None

        def fake_windll(path):
            # Accept only the very last fallback path
            if "Program Files (x86)" in path and "vxlapi.dll" in path:
                return sentinel
            raise OSError("not here")

        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", side_effect=fake_find), \
             patch.object(vxl.ctypes, "WinDLL", side_effect=fake_windll):
            result = VectorXLApi._load_dll()
            assert result is sentinel

    def test_all_paths_fail_raises(self):
        """Neither find_library nor fallback paths work."""
        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", return_value=None), \
             patch.object(vxl.ctypes, "WinDLL", side_effect=OSError("nope")):
            with pytest.raises(VectorXLDriverNotFoundError, match="vxlapi.dll not found"):
                VectorXLApi._load_dll()

    def test_find_library_path_oserror_then_fallback_works(self):
        """find_library returns a path for vxlapi64, WinDLL raises OSError,
        then the standard-path fallback for vxlapi64 succeeds."""
        sentinel = MagicMock(name="fallback_64")

        def fake_find(name):
            if name == "vxlapi64":
                return "C:\\found_vxlapi64.dll"
            return None

        def fake_windll(path):
            if path == "C:\\found_vxlapi64.dll":
                raise OSError("bad dll")
            if "Public" in path and "vxlapi64" in path:
                return sentinel
            raise OSError("nope")

        with patch.object(vxl.platform, "system", return_value="Windows"), \
             patch.object(vxl.ctypes.util, "find_library", side_effect=fake_find), \
             patch.object(vxl.ctypes, "WinDLL", side_effect=fake_windll):
            result = VectorXLApi._load_dll()
            assert result is sentinel


# ===================================================================
# 5. _setup_prototypes
# ===================================================================


class TestSetupPrototypes:
    def test_prototypes_set_on_dll_functions(self):
        api, dll = _make_api()
        # After _setup_prototypes, each DLL function should have restype and argtypes
        assert dll.xlOpenDriver.restype is not None
        assert dll.xlCloseDriver.restype is not None
        assert dll.xlGetDriverConfig.restype is not None
        assert dll.xlOpenPort.restype is not None
        assert dll.xlReceive.restype is not None
        assert dll.xlGetErrorString.restype is not None


# ===================================================================
# 6. Driver lifecycle
# ===================================================================


class TestOpenDriver:
    def test_success(self):
        api, dll = _make_api()
        api.open_driver()  # should not raise
        dll.xlOpenDriver.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlOpenDriver.return_value = XL_ERR_NO_LICENSE
        with pytest.raises(VectorXLError) as exc_info:
            api.open_driver()
        assert exc_info.value.func_name == "xlOpenDriver"
        assert exc_info.value.status == XL_ERR_NO_LICENSE


class TestCloseDriver:
    def test_calls_dll(self):
        api, dll = _make_api()
        api.close_driver()
        dll.xlCloseDriver.assert_called_once()


class TestPreflight:
    def test_preflight_ok(self):
        """xlOpenDriver returns XL_SUCCESS -> preflight returns (True, 'OK')."""
        api, dll = _make_api()
        dll.xlOpenDriver.return_value = 0
        ok, msg = api.preflight()
        assert ok is True
        assert msg == "OK"
        dll.xlCloseDriver.assert_called_once()

    def test_preflight_driver_error(self):
        """xlOpenDriver returns non-zero -> preflight returns (False, reason)."""
        api, dll = _make_api()
        dll.xlOpenDriver.return_value = XL_ERR_NO_LICENSE
        ok, msg = api.preflight()
        assert ok is False
        assert "xlOpenDriver" in msg or "0x" in msg

    def test_preflight_exception(self):
        """Unexpected exception -> preflight returns (False, str(exc))."""
        api, dll = _make_api()
        dll.xlOpenDriver.side_effect = OSError("driver service not running")
        ok, msg = api.preflight()
        assert ok is False
        assert "driver service" in msg


# ===================================================================
# 7. get_driver_config
# ===================================================================


class TestGetDriverConfig:
    def test_success_returns_config(self):
        api, dll = _make_api()
        dll.xlGetDriverConfig.return_value = 0
        cfg = api.get_driver_config()
        assert isinstance(cfg, XL_DRIVER_CONFIG)

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlGetDriverConfig.return_value = 0xFF
        with pytest.raises(VectorXLError) as exc_info:
            api.get_driver_config()
        assert exc_info.value.func_name == "xlGetDriverConfig"


class TestGetChannelMask:
    def test_get_channel_mask_found(self):
        api, _ = _make_api()
        cfg = XL_DRIVER_CONFIG()
        cfg.channelCount = 1
        cfg.channel[0].hwType = 57
        cfg.channel[0].hwIndex = 0
        cfg.channel[0].hwChannel = 1
        cfg.channel[0].channelMask = 0x42
        api.get_driver_config = MagicMock(return_value=cfg)
        assert api.get_channel_mask(57, 0, 1) == 0x42

    def test_get_channel_mask_not_found_raises(self):
        api, _ = _make_api()
        cfg = XL_DRIVER_CONFIG()
        cfg.channelCount = 0
        api.get_driver_config = MagicMock(return_value=cfg)
        with pytest.raises(VectorXLError) as exc_info:
            api.get_channel_mask(57, 0, 1)
        assert exc_info.value.status == XL_ERR_WRONG_PARAMETER


# ===================================================================
# 8. lin_channels
# ===================================================================


class TestLinChannels:
    def _make_config(self, capabilities_list):
        """Build an XL_DRIVER_CONFIG with given bus-capability values."""
        cfg = XL_DRIVER_CONFIG()
        cfg.channelCount = len(capabilities_list)
        for i, cap in enumerate(capabilities_list):
            cfg.channel[i].channelBusCapabilities = cap
        return cfg

    def test_filters_lin_capable(self):
        api, _ = _make_api()
        cfg = self._make_config([XL_BUS_TYPE_LIN, 0, XL_BUS_TYPE_LIN | 0x01, 0])
        result = api.lin_channels(cfg)
        assert len(result) == 2

    def test_no_lin_channels(self):
        api, _ = _make_api()
        cfg = self._make_config([0, 0x100])
        result = api.lin_channels(cfg)
        assert result == []

    def test_none_cfg_calls_get_driver_config(self):
        api, dll = _make_api()
        dll.xlGetDriverConfig.return_value = 0
        # When cfg is None, lin_channels should call get_driver_config
        result = api.lin_channels(None)
        dll.xlGetDriverConfig.assert_called_once()
        assert isinstance(result, list)


# ===================================================================
# 9. Port management
# ===================================================================


class TestOpenPort:
    def test_success(self):
        api, dll = _make_api()
        dll.xlOpenPort.return_value = 0
        handle, perm = api.open_port("TestApp", 0x01)
        dll.xlOpenPort.assert_called_once()
        # handle defaults to c_int(-1).value since mock doesn't mutate it
        assert isinstance(handle, int)
        assert isinstance(perm, int)

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlOpenPort.return_value = XL_HARDWARE_NOT_PRESENT
        with pytest.raises(VectorXLError) as exc_info:
            api.open_port("App", 0x01)
        assert exc_info.value.func_name == "xlOpenPort"
        assert exc_info.value.status == XL_HARDWARE_NOT_PRESENT

    def test_custom_queue_size(self):
        api, dll = _make_api()
        dll.xlOpenPort.return_value = 0
        api.open_port("App", 0x02, rx_queue_size=4096)
        dll.xlOpenPort.assert_called_once()


class TestClosePort:
    def test_calls_dll(self):
        api, dll = _make_api()
        api.close_port(42)
        dll.xlClosePort.assert_called_once_with(42)


# ===================================================================
# 10. Channel configuration
# ===================================================================


class TestSetLinChannelParams:
    def test_success(self):
        api, dll = _make_api()
        api.set_lin_channel_params(1, 0x01, baudrate=19200)
        dll.xlLinSetChannelParams.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlLinSetChannelParams.return_value = 0xAA
        with pytest.raises(VectorXLError) as exc_info:
            api.set_lin_channel_params(1, 0x01)
        assert exc_info.value.func_name == "xlLinSetChannelParams"

    def test_custom_lin_version(self):
        api, dll = _make_api()
        api.set_lin_channel_params(1, 0x01, lin_version=0x21)
        dll.xlLinSetChannelParams.assert_called_once()


class TestSetLinDlc:
    def test_success(self):
        api, dll = _make_api()
        dlc_table = [8] * 64
        api.set_lin_dlc(1, 0x01, dlc_table)
        dll.xlLinSetDLC.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlLinSetDLC.return_value = 0xBB
        with pytest.raises(VectorXLError) as exc_info:
            api.set_lin_dlc(1, 0x01, [8] * 64)
        assert exc_info.value.func_name == "xlLinSetDLC"

    def test_short_dlc_table_padded(self):
        """A table shorter than 64 entries should still work (zero-padded)."""
        api, dll = _make_api()
        api.set_lin_dlc(1, 0x01, [4, 4, 8])
        dll.xlLinSetDLC.assert_called_once()

    def test_long_dlc_table_truncated(self):
        """A table longer than 64 should be truncated to 64."""
        api, dll = _make_api()
        api.set_lin_dlc(1, 0x01, [8] * 100)
        dll.xlLinSetDLC.assert_called_once()


class TestSetLinFrameResponse:
    def test_success(self):
        api, dll = _make_api()
        api.set_lin_frame_response(1, 0x01, 0x3C, [0x01, 0x02, 0x03])
        dll.xlLinSetFrameResponse.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlLinSetFrameResponse.return_value = 0xCC
        with pytest.raises(VectorXLError) as exc_info:
            api.set_lin_frame_response(1, 0x01, 0x3C, [0xFF])
        assert exc_info.value.func_name == "xlLinSetFrameResponse"

    def test_data_truncated_to_8_bytes(self):
        """Data longer than 8 should be truncated."""
        api, dll = _make_api()
        api.set_lin_frame_response(1, 0x01, 0x10, list(range(16)))
        dll.xlLinSetFrameResponse.assert_called_once()


# ===================================================================
# 11. Bus activation
# ===================================================================


class TestActivateChannel:
    def test_success(self):
        api, dll = _make_api()
        api.activate_channel(1, 0x01)
        dll.xlActivateChannel.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlActivateChannel.return_value = 0xDD
        with pytest.raises(VectorXLError) as exc_info:
            api.activate_channel(1, 0x01)
        assert exc_info.value.func_name == "xlActivateChannel"


class TestDeactivateChannel:
    def test_calls_dll(self):
        api, dll = _make_api()
        api.deactivate_channel(1, 0x01)
        dll.xlDeactivateChannel.assert_called_once()


class TestSetTimerRate:
    def test_success(self):
        api, dll = _make_api()
        api.set_timer_rate(1, 1000)
        dll.xlSetTimerRate.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlSetTimerRate.return_value = 0xAB
        with pytest.raises(VectorXLError) as exc_info:
            api.set_timer_rate(1, 1000)
        assert exc_info.value.func_name == "xlSetTimerRate"


# ===================================================================
# 12. LIN master TX
# ===================================================================


class TestLinSendRequest:
    def test_success(self):
        api, dll = _make_api()
        api.lin_send_request(1, 0x01, 0x10)
        dll.xlLinSendRequest.assert_called_once()

    def test_failure_raises(self):
        api, dll = _make_api()
        dll.xlLinSendRequest.return_value = 0xEE
        with pytest.raises(VectorXLError) as exc_info:
            api.lin_send_request(1, 0x01, 0x10)
        assert exc_info.value.func_name == "xlLinSendRequest"

    def test_custom_flags(self):
        api, dll = _make_api()
        api.lin_send_request(1, 0x01, 0x3F, flags=1)
        dll.xlLinSendRequest.assert_called_once()


class TestLinSendResponse:
    def test_success(self):
        api, _ = _make_api()
        api.set_lin_frame_response = MagicMock()
        api.lin_send_request = MagicMock()
        api.lin_send_response(1, 0x01, 0x10, 2, [0x11, 0x22])
        api.set_lin_frame_response.assert_called_once_with(1, 0x01, 0x10, [0x11, 0x22])
        api.lin_send_request.assert_called_once_with(1, 0x01, 0x10)

    def test_short_payload_is_padded(self):
        api, _ = _make_api()
        api.set_lin_frame_response = MagicMock()
        api.lin_send_request = MagicMock()
        api.lin_send_response(1, 0x01, 0x10, 4, [0x11, 0x22])
        api.set_lin_frame_response.assert_called_once_with(
            1,
            0x01,
            0x10,
            [0x11, 0x22, 0x00, 0x00],
        )

    def test_invalid_frame_id_raises(self):
        api, _ = _make_api()
        with pytest.raises(VectorXLError):
            api.lin_send_response(1, 0x01, 0x99, 1, [0x01])

    def test_invalid_dlc_raises(self):
        api, _ = _make_api()
        with pytest.raises(VectorXLError):
            api.lin_send_response(1, 0x01, 0x10, 9, [0x01] * 9)


class TestLinSetChecksumInfo:
    def test_with_optional_export(self):
        api, dll = _make_api()
        api.lin_set_checksum_info(1, 0x01, [1] * 64)
        dll.xlLinSetChecksum.assert_called_once()

    def test_optional_export_error_raises(self):
        api, dll = _make_api()
        dll.xlLinSetChecksum.return_value = 0xAD
        with pytest.raises(VectorXLError):
            api.lin_set_checksum_info(1, 0x01, [1] * 64)

    def test_without_optional_export(self):
        dll = FakeDLL()
        del dll.xlLinSetChecksum
        api, _ = _make_api(dll)
        api.lin_set_checksum_info(1, 0x01, [1] * 64)


# ===================================================================
# 13. Receive
# ===================================================================


class TestReceive:
    def test_success_returns_event(self):
        api, dll = _make_api()
        dll.xlReceive.return_value = 0
        result = api.receive(1)
        assert isinstance(result, XL_EVENT)

    def test_empty_queue_returns_none(self):
        api, dll = _make_api()
        dll.xlReceive.return_value = XL_ERR_QUEUE_IS_EMPTY
        result = api.receive(1)
        assert result is None

    def test_other_error_raises(self):
        api, dll = _make_api()
        dll.xlReceive.return_value = 0xFF
        with pytest.raises(VectorXLError) as exc_info:
            api.receive(1)
        assert exc_info.value.func_name == "xlReceive"


class TestReceiveAliasesAndQueue:
    def test_receive_event_alias(self):
        api, _ = _make_api()
        api.receive = MagicMock(return_value=None)
        assert api.receive_event(1) is None
        api.receive.assert_called_once_with(1)

    def test_flush_receive_queue(self):
        api, _ = _make_api()
        evt = XL_EVENT()
        api.receive = MagicMock(side_effect=[evt, None])
        api.flush_receive_queue(1)
        assert api.receive.call_count == 2


class TestNotification:
    def test_set_notification_success(self):
        api, _ = _make_api()
        handle = api.set_notification(1)
        assert handle is not None

    def test_set_notification_failure_raises(self):
        api, dll = _make_api()
        dll.xlSetNotification.return_value = 0x99
        with pytest.raises(VectorXLError):
            api.set_notification(1)


# ===================================================================
# 14. error_string
# ===================================================================


class TestErrorString:
    def test_returns_decoded_string(self):
        api, dll = _make_api()
        dll.xlGetErrorString.return_value = b"XL_ERR_NO_LICENSE"
        result = api.error_string(XL_ERR_NO_LICENSE)
        assert result == "XL_ERR_NO_LICENSE"

    def test_none_raw_returns_fallback(self):
        api, dll = _make_api()
        dll.xlGetErrorString.return_value = None
        result = api.error_string(0x87)
        assert "0x87" in result

    def test_non_ascii_handled(self):
        api, dll = _make_api()
        dll.xlGetErrorString.return_value = b"caf\xe9"
        result = api.error_string(0)
        assert "caf" in result

    def test_get_error_string_alias(self):
        api, _ = _make_api()
        api.error_string = MagicMock(return_value="ok")
        assert api.get_error_string(0) == "ok"
        api.error_string.assert_called_once_with(0)


# ===================================================================
# 15. __init__ integration
# ===================================================================


class TestInit:
    def test_init_calls_load_and_setup(self):
        """VectorXLApi.__init__ should call _load_dll and _setup_prototypes."""
        fake = FakeDLL()
        with patch.object(VectorXLApi, "_load_dll", return_value=fake) as mock_load, \
             patch.object(VectorXLApi, "_setup_prototypes") as mock_setup:
            api = VectorXLApi()
            mock_load.assert_called_once()
            mock_setup.assert_called_once()
            assert api._dll is fake

# ===================================================================
# 16. dll_path
# ===================================================================


class TestDllPath:
    def test_dll_path_property_returns_stored_value(self):
        api, _ = _make_api()
        api._dll_path = r"C:\third_party\vector\bin\vxlapi64.dll"
        assert api.dll_path == r"C:\third_party\vector\bin\vxlapi64.dll"

    def test_dll_path_property_none(self):
        api, _ = _make_api()
        api._dll_path = None
        assert api.dll_path is None

    def test_dll_path_captured_from_dll_name_at_init(self):
        """__init__ reads ._name from the loaded DLL and stores it as _dll_path."""
        fake = FakeDLL()
        fake._name = r"C:\third_party\vector\bin\vxlapi64.dll"
        with patch.object(VectorXLApi, "_load_dll", return_value=fake):
            api = VectorXLApi()
        assert api.dll_path == r"C:\third_party\vector\bin\vxlapi64.dll"

    def test_dll_path_none_when_dll_has_no_name_attribute(self):
        """When DLL has no _name attribute, _dll_path is None."""
        fake = FakeDLL()  # FakeDLL does not define _name
        with patch.object(VectorXLApi, "_load_dll", return_value=fake):
            api = VectorXLApi()
        assert api.dll_path is None
