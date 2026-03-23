# Easy-LIN Todo

Date: 2026-03-23

## In Progress

- [ ] Add DLL provenance/status message in communication window.
- [ ] Add runtime integrity preflight check before connect.

## Next (0.8.0 Communication Window Upgrade)

- [ ] Build dedicated per-slave panel cards in the communication window.
- [ ] Add slave card sections for telemetry widgets and command controls.
- [ ] Integrate PyQtGraph gauges for slave->master telemetry visualization.
- [ ] Display textual signal value with units alongside each gauge widget.
- [ ] Map master->slave physical signals to engineering-unit fields.
- [ ] Map master->slave logic/flag signals to dropdown selectors only.
- [ ] Implement slave->master LIN Comm error as strict 1-bit flag handling.
- [ ] Add input validation for physical ranges and enumerated logic values.
- [ ] Add GUI tests for per-slave rendering and card interactions.
- [ ] Add feature tests for signal-type widget mapping and send-value validation.
- [ ] Add tests for LIN Comm error 1-bit semantics.

## Backlog

- [ ] Add monitor CSV export UI action and tests.
- [ ] Consolidate overlapping integration-style GUI tests.
- [ ] Add troubleshooting docs for common autonomous runtime failures.
