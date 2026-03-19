# Easy-LIN

An open-source LIN master GUI built in Python + PyQt5 for **Vector VN16xx** hardware.
Easy-LIN parses LDF (LIN Description File) files and lets you communicate with LIN slaves
in real time — the application acts as the **LIN master** on the bus.

---

## Features

| Category | Details |
|---|---|
| **LDF Parsing** | Full parser for LIN 1.3 / 2.0 / 2.1 / 2.2 — nodes, signals, frames, schedules, encoding types, node attributes |
| **LDF Viewer** | Tabbed GUI: Overview · Signals · Frames · Schedules · Encodings |
| **Hardware** | Connects to Vector VN16xx (and all XL-Driver-compatible) devices via `vxlapi.dll` |
| **LIN Master** | Sends frame headers (master request) and master-response frames |
| **Schedule Execution** | Runs any schedule table from the LDF automatically in a background thread |
| **Frame Monitor** | Live timestamped log of all received LIN frames with CRC-error detection |
| **Recent Files** | Last 10 opened LDF files remembered across sessions |

---

## Screenshots

### Overview tab — protocol metadata, node topology and network summary
After opening an LDF file the **Overview** tab shows the protocol version, bus speed,
channel name, master/slave node list, and a quick summary of all network objects.

### Signals tab — complete signal table
Every signal in the LDF is listed with its bit size, initial value, publisher node and
subscriber nodes. The table is sortable by any column.

### Frames tab — hierarchical frame browser
Frames are shown in a tree view: each parent row describes the frame (ID, publisher,
size in bytes) and child rows list every signal mapped into it with its bit offset.

### Communication panel (right dock)
* **Hardware Connection** — channel selector with refresh, connect/disconnect toggle
  and a green/red LED status indicator.
* **Send Frame (Manual)** — pick any frame from the LDF, optionally edit the data
  bytes, then send either a master *request* (slave responds) or a master *response*
  (master supplies the data).
* **Schedule Execution** — select a schedule table and click **Run**; Easy-LIN
  cycles through all entries at the LDF-specified delays.
* **Frame Monitor** — scrolling table of every received frame, timestamp in ms,
  hex data bytes, and CRC-error flag.

---

## Hardware requirements

Easy-LIN uses the **Vector XL Driver Library** (`vxlapi.dll` / `vxlapi64.dll`) which
ships with every Vector VN16xx device and is available as a free download from:

> <https://www.vector.com/int/en/products/products-a-z/software/xl-driver-library/>

Supported hardware (any XL-Driver-compatible device with LIN capability):

* VN1610 / VN1611
* VN1630A / VN1630log
* VN1640A
* VN7610 / VN7640

The GUI starts and fully displays LDF files on any platform; hardware communication
requires Windows with the Vector XL Driver installed.

---

## Installation

```bash
# 1. Clone
git clone https://github.com/aminekhettat/Easy-LIN.git
cd Easy-LIN

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt
```

### Requirements

```
PyQt5 >= 5.15
```

No other runtime dependencies — the Vector XL API is accessed directly via `ctypes`.

---

## Usage

```bash
# Launch the GUI
python main.py

# Open an LDF file directly from the command line
python main.py path/to/your_network.ldf
```

Or use **File → Open LDF…** inside the application.

### Connecting to hardware

1. Click **↻ Refresh** in the Communication panel to enumerate connected devices.
2. Select your VN16xx channel from the drop-down list.
3. Click **Connect** (green button); the LED turns green when the channel is active.
4. Use **Send Frame** or **Run** a schedule to communicate with slaves.
5. Click **Disconnect** (red button) to release the hardware.

---

## Project structure

```
Easy-LIN/
├── main.py                        # Application entry point
├── requirements.txt               # Python dependencies
├── src/
│   ├── ldf_parser.py              # LDF file parser (LIN 1.3 / 2.0 / 2.1 / 2.2)
│   ├── vector_xl_api.py           # ctypes wrapper for vxlapi.dll
│   ├── lin_master.py              # High-level LIN master (connect, TX, schedule)
│   └── gui/
│       ├── main_window.py         # QMainWindow — menus, toolbar, status bar
│       ├── ldf_viewer.py          # Tabbed LDF content viewer
│       └── communication_panel.py # Hardware connect / TX / monitor dock
└── tests/
    ├── test_ldf_parser.py         # 40 unit tests for the LDF parser
    └── data/
        └── sample.ldf             # Example LDF file (LIN 2.1, 3 slaves)
```

---

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

All 40 tests cover: protocol metadata, nodes, signals, frames, schedule tables,
encoding types, node attributes, error handling, and negative-number parsing.

---

## LDF file format overview

LDF (LIN Description File) is the standard configuration file for a LIN network.
It describes every object on the bus:

| Section | Contents |
|---|---|
| `Nodes` | Master node (timing) + slave node names |
| `Signals` | Name, bit-size, initial value, publisher/subscriber nodes |
| `Frames` | Frame ID (0x00–0x3B), publisher, byte-length, signal-to-bit-offset map |
| `Schedule_tables` | Ordered list of frames with inter-frame delays (ms) |
| `Signal_encoding_types` | Logical values (enum) and physical ranges (scale/offset/unit) |
| `Node_attributes` | NAD, product ID, response-error signal, LIN 2.x diagnostics timing |

---

## License

Personal, non-commercial use only.  
Commercial use or redistribution requires written permission from the author.

