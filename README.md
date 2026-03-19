# Easy-LIN

Easy-LIN is an accessibility-first Python application for LIN (Local Interconnect Network) engineering.

It focuses on two workflows:

- Interpreting LDF files with a tree view and plain-language textual explanations for screen readers.
- Connecting to Vector hardware over USB and sending/monitoring LIN traffic (with simulation fallback when hardware is unavailable).

## Accessibility Goals

The GUI is designed for blind and low-vision users:

- Keyboard-first workflow with explicit shortcuts (`Ctrl+O`, `Ctrl+1`, `Ctrl+2`, `F1`)
- Screen-reader-friendly tree labels (no decorative symbols)
- Status bar narration and detailed text panel for every selected item
- Clear, professional layout with standard menu, status bar, split panes, and communication console

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

Optional preserved PyQt launcher:

```bash
python main.py --qt
```

## Testing and Coverage

This project enforces strict coverage in CI.

```bash
pytest
```

- Coverage configuration: `.coveragerc`
- CI workflow: `.github/workflows/ci.yml`
- Target: 100% coverage for covered modules

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
