# Easy-LIN

Current release: 0.5.2

Easy-LIN is an accessibility-first Python application for LIN (Local Interconnect Network) engineering.

It focuses on two workflows:

- Interpreting LDF files with a tree view and plain-language textual explanations for screen readers.
- Connecting to Vector hardware over USB and sending/monitoring LIN traffic (with simulation fallback when hardware is unavailable).

## Accessibility Goals

The GUI is designed for blind and low-vision users:

- Keyboard-first workflow with explicit shortcuts
- Screen-reader-friendly tree labels (no decorative symbols)
- Status bar narration and detailed text panel for every selected item
- Clear, professional layout with standard menu, status bar, split panes, and communication console
- Dedicated focus shortcuts for major interface regions

## Features

### LDF Interpretation

- Parse LDF content (LIN 1.3, 2.0, 2.1, 2.2 style structures)
- Display nodes, signals, frames, schedules, and encodings in a tree view
- Show textual explanation for each selected item

### Communication (Vector USB)

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

Legacy Tk launcher (fallback only):

```bash
python main.py --tk
```

## Accessibility

The default Qt interface is optimized for keyboard and screen-reader usage.

Known limitation (0.5.2): accessibility behaviors were improved, but the interface is still not reliably usable in day-to-day operation. Ongoing stabilization work is required before production use.

### Keyboard Shortcuts

- `Ctrl+O`: Open an LDF file
- `Ctrl+1`: Focus hierarchy tree
- `Ctrl+2`: Focus communication panel
- `Ctrl+C`: Copy focused hierarchy line
- `F6`: Move focus to next major region
- `Shift+F6`: Move focus to previous major region
- `F1`: Open accessibility help

### Navigation Behavior

- After loading an LDF file, focus is moved directly to the hierarchy tree
- Hierarchy view supports expand/collapse navigation with standard tree keyboard behavior
- Region shortcuts let you jump directly without repeated tabbing
- `Tab` and `Shift+Tab` continue navigation inside the currently focused region
- Bottom status bar tracks persistent fields for LDF summary, LDF warnings/errors, communication state, and latest event

### Screen Reader Notes

- Tree labels and tab names avoid decorative symbols to improve speech clarity
- Key values are exposed directly in tree rows (for example: `Protocol version: 2.1`)
- Status bar messages summarize loading and communication state changes
- Persistent status fields are color-coded: green (healthy), amber (warning/no hardware), red (error), blue (informational)
- RGAA 4.1.2 (automatable criteria scope): 100% compliant on implemented automatic checks (16/16), validated by automated tests.

## Testing and Coverage

This project enforces strict coverage in CI.

```bash
pytest
```

- Coverage configuration: `.coveragerc`
- CI workflow: `.github/workflows/ci.yml`
- Target: 100% coverage for covered modules

## Linting

Ruff provides the fast default lint pass for import hygiene, correctness issues,
and modern Python cleanup.

```bash
ruff check .
```

Pylint provides a second pass tuned for this codebase's parser, GUI, PyQt, and
ctypes integration layers.

```bash
pylint main.py src tests tools
```

## Project Structure

```text
Easy-LIN/
|- main.py
|- requirements.txt
|- src/
|  |- ldf_parser.py
|  |- ldf_presenter.py
|  |- communication/
|  |  |- vector_lin.py
|  |- gui/
|  |  |- main_window.py
|  |  |- ldf_tree.py
|  |  |- signal_viewer.py
|  |  |- comm_panel.py
|- tests/
|  |- test_feature_ldf_parser_core.py
|  |- test_feature_accessible_presentation.py
|  |- test_feature_vector_lin_transport.py
|- .github/workflows/ci.yml
|- .coveragerc
|- pytest.ini
```

## License

See `LICENSE`.
