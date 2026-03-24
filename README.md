# Easy-LIN

Current release: 0.8.1

Planned next patch release: 0.8.2

Planned next minor release: 0.9.0

## Automated Version Bump

Easy-LIN uses `bump2version` to increment the project subversion consistently across runtime and documentation anchors.

Patch bump (for example 0.8.0 -> 0.8.1):

```bash
bump2version patch
```

Minor bump (for example 0.8.x -> 0.9.0):

```bash
bump2version minor
```

Major bump:

```bash
bump2version major
```

Notes:

- Version automation config is in `.bumpversion.cfg`.
- This updates only canonical version anchors. Keep release roadmap lines (like "Planned next patch release") aligned during release preparation.

Easy-LIN is a Python engineering tool for LIN (Local Interconnect Network), built with PySide6 (Qt 6).

It is designed around two core technical workflows:

- Parsing and inspecting LDF files with structured hierarchy, protocol metadata, and frame/signal details.
- Operating LIN communication over Vector-backed channels (connect, request/response, scheduling, and monitoring), with simulation fallback when hardware is unavailable.

## Purpose

Easy-LIN provides one operational workspace for:

- LDF parsing, hierarchy exploration, and consistency validation
- Runtime LIN communication control on supported Vector hardware
- Session observability through status tracking and CSV trace export

## Features

### LDF Interpretation

- Parse LDF content (LIN 1.3, 2.0, 2.1, 2.2 style structures)
- Display nodes, signals, frames, schedules, and encodings in a hierarchy tree
- Expand/collapse all children of current item
- LDF consistency validation with detailed report
- Node checkboxes for communication preselection (one master, at least one slave)
- Node checkbox state is locked while communication is connected

### Communication (Vector USB)

- Managed in a separate window (View > Communication Window or Ctrl+Shift+C)
- Vector transport through `python-can` + Vector XL driver
- Connect/disconnect, send frames, monitor RX/TX
- Start and stop live CSV logging while the communication window remains open
- Logged CSV files start with session metadata (LDF file, master/slave names, protocol details)
- Logged frames include timestamp, transfer direction, frame identity, status, checksum, and hex payload
- Communication selection only accepts the active LDF master and its declared slaves, preventing stale cross-network selections from reaching the runtime panel
- Automatic simulation mode when Vector backend is not available

### LIN Runtime Workflows

- **Master-only**: open one LIN-capable channel with init access, configure DLC/checksum, activate channel, send master headers, receive frame events.
- **Master + slave task**: configure runtime slave responses (`xlLinSetSlave`) for selected IDs, then enable/disable each slave response during measurement (`xlLinSwitchSlave`).
- **Sleep / wakeup cycle**: set sleep mode with optional wake-up ID policy, then send wake-up pattern and continue request scheduling.
- **Viewer-to-communication sync**: LDF and node-selection changes are queued onto the Qt event loop before being applied to the communication window, so viewer operations stay responsive while communication state remains synchronized.

### Supported Hardware Assumptions

- Easy-LIN supports **LIN-capable Vector channels exposed by XL Driver Library** on Windows.
- Channel discovery uses the live XL driver configuration and does not hardcode one specific VN family.
- Operations requiring init access (notably LIN open/startup) fail fast with explicit error reporting.
- If no usable Vector backend is available, the communication layer can run in simulation mode for UI and functional testing.

## Official Documentation References

### Vector

- Vector XL Driver Library product page:
  https://www.vector.com/int/en/products/products-a-z/software/xl-driver-library/
- `python-can` Vector backend docs:
  https://python-can.readthedocs.io/en/stable/interfaces/vector.html

### LIN Standards and Conformance

- LIN Specification Package 2.2A (public package reference):
  https://www.lin-cia.org/standards/
- ISO 17987 road vehicles LIN family (conformance basis):
  https://www.iso.org/standard/69815.html

Note: ISO standards are copyrighted and typically distributed via official ISO channels.

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Autonomous Vector Runtime

Easy-LIN can run with a project-local Vector runtime bundle (no global path setup required).

- Runtime DLLs are vendored under `third_party/vector/bin`
- Vector manuals are vendored under `third_party/vector/doc`
- The loader in `src/vector_xl_api.py` now checks `third_party/vector/bin` first, then falls back to system installation paths

## Runtime Safety Guards

- Easy-LIN enforces single-instance startup with a lock file in the OS temp folder.
- If another instance is already running, startup is refused with an explicit warning dialog.
- Before communication starts, the selected communication set must include one master and at least one slave.
- While communication is connected, node checkbox selection is locked to prevent mid-session topology drift.

