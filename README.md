# Easy-LIN

Current release: 0.6.0

Easy-LIN is an accessibility-first Python application for LIN (Local Interconnect Network) engineering, built with PySide6 (Qt 6).

It focuses on two workflows:

- Interpreting LDF files with a hierarchy tree, breadcrumb navigation, type-ahead search, and plain-language textual explanations for screen readers.
- Connecting to Vector hardware over USB and sending/monitoring LIN traffic in a separate communication window (with simulation fallback when hardware is unavailable).

## Accessibility Goals

The GUI is designed for blind and low-vision users:

- Keyboard-first workflow with explicit shortcuts
- Screen-reader-friendly tree labels (no decorative symbols)
- Breadcrumb trail showing current position in the hierarchy
- Type-ahead search with match count announcements
- Sibling navigation and position announcements ("Item 3 of 5")
- Status bar narration for every event
- QAccessible event notifications for screen readers
- Dedicated focus shortcuts for major interface regions

## Features

### LDF Interpretation

- Parse LDF content (LIN 1.3, 2.0, 2.1, 2.2 style structures)
- Display nodes, signals, frames, schedules, and encodings in a hierarchy tree
- Breadcrumb trail and position announcements for navigation context
- Type-ahead search (Ctrl+F) to find items in the tree
- Expand/collapse all children of current item
- LDF consistency validation with detailed report
- Node checkboxes for communication preselection (one master, at least one slave)
- Node checkbox state is locked while communication is connected

### Communication (Vector USB)

- Managed in a separate window (View > Communication Window or Ctrl+Shift+C)
- Vector transport through `python-can` + Vector XL driver
- Connect/disconnect, send frames, monitor RX/TX
- Automatic simulation mode when Vector backend is not available

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

The PySide6 interface is optimized for keyboard and screen-reader usage.

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
