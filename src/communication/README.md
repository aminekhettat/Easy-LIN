# Communication Backend (Vector XL ctypes)

This directory contains the communication backend used by Easy-LIN.

## Prerequisites

- Windows 10/11 64-bit
- Vector XL Driver Library installed
- `vxlapi64.dll` available in one of these locations:
  - `third_party\vector\bin` (project-local, preferred)
  - `C:\Users\Public\Documents\Vector\XL Driver Library\bin`
  - `C:\Program Files\Vector XL Driver Library\bin`
  - `C:\Program Files (x86)\Vector XL Driver Library\bin`

## Autonomous Behavior

`src/vector_xl_api.py` resolves DLLs in this order:

1. Project-local bundle: `third_party\vector\bin`
2. Standard Windows library lookup
3. Common Vector installation folders

## Main Modules

- `src/vector_xl_api.py`: low-level ctypes wrapper around Vector XL API
- `src/communication/hardware_discovery.py`: hardware and LIN channel scan
- `src/communication/lin_controller.py`: high-level LIN connect/send/receive/scheduler
- `src/communication/exceptions.py`: communication-specific exceptions

## Quick Usage Example

```python
from src.communication.hardware_discovery import HardwareDiscovery
from src.communication.lin_controller import LINController, LINMode

channels = HardwareDiscovery().get_lin_channels()
if not channels:
    raise RuntimeError("No LIN-capable Vector channel found")

controller = LINController()
controller.connect(channels[0], baudrate=19200, mode=LINMode.MASTER)
controller.send_master_request(0x10)
frame = controller.receive_frame(timeout_ms=50)
controller.disconnect()
```

## Supported Hardware (typical)

- CANcaseXL
- VN1600 family
- VN1610 family
- Virtual channels (driver-dependent)

## Troubleshooting

- `VectorXLDriverNotFoundError`: install/reinstall Vector XL Driver Library.
- `xlOpenDriver returned status ...`: verify license and driver service state.
- `get_channel_mask returned status ...`: selected channel not present.
- No frames received: validate LIN bitrate and master/slave role.
