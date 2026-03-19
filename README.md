# Easy-LIN
Fully Vibe coded LIN communication tool with full management of LDF files.

## Overview

Easy-LIN is a Python GUI application for working with the **LIN (Local Interconnect Network)** bus protocol.  It lets you:

- **Open and parse** LIN Description Files (`.ldf`) — LIN spec versions 1.3, 2.0, 2.1 and 2.2
- **Inspect** every LDF element in an interactive tree view (nodes, signals, frames, schedule tables, encoding types, node attributes)
- **See detailed, human-readable information** about every selected element including signal bit layout, byte diagrams and value encoding tables
- **Communicate on a real LIN bus** via **Vector CAN** hardware (XL-driver) — send frames, monitor RX/TX traffic, and work with schedule tables
- **Simulate** without hardware — the application falls back to a software simulation mode when no Vector hardware is detected

![Easy-LIN Screenshot](https://github.com/user-attachments/assets/2870be9b-8005-4812-8866-599294431cde)

---

## Project structure

```
Easy-LIN/
├── main.py                        Application entry point
├── requirements.txt               Python dependencies
├── src/
│   ├── ldf/
│   │   └── parser.py              LDF file parser (pure Python, no external deps)
│   ├── communication/
│   │   └── vector_lin.py          Vector CAN/LIN bus wrapper (python-can)
│   └── gui/
│       ├── main_window.py         Main application window
│       ├── ldf_tree.py            LDF tree-view widget
│       ├── signal_viewer.py       Detail / signal viewer panel
│       └── comm_panel.py          LIN communication panel
└── tests/
    ├── test_ldf_parser.py         56 unit tests for the LDF parser
    └── fixtures/
        └── sample.ldf             Sample LDF file for testing
```

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **tkinter** must also be available (it is included with most Python installers; on Debian/Ubuntu run `sudo apt-get install python3-tk`).

### 2. Run the application

```bash
python main.py
```

### 3. Open an LDF file

Use **File → Open LDF…** (or `Ctrl+O`) and select any `.ldf` file.

---

## LDF Parser

The built-in parser handles all standard LDF sections:

| Section | Description |
|---|---|
| `Nodes` | Master and slave node definitions |
| `Signals` | Signal names, sizes, init values, publishers, subscribers |
| `Frames` | Frame IDs, publishers, lengths, signal layouts |
| `Schedule_tables` | Schedule entries with delay values |
| `Signal_encoding_types` | Logical, physical, BCD and ASCII value encodings |
| `Signal_representation` | Signal-to-encoding-type mapping |
| `Node_attributes` | NAD, product ID, response error, timing (LIN 2.x) |

---

## LIN Communication (Vector CAN)

The communication panel connects to a **Vector LIN channel** via the `python-can` library and the XL-driver:

- Select the channel index and bitrate, then click **Connect**
- The frame monitor table shows every TX and RX frame in real time, colour-coded by direction
- Use the **Send Frame** bar to transmit any frame by ID + data bytes
- Pre-fill the send bar by picking a frame from the **Frame** drop-down (populated from the loaded LDF)
- If no Vector hardware is found the application switches to **simulation mode** automatically — transmitted frames are echoed back as received frames so the UI can still be exercised

### Requirements for real hardware

- Vector VN-series or CANalyzer/CANoe CAN/LIN interface
- [Vector XL-driver](https://www.vector.com/int/en/products/products-a-z/software/xl-driver-library/) installed on the host
- `python-can >= 4.0.0`

---

## Running the tests

```bash
python -m pytest tests/ -v
```

All 56 tests should pass.

---

## Dependencies

| Package | Purpose |
|---|---|
| `tkinter` | GUI (Python standard library) |
| `python-can >= 4.0.0` | Vector CAN/LIN hardware communication |
| `pytest >= 7.0` | Test framework |

