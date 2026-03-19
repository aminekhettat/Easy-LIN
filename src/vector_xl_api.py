"""Vector XL Driver ctypes wrapper.

Provides a thin Python layer over the Vector XL API required to operate a
VN16xx device as a LIN master. On non-Windows systems or when the driver is
not installed the module degrades gracefully so that the GUI can still run in
simulation or demo mode.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import ctypes
import ctypes.util
import logging
import platform
import sys
from ctypes import c_int, c_uint, c_ubyte, c_char, c_char_p, POINTER
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

# Bus types
XL_BUS_TYPE_LIN = 0x00000200

# LIN mode
XL_LIN_MASTER = 1
XL_LIN_SLAVE = 2

# LIN protocol versions
XL_LIN_VERSION_1_3 = 0x13
XL_LIN_VERSION_2_0 = 0x20
XL_LIN_VERSION_2_1 = 0x21

# XL interface versions
XL_INTERFACE_VERSION = 3
XL_INTERFACE_VERSION_V4 = 4

# Channel capabilities
XL_CHANNEL_FLAG_LIN_CAP = 0x00000400

# Activate flags
XL_ACTIVATE_RESET_CLOCK = 8

# Event tags
XL_LIN_MSG = 14

# ---------------------------------------------------------------------------
# Structures  (must match the C layout in xlapi.h exactly)
# ---------------------------------------------------------------------------

XL_MAX_APPNAME = 32
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


class VectorXLApi:
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
        self._setup_prototypes()

    # ------------------------------------------------------------------
    # DLL loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_dll() -> ctypes.CDLL:
        """Load the Vector XL DLL from the current Windows installation."""
        if platform.system() != "Windows":
            raise VectorXLDriverNotFoundError(
                "Vector XL Driver is only available on Windows."
            )
        # Try 64-bit first, then 32-bit
        for name in ("vxlapi64", "vxlapi"):
            path = ctypes.util.find_library(name)
            if path:
                try:
                    return ctypes.WinDLL(path)
                except OSError:
                    continue
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
        _proto(
            "xlLinSetChannelParams", c_int, c_int, ctypes.c_ulonglong, XL_LIN_STAT_PARAM
        )
        _proto("xlLinSetDLC", c_int, c_int, ctypes.c_ulonglong, c_ubyte * 64)
        _proto(
            "xlLinSetFrameResponse",
            c_int,
            c_int,
            ctypes.c_ulonglong,
            POINTER(XL_LIN_MSG),
            c_uint,
        )
        _proto("xlLinSendRequest", c_int, c_int, ctypes.c_ulonglong, c_ubyte, c_uint)
        _proto("xlReceive", c_int, c_int, POINTER(c_uint), POINTER(XL_EVENT))
        _proto("xlSetNotification", c_int, c_int, POINTER(ctypes.c_void_p), c_int)
        _proto("xlGetErrorString", c_char_p, c_int)

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

    def get_driver_config(self) -> XL_DRIVER_CONFIG:
        """Return the current Vector driver configuration structure."""
        cfg = XL_DRIVER_CONFIG()
        status = self._dll.xlGetDriverConfig(ctypes.byref(cfg))
        if status != XL_SUCCESS:
            raise VectorXLError("xlGetDriverConfig", status)
        return cfg

    def lin_channels(
        self, cfg: Optional[XL_DRIVER_CONFIG] = None
    ) -> List[XL_CHANNEL_CONFIG]:
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
        """Set data length for each of the 64 LIN frame IDs (0–63)."""
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

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def error_string(self, status: int) -> str:
        """Return the Vector driver error string for a status code."""
        raw = self._dll.xlGetErrorString(status)
        return raw.decode("ascii", errors="replace") if raw else f"status={status:#x}"