## Accessibility

Accessibility is a dedicated support layer that complements the core LIN parsing
and communication workflows described above.

The PySide6 interface is optimized for keyboard and screen-reader usage.

### Main Accessibility Capabilities

- Keyboard-first workflow with explicit shortcuts
- Screen-reader-friendly tree labels (no decorative symbols)
- Breadcrumb trail showing current position in the hierarchy
- Type-ahead search with match count announcements
- Sibling navigation and position announcements ("Item 3 of 5")
- Status bar narration for every event
- QAccessible event notifications for screen readers
- Dedicated focus shortcuts for major interface regions
- Accessible names and descriptions across application-owned windows, dialogs, controls, and monitoring widgets

### Keyboard Shortcuts

- `Ctrl+O`: Open an LDF file
- `Ctrl+1`: Focus hierarchy tree
- `Ctrl+2`: Focus communication window
- `Ctrl+Shift+C`: Toggle communication window
- `Ctrl+C`: Copy focused hierarchy line
- `Ctrl+F`: Search in hierarchy tree
- `F3`: Find next match
- `Alt+Up/Down`: Navigate to previous/next sibling
- `Ctrl+Shift+Right`: Expand all children of current item
- `Ctrl+Shift+Left`: Collapse all children of current item
- `F6`: Move focus to next major region
- `Shift+F6`: Move focus to previous major region
- `F1`: Open accessibility help

### Navigation Behavior

- After loading an LDF file, focus is moved directly to the hierarchy tree
- Breadcrumb trail shows the path from root to the current item
- Position announcements ("Item 3 of 5") provide context among siblings
- Hierarchy view supports expand/collapse navigation with standard tree keyboard behavior
- Region shortcuts let you jump directly without repeated tabbing
- `Tab` and `Shift+Tab` continue navigation inside the currently focused region
- Bottom status bar tracks persistent fields for LDF summary, LDF warnings/errors, communication state, and latest event

### Screen Reader Notes

- Tree labels and tab names avoid decorative symbols to improve speech clarity
- Key values are exposed directly in tree rows (for example: `Protocol version: 2.1`)
- Status bar messages summarize loading and communication state changes
- Persistent status fields are color-coded: green (healthy), amber (warning/no hardware), red (error), blue (informational)
- QAccessible events are fired on navigation changes
- RGAA 4.1.2 (automatable criteria scope): 100% compliant on implemented automatic checks (16/16), validated by automated tests.

## Testing and Coverage

This project enforces strict 100% coverage on all modules.

```bash
pytest
```

- Coverage configuration: `.coveragerc`
- CI workflow: `.github/workflows/ci.yml`
- Target: 100% coverage for all modules

## Linting

Ruff provides the fast default lint pass for import hygiene, correctness issues,
and modern Python cleanup.

```bash
ruff check src/ tests/
```

Pylint provides a second pass tuned for this codebase's parser, GUI, PySide6, and
ctypes integration layers.

```bash
pylint main.py src tests tools
```

CI also validates Sphinx docs generation:

```bash
python -m sphinx -b html docs docs/_build/html
```

## Project Structure

```text
Easy-LIN/
|- main.py
|- requirements.txt
|- src/
|  |- ldf_parser.py
|  |- ldf_presenter.py
|  |- ldf_consistency.py
|  |- lin_master.py
|  |- vector_xl_api.py
|  |- main_qt.py
|  |- communication/
|  |  |- vector_lin.py
|  |- gui/
|  |  |- main_window_qt.py
|  |  |- ldf_viewer.py
|  |  |- communication_window.py
|  |  |- communication_panel.py
|  |  |- rgaa_auto.py
|- tests/
|  |- test_feature_ldf_parser_core.py
|  |- test_feature_accessible_presentation.py
|  |- test_feature_vector_lin_transport.py
|  |- test_feature_ldf_consistency.py
|  |- test_feature_ldf_hierarchy_completeness.py
|  |- test_feature_ldf_validation_gate.py
|  |- test_feature_qt_accessibility_navigation.py
|  |- test_feature_rgaa_automatic_compliance.py
|  |- (+ additional coverage tests)
|- docs/
|- third_party/
|  |- vector/
|  |  |- bin/
|  |  |- doc/
|- .github/workflows/ci.yml
|- .coveragerc
|- pytest.ini
```

## License

See `LICENSE`.
