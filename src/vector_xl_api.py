"""Vector XL Driver ctypes wrapper.

Provides a thin Python layer over the Vector XL API required to operate a
VN16xx device as a LIN master. On non-Windows systems or when the driver is
not installed the module degrades gracefully so that the GUI can still run in
simulation or demo mode.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import ctypes
import ctypes.util
import ctypes.wintypes
import logging
import platform
from dataclasses import dataclass
from pathlib import Path
from ctypes import c_int, c_uint, c_ubyte, c_char, c_char_p, c_ulonglong, POINTER
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants from vxlapi.h
# ---------------------------------------------------------------------------

XL_SUCCESS = 0
XL_PENDING = 1

# Error codes (selected)
XL_ERR_QUEUE_IS_EMPTY = 10
XL_ERR_NO_LICENSE = 135
XL_HARDWARE_NOT_PRESENT = 129

# Common XL error codes used by higher-level modules
XL_ERR_INVALID_ACCESS = 112
XL_ERR_PORT_IS_OFFLINE = 117
XL_ERR_INVALID_PORT = 118
XL_ERR_WRONG_PARAMETER = 101

# Bus types
XL_BUS_TYPE_LIN = 0x00000200

# Hardware types (selected)
XL_HWTYPE_VIRTUAL = 1
XL_HWTYPE_CANCASEXL = 21
XL_HWTYPE_VN1600 = 55
XL_HWTYPE_VN1610 = 57

# LIN mode
XL_LIN_MASTER = 1
XL_LIN_SLAVE = 2
XL_LIN_SLAVE_OFF = 0
XL_LIN_SLAVE_ON = 0xFF

# LIN slave checksum calculation modes
XL_LIN_CALC_CHECKSUM = 0x100
XL_LIN_CALC_CHECKSUM_ENHANCED = 0x200

# LIN sleep mode flags
XL_LIN_FLAG_NO_SLEEP_MODE_EVENT = 0x01
XL_LIN_FLAG_USE_ID_AS_WAKEUPID = 0x02

# LIN event tags
XL_LIN_TAG_MSG = 20
XL_LIN_ERRMSG = 21
XL_LIN_SYNCERR = 22
XL_LIN_SYNC_ERR = XL_LIN_SYNCERR  # compatibility alias
XL_LIN_NOANS = 23
XL_LIN_WAKEUP = 24
XL_LIN_SLEEP = 25
XL_LIN_CRCINFO = 26

# LIN event flags
XL_LIN_MSGFLAG_TX = 0x40
XL_LIN_MSGFLAG_CRCERROR = 0x81
XL_LIN_WAKUP_INTERNAL = 0x01
XL_LIN_STAYALIVE = 0x00
XL_LIN_SET_SLEEPMODE = 0x01
XL_LIN_COMESFROM_SLEEPMODE = 0x02

# Checksum modes
XL_LIN_CHECKSUM_CLASSIC = 0
XL_LIN_CHECKSUM_ENHANCED = 1

# LIN protocol versions
XL_LIN_VERSION_1_3 = 0x13
XL_LIN_VERSION_2_0 = 0x20
XL_LIN_VERSION_2_1 = 0x21

# XL interface versions
XL_INTERFACE_VERSION = 3
XL_INTERFACE_VERSION_V3 = 3
XL_INTERFACE_VERSION_V4 = 4

# Channel capabilities
XL_CHANNEL_FLAG_LIN_CAP = 0x00000400

# Activate flags
XL_ACTIVATE_RESET_CLOCK = 8

# ---------------------------------------------------------------------------
# Structures  (must match the C layout in xlapi.h exactly)
# ---------------------------------------------------------------------------

XL_MAX_APPNAME = 32
XL_MAX_LENGTH = 8
XL_CONFIG_MAX_CHANNELS = 64


class XL_LIN_STAT_PARAM(ctypes.Structure):
    """Parameters used to configure a LIN channel."""

    _pack_ = 1
    _fields_ = [
        ("LINMode", c_uint),  # XL_LIN_MASTER or XL_LIN_SLAVE
        ("baudrate", c_int),  # e.g. 19200
        ("LINVersion", c_uint),  # XL_LIN_VERSION_*
        ("reserved", c_uint),
    ]


class XL_LIN_MSG(ctypes.Structure):
    """A LIN message received or to be transmitted."""

    _pack_ = 1
    _fields_ = [
        ("id", c_ubyte),
        ("dlc", c_ubyte),
        ("flags", ctypes.c_ushort),
        ("data", c_ubyte * 8),
        ("crc", c_uint),
        ("dir", c_ubyte),
        ("reserved", c_uint * 3),
    ]


class XL_CHANNEL_CONFIG(ctypes.Structure):
    """Per-channel hardware description returned by xlGetDriverConfig."""

    _pack_ = 1
    _fields_ = [
        ("name", c_char * (XL_MAX_APPNAME + 1)),
        ("hwType", c_ubyte),
        ("hwIndex", c_ubyte),
        ("hwChannel", c_ubyte),
        ("transceiver", c_uint),
        ("transceiverState", c_uint),
        ("transceiverFeatureMask", c_uint),
        ("channelIndex", c_uint),
        ("channelMask", ctypes.c_ulonglong),
        ("channelCapabilities", c_uint),
        ("channelBusCapabilities", c_uint),
        ("isOnBus", c_ubyte),
        ("busParams", c_ubyte * 32),
        ("_reserved", c_uint * 24),
        ("channelVersion", c_uint),
        ("channelBusActiveCapabilities", c_uint),
        ("connectorMode", c_uint),
        ("transceiverType", c_uint),
        ("_reserved2", c_uint * 9),
    ]


class XL_DRIVER_CONFIG(ctypes.Structure):
    """Global driver configuration, contains all available channels."""

    _pack_ = 1
    _fields_ = [
        ("dllVersion", c_uint),
        ("channelCount", c_uint),
        ("reserved", c_uint * 10),
        ("channel", XL_CHANNEL_CONFIG * XL_CONFIG_MAX_CHANNELS),
    ]


# We use a union / opaque event just large enough for the XL_EVENT structure.
# The real structure is ~72 bytes; use a byte-array placeholder.
_XL_EVENT_SIZE = 72


class XL_EVENT(ctypes.Structure):
    """Opaque XL event buffer (receives LIN messages and other events)."""

    _pack_ = 1
    _fields_ = [
        ("tag", c_ubyte),
        ("chanIndex", c_ubyte),
        ("transId", ctypes.c_ushort),
        ("portHandle", ctypes.c_ushort),
        ("flags", c_ubyte),
        ("reserved", c_ubyte),
        ("timeStamp", ctypes.c_ulonglong),
        ("_raw", c_ubyte * 52),  # union payload (max ~52 bytes)
    ]

    @property
    def lin_msg(self) -> XL_LIN_MSG:
        """Overlay the payload bytes as an XL_LIN_MSG."""
        return XL_LIN_MSG.from_buffer_copy(self._raw)


@dataclass(frozen=True)
class LINEventBase:
    """Common metadata for decoded LIN events."""

    tag: int
    timestamp_ns: int
    channel_index: int


@dataclass(frozen=True)
class LINMessageEvent(LINEventBase):
    """Decoded XL_LIN_MSG payload."""

    lin_id: int
    dlc: int
    flags: int
    data: bytes
    crc: int


@dataclass(frozen=True)
class LINNoAnswerEvent(LINEventBase):
    """Decoded XL_LIN_NOANS payload."""

    lin_id: int


@dataclass(frozen=True)
class LINWakeupEvent(LINEventBase):
    """Decoded XL_LIN_WAKEUP payload."""

    flag: int
    start_offset: int
    width: int


@dataclass(frozen=True)
class LINSleepEvent(LINEventBase):
    """Decoded XL_LIN_SLEEP payload."""

    flag: int


@dataclass(frozen=True)
class LINCrcInfoEvent(LINEventBase):
    """Decoded XL_LIN_CRCINFO payload."""

    lin_id: int
    flags: int


@dataclass(frozen=True)
class LINRawTagEvent(LINEventBase):
    """Decoded LIN tag without additional payload fields."""


LINDecodedEvent = (
    LINMessageEvent
    | LINNoAnswerEvent
    | LINWakeupEvent
    | LINSleepEvent
    | LINCrcInfoEvent
    | LINRawTagEvent
)


# ---------------------------------------------------------------------------
# Driver wrapper
# ---------------------------------------------------------------------------


class VectorXLDriverNotFoundError(RuntimeError):
    """Raised when vxlapi.dll cannot be loaded."""


class VectorXLError(RuntimeError):
    """Raised when a Vector XL API call returns a non-success status."""

    def __init__(self, func_name: str, status: int) -> None:
        """Store the failing API function name and return status."""
        super().__init__(f"{func_name} returned status {status:#x}")
        self.func_name = func_name
        self.status = status


class VectorXLApi:  # pylint: disable=too-many-public-methods
    """
    Thin ctypes wrapper around vxlapi.dll / vxlapi64.dll.

    Usage::

        api = VectorXLApi()           # loads the DLL
        api.open_driver()
        cfg = api.get_driver_config()
        mask = <choose channel mask from cfg>
        port = api.open_port("EasyLIN", mask, mask, 8192)
        api.set_lin_channel_params(port, mask, 19200)
        api.activate_channel(port, mask)
        api.lin_send_request(port, mask, 0x10)
        evt = api.receive(port)
        api.deactivate_channel(port, mask)
        api.close_port(port)
        api.close_driver()
    """

    def __init__(self) -> None:
        """Load the Vector XL DLL and configure ctypes prototypes."""
        self._dll = self._load_dll()
        self._dll_path: Optional[str] = getattr(self._dll, '_name', None)
        self._setup_prototypes()

    @property
    def dll_path(self) -> Optional[str]:
        """Return the filesystem path from which the DLL was loaded."""
        return self._dll_path

    # ------------------------------------------------------------------
    # DLL loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_dll() -> ctypes.CDLL:
        """Load the Vector XL DLL from the current Windows installation."""
        if platform.system() != "Windows":
            raise VectorXLDriverNotFoundError("Vector XL Driver is only available on Windows.")

        local_bin = Path(__file__).resolve().parent.parent / "third_party" / "vector" / "bin"
        local_bases = [str(local_bin)] if local_bin.is_dir() else []

        # Try 64-bit first, then 32-bit
        for name in ("vxlapi64", "vxlapi"):
            # Prefer vendored runtime shipped with this repository.
            for base in local_bases:
                candidate = str(Path(base) / f"{name}.dll")
                try:
                    return ctypes.WinDLL(candidate)
                except OSError:
                    continue

            path = ctypes.util.find_library(name)
            if path:
                try:
                    return ctypes.WinDLL(path)
                except OSError:
                    pass  # fall through to standard installation paths
            # Also try standard installation paths
            for base in (
                r"C:\Users\Public\Documents\Vector\XL Driver Library\bin",
                r"C:\Program Files\Vector XL Driver Library\bin",
                r"C:\Program Files (x86)\Vector XL Driver Library\bin",
            ):
                candidate = rf"{base}\{name}.dll"
                try:
                    return ctypes.WinDLL(candidate)
                except OSError:
                    continue
        raise VectorXLDriverNotFoundError(
            "vxlapi.dll not found.  Please install the Vector XL Driver "
            "Library (available from https://www.vector.com/int/en/products/"
            "products-a-z/software/xl-driver-library/)."
        )

    def _setup_prototypes(self) -> None:
        """Configure ctypes signatures for the Vector XL functions in use."""
        dll = self._dll

        def _proto(name: str, restype, *argtypes):
            """Assign a ctypes return type and argument list to one DLL export."""
            fn = getattr(dll, name)
            fn.restype = restype
            fn.argtypes = list(argtypes)

        _proto("xlOpenDriver", c_int)
        _proto("xlCloseDriver", c_int)
        _proto("xlGetDriverConfig", c_int, POINTER(XL_DRIVER_CONFIG))
        _proto(
            "xlOpenPort",
            c_int,
            POINTER(c_int),  # portHandle out
            c_char_p,  # userName
            ctypes.c_ulonglong,  # accessMask
            POINTER(ctypes.c_ulonglong),  # permissionMask in/out
            c_uint,  # rxQueueSize
            c_uint,  # interfaceVersion
            c_uint,
        )  # busType
        _proto("xlClosePort", c_int, c_int)
        _proto("xlActivateChannel", c_int, c_int, ctypes.c_ulonglong, c_uint, c_uint)
        _proto("xlDeactivateChannel", c_int, c_int, ctypes.c_ulonglong)
        _proto("xlLinSetChannelParams", c_int, c_int, ctypes.c_ulonglong, XL_LIN_STAT_PARAM)
        _proto("xlLinSetDLC", c_int, c_int, ctypes.c_ulonglong, c_ubyte * 64)
        _proto(
            "xlLinSetSlave",
            c_int,
            c_int,
            ctypes.c_ulonglong,
            c_ubyte,
            c_ubyte * 8,
            c_ubyte,
            ctypes.c_ushort,
        )
        _proto(
            "xlLinSwitchSlave",
            c_int,
            c_int,
            ctypes.c_ulonglong,
            c_ubyte,
            c_uint,
        )
        _proto(
            "xlLinSetFrameResponse",
            c_int,
            c_int,
            ctypes.c_ulonglong,
            POINTER(XL_LIN_MSG),
            c_uint,
        )
        _proto("xlLinSendRequest", c_int, c_int, ctypes.c_ulonglong, c_ubyte, c_uint)
        _proto("xlLinWakeUp", c_int, c_int, ctypes.c_ulonglong)
        _proto("xlLinSetSleepMode", c_int, c_int, ctypes.c_ulonglong, c_uint, c_ubyte)
        _proto("xlReceive", c_int, c_int, POINTER(c_uint), POINTER(XL_EVENT))
        _proto("xlSetNotification", c_int, c_int, POINTER(ctypes.c_void_p), c_int)
        _proto("xlSetTimerRate", c_int, c_int, c_ulonglong)
        _proto("xlGetErrorString", c_char_p, c_int)

        # Optional export on some XL driver versions.
        if hasattr(dll, "xlLinSetChecksum"):
            _proto("xlLinSetChecksum", c_int, c_int, ctypes.c_ulonglong, c_ubyte * 64)

    # ------------------------------------------------------------------
    # Driver lifecycle
    # ------------------------------------------------------------------

    def open_driver(self) -> None:
        """Open the Vector XL driver library."""
        status = self._dll.xlOpenDriver()
        if status != XL_SUCCESS:
            raise VectorXLError("xlOpenDriver", status)

    def close_driver(self) -> None:
        """Close the Vector XL driver library."""
        self._dll.xlCloseDriver()

    def preflight(self) -> tuple[bool, str]:
        """Verify the DLL is functional by executing a harmless open/close cycle.

        Returns:
            ``(True, 'OK')`` when ``xlOpenDriver`` succeeds.
            ``(False, <reason>)`` when the call fails or raises.
        """
        try:
            self.open_driver()
            self.close_driver()
            return True, "OK"
        except VectorXLError as exc:
            return False, f"xlOpenDriver returned 0x{exc.status:02X}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def get_driver_config(self) -> XL_DRIVER_CONFIG:
        """Return the current Vector driver configuration structure."""
        cfg = XL_DRIVER_CONFIG()
        status = self._dll.xlGetDriverConfig(ctypes.byref(cfg))
        if status != XL_SUCCESS:
            raise VectorXLError("xlGetDriverConfig", status)
        return cfg

    def get_channel_mask(self, hw_type: int, hw_index: int, hw_channel: int) -> int:
        """Resolve a Vector channel mask from hardware identity.

        Args:
            hw_type: Hardware type constant (for example ``XL_HWTYPE_VN1610``).
            hw_index: Device index reported by the driver.
            hw_channel: Channel index on the hardware device.

        Returns:
            Channel mask for the matching channel.

        Raises:
            VectorXLError: If no matching channel exists in current driver config.

        Example:
            ``mask = api.get_channel_mask(XL_HWTYPE_VN1610, 0, 0)``
        """
        cfg = self.get_driver_config()
        for i in range(cfg.channelCount):
            ch = cfg.channel[i]
            if ch.hwType == hw_type and ch.hwIndex == hw_index and ch.hwChannel == hw_channel:
                return int(ch.channelMask)
        raise VectorXLError("get_channel_mask", XL_ERR_WRONG_PARAMETER)

    def lin_channels(self, cfg: Optional[XL_DRIVER_CONFIG] = None) -> List[XL_CHANNEL_CONFIG]:
        """Return all channels that have LIN capability."""
        if cfg is None:
            cfg = self.get_driver_config()
        result = []
        for i in range(cfg.channelCount):
            ch = cfg.channel[i]
            if ch.channelBusCapabilities & XL_BUS_TYPE_LIN:
                result.append(ch)
        return result

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def open_port(
        self,
        app_name: str,
        access_mask: int,
        rx_queue_size: int = 8192,
    ) -> Tuple[int, int]:
        """Open a port for the given channel access mask.

        Returns:
            (port_handle, granted_permission_mask)
        """
        port_handle = c_int(-1)
        perm_mask = ctypes.c_ulonglong(access_mask)
        status = self._dll.xlOpenPort(
            ctypes.byref(port_handle),
            app_name.encode("ascii"),
            ctypes.c_ulonglong(access_mask),
            ctypes.byref(perm_mask),
            rx_queue_size,
            XL_INTERFACE_VERSION_V4,
            XL_BUS_TYPE_LIN,
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlOpenPort", status)
        return port_handle.value, perm_mask.value

    def close_port(self, port_handle: int) -> None:
        """Close a previously opened Vector port handle."""
        self._dll.xlClosePort(port_handle)

    # ------------------------------------------------------------------
    # Channel configuration
    # ------------------------------------------------------------------

    def set_lin_channel_params(
        self,
        port_handle: int,
        access_mask: int,
        baudrate: int = 19200,
        lin_version: int = XL_LIN_VERSION_2_0,
    ) -> None:
        """Configure the channel as a LIN master with the given baud rate."""
        params = XL_LIN_STAT_PARAM(
            LINMode=XL_LIN_MASTER,
            baudrate=baudrate,
            LINVersion=lin_version,
            reserved=0,
        )
        status = self._dll.xlLinSetChannelParams(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            params,
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSetChannelParams", status)

    def set_lin_dlc(
        self,
        port_handle: int,
        access_mask: int,
        dlc_table: List[int],
    ) -> None:
        """Set data length for each of the 64 LIN frame IDs (0â€“63)."""
        arr = (c_ubyte * 64)(*([0] * 64))
        for i, v in enumerate(dlc_table[:64]):
            arr[i] = v
        status = self._dll.xlLinSetDLC(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            arr,
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSetDLC", status)

    def set_lin_frame_response(
        self,
        port_handle: int,
        access_mask: int,
        frame_id: int,
        data: List[int],
    ) -> None:
        """Pre-load data bytes for a slave-side response (for simulation)."""
        msg = XL_LIN_MSG()
        msg.id = frame_id
        msg.dlc = len(data)
        for i, b in enumerate(data[:8]):
            msg.data[i] = b
        status = self._dll.xlLinSetFrameResponse(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            ctypes.byref(msg),
            1,
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSetFrameResponse", status)

    def lin_set_slave(
        self,
        port_handle: int,
        access_mask: int,
        lin_id: int,
        data: List[int],
        dlc: int,
        checksum: int,
    ) -> None:
        """Configure one LIN slave response entry for a specific LIN identifier.

        This call can be used on a dedicated slave channel and also to set up
        slave tasks on a master channel.
        """
        payload = [0] * 8
        for i, value in enumerate(data[:8]):
            payload[i] = int(value) & 0xFF
        arr = (c_ubyte * 8)(*payload)
        status = self._dll.xlLinSetSlave(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            c_ubyte(lin_id & 0x3F),
            arr,
            c_ubyte(dlc & 0xFF),
            ctypes.c_ushort(checksum & 0xFFFF),
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSetSlave", status)

    def lin_switch_slave(
        self,
        port_handle: int,
        access_mask: int,
        lin_id: int,
        mode: int,
    ) -> None:
        """Enable or disable one configured LIN slave during active measurement."""
        status = self._dll.xlLinSwitchSlave(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            c_ubyte(lin_id & 0x3F),
            c_uint(mode),
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSwitchSlave", status)

    def lin_wakeup(self, port_handle: int, access_mask: int) -> None:
        """Transmit a LIN wake-up request on the selected channel."""
        status = self._dll.xlLinWakeUp(port_handle, ctypes.c_ulonglong(access_mask))
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinWakeUp", status)

    def lin_set_sleep_mode(
        self,
        port_handle: int,
        access_mask: int,
        flags: int,
        lin_id: int = 0,
    ) -> None:
        """Put the LIN channel into sleep mode, optionally configuring wake-up ID."""
        status = self._dll.xlLinSetSleepMode(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            c_uint(flags),
            c_ubyte(lin_id & 0x3F),
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSetSleepMode", status)

    # ------------------------------------------------------------------
    # Bus activation
    # ------------------------------------------------------------------

    def activate_channel(self, port_handle: int, access_mask: int) -> None:
        """Activate a LIN-capable channel for communication."""
        status = self._dll.xlActivateChannel(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            XL_BUS_TYPE_LIN,
            XL_ACTIVATE_RESET_CLOCK,
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlActivateChannel", status)

    def deactivate_channel(self, port_handle: int, access_mask: int) -> None:
        """Deactivate a previously activated channel."""
        self._dll.xlDeactivateChannel(port_handle, ctypes.c_ulonglong(access_mask))

    def set_timer_rate(self, port_handle: int, timer_rate: int) -> None:
        """Set event polling timer period for one opened port.

        Args:
            port_handle: Opened XL port handle.
            timer_rate: Timer rate in 10 us units.

        Raises:
            VectorXLError: If ``xlSetTimerRate`` fails.

        Example:
            ``api.set_timer_rate(port, 1000)``
        """
        status = self._dll.xlSetTimerRate(port_handle, c_ulonglong(timer_rate))
        if status != XL_SUCCESS:
            raise VectorXLError("xlSetTimerRate", status)

    # ------------------------------------------------------------------
    # LIN master TX
    # ------------------------------------------------------------------

    def lin_send_request(
        self,
        port_handle: int,
        access_mask: int,
        lin_id: int,
        flags: int = 0,
    ) -> None:
        """Send a LIN master frame header (request) for the given ID.

        The slave whose ID matches will respond with its data bytes.
        """
        status = self._dll.xlLinSendRequest(
            port_handle,
            ctypes.c_ulonglong(access_mask),
            c_ubyte(lin_id & 0x3F),
            c_uint(flags),
        )
        if status != XL_SUCCESS:
            raise VectorXLError("xlLinSendRequest", status)

    def lin_send_response(
        self,
        port_handle: int,
        access_mask: int,
        frame_id: int,
        dlc: int,
        data: List[int],
    ) -> None:
        """Send a master-published LIN response frame.

        Args:
            port_handle: Opened XL port handle.
            access_mask: Channel access mask.
            frame_id: LIN frame identifier in range 0..63.
            dlc: Number of payload bytes (0..8).
            data: Payload bytes, each in range 0..255.

        Raises:
            VectorXLError: If ID/DLC is invalid or underlying XL calls fail.

        Example:
            ``api.lin_send_response(port, mask, 0x12, 2, [0x11, 0x22])``
        """
        if frame_id < 0 or frame_id > 0x3F:
            raise VectorXLError("lin_send_response", XL_ERR_WRONG_PARAMETER)
        if dlc < 0 or dlc > XL_MAX_LENGTH:
            raise VectorXLError("lin_send_response", XL_ERR_WRONG_PARAMETER)
        payload = list(data[:dlc])
        if len(payload) < dlc:
            payload.extend([0] * (dlc - len(payload)))
        self.set_lin_frame_response(port_handle, access_mask, frame_id, payload)
        self.lin_send_request(port_handle, access_mask, frame_id)

    def lin_set_checksum_info(
        self,
        port_handle: int,
        access_mask: int,
        checksum_table: List[int],
    ) -> None:
        """Set checksum strategy table for all LIN frame IDs.

        Args:
            port_handle: Opened XL port handle.
            access_mask: Channel access mask.
            checksum_table: 64 entries (classic/enhanced).

        Raises:
            VectorXLError: If driver reports failure.

        Example:
            ``api.lin_set_checksum_info(port, mask, [XL_LIN_CHECKSUM_ENHANCED] * 64)``
        """
        if hasattr(self._dll, "xlLinSetChecksum"):
            arr = (c_ubyte * 64)(*([0] * 64))
            for i, v in enumerate(checksum_table[:64]):
                arr[i] = int(v)
            status = self._dll.xlLinSetChecksum(
                port_handle,
                ctypes.c_ulonglong(access_mask),
                arr,
            )
            if status != XL_SUCCESS:
                raise VectorXLError("xlLinSetChecksum", status)

    def set_notification(self, port_handle: int) -> ctypes.wintypes.HANDLE:
        """Create and return a Windows notification handle for an XL port.

        Args:
            port_handle: Opened XL port handle.

        Returns:
            Notification handle compatible with Win32 wait APIs.

        Raises:
            VectorXLError: If ``xlSetNotification`` fails.

        Example:
            ``handle = api.set_notification(port)``
        """
        notify = ctypes.c_void_p()
        status = self._dll.xlSetNotification(port_handle, ctypes.byref(notify), 1)
        if status != XL_SUCCESS:
            raise VectorXLError("xlSetNotification", status)
        return ctypes.wintypes.HANDLE(notify.value)

    # ------------------------------------------------------------------
    # RX
    # ------------------------------------------------------------------

    def receive(self, port_handle: int) -> Optional[XL_EVENT]:
        """Try to dequeue one event.  Returns None when the queue is empty."""
        count = c_uint(1)
        evt = XL_EVENT()
        status = self._dll.xlReceive(
            port_handle,
            ctypes.byref(count),
            ctypes.byref(evt),
        )
        if status == XL_ERR_QUEUE_IS_EMPTY:
            return None
        if status != XL_SUCCESS:
            raise VectorXLError("xlReceive", status)
        return evt

    def receive_event(self, port_handle: int) -> Optional[XL_EVENT]:
        """Compatibility alias for :meth:`receive`."""
        return self.receive(port_handle)

    @staticmethod
    def decode_lin_event(evt: XL_EVENT) -> Optional[LINDecodedEvent]:
        """Decode one raw XL event into a typed LIN event model.

        Returns ``None`` when the event tag does not represent a LIN event.
        """
        raw = bytes(evt._raw)
        base = {
            "tag": int(evt.tag),
            "timestamp_ns": int(evt.timeStamp),
            "channel_index": int(evt.chanIndex),
        }

        if evt.tag == XL_LIN_TAG_MSG:
            flags = int.from_bytes(raw[2:4], byteorder="little", signed=False)
            dlc = int(raw[1])
            return LINMessageEvent(
                **base,
                lin_id=int(raw[0]),
                dlc=dlc,
                flags=flags,
                data=raw[4 : 4 + min(8, dlc)],
                crc=int(raw[12]),
            )

        if evt.tag == XL_LIN_NOANS:
            return LINNoAnswerEvent(**base, lin_id=int(raw[0]))

        if evt.tag == XL_LIN_WAKEUP:
            return LINWakeupEvent(
                **base,
                flag=int(raw[0]),
                start_offset=int.from_bytes(raw[4:8], byteorder="little", signed=False),
                width=int.from_bytes(raw[8:12], byteorder="little", signed=False),
            )

        if evt.tag == XL_LIN_SLEEP:
            return LINSleepEvent(**base, flag=int(raw[0]))

        if evt.tag == XL_LIN_CRCINFO:
            return LINCrcInfoEvent(**base, lin_id=int(raw[0]), flags=int(raw[1]))

        if evt.tag in (XL_LIN_ERRMSG, XL_LIN_SYNCERR, XL_LIN_SYNC_ERR):
            return LINRawTagEvent(**base)

        return None

    def receive_lin_event(self, port_handle: int) -> Optional[LINDecodedEvent]:
        """Receive and decode one LIN event from the queue.

        Returns ``None`` when the queue is empty or when the dequeued event is
        not one of the LIN tags handled by :meth:`decode_lin_event`.
        """
        evt = self.receive(port_handle)
        if evt is None:
            return None
        return self.decode_lin_event(evt)

    def flush_receive_queue(self, port_handle: int) -> None:
        """Drain all pending receive events for one XL port.

        Args:
            port_handle: Opened XL port handle.

        Raises:
            VectorXLError: If one receive call fails with a non-empty-queue error.

        Example:
            ``api.flush_receive_queue(port)``
        """
        while True:
            evt = self.receive(port_handle)
            if evt is None:
                break

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def error_string(self, status: int) -> str:
        """Return the Vector driver error string for a status code."""
        raw = self._dll.xlGetErrorString(status)
        return raw.decode("ascii", errors="replace") if raw else f"status={status:#x}"

    def get_error_string(self, status: int) -> str:
        """Compatibility alias for :meth:`error_string`."""
        return self.error_string(status)

