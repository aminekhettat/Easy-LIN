# Communication Mission Status (Easy-LIN)

Date: 2026-03-23

## Release Versioning

- Current release: `0.7.0`
- Next patch release target: `0.7.1`
- Next minor release target: `0.8.0`

Release rationale:

- `0.7.0` is the right current release because the repo accumulated several user-visible feature additions and safeguards since `0.6.0`, not just isolated fixes.
- `0.7.1` is reserved for tightening diagnostics, integrity checks, and documentation without broadening scope.
- `0.8.0` is reserved for the next larger communication workflow increment once the hardening line is complete.

## Completed

- Vendored Vector runtime and docs into project:
  - `third_party/vector/bin/vxlapi64.dll`
  - `third_party/vector/bin/vxlapi.dll`
  - `third_party/vector/bin/vxlapi.h`
  - `third_party/vector/ReadMe.txt`
  - `third_party/vector/doc/XL Driver Library - Description.pdf`
  - `third_party/vector/doc/TC_XLDriverLibrary_VI.pdf`
- Updated `src/vector_xl_api.py` to resolve DLLs with local-first priority:
  1. `third_party/vector/bin`
  2. OS library lookup
  3. common Vector install paths
- Added communication backend documentation for autonomous behavior:
  - `src/communication/README.md`
  - `README.md`
- Added single-instance startup protection:
  - `src/main_qt.py` now uses a lock file and blocks duplicate process launch.
- Added communication node preselection guardrails in GUI:
  - Nodes in `src/gui/ldf_viewer.py` are checkable for master/slave preselection.
  - Communication selection requires one master and at least one slave.
  - Node checkboxes are locked while communication is connected.
  - Wiring and status synchronization handled in `src/gui/main_window_qt.py`.
- Completed a broad GUI accessibility pass:
  - Added accessible names and descriptions across application-owned windows, dialogs, toolbars, containers, communication controls, and monitor widgets.
  - Expanded automated regression coverage for accessibility metadata and dialog behavior.
- Validation complete after changes:
  - `pytest -q` with strict 100% global coverage
  - `ruff check src/ tests/`
  - `pylint main.py src tests tools`
  - `python -m sphinx -b html docs docs/_build/html`

## Remaining High-Priority Gaps for 0.7.1

- Remove legacy `python-can` dependency path from communication wording and architecture docs where direct ctypes is now preferred.
- Add an explicit startup diagnostic in GUI for local DLL provenance (displaying whether DLL loaded from project bundle or system path).
- Add a small runtime integrity check for vendored binaries (file presence + readable + architecture hint).

## Remaining Medium-Priority Gaps for 0.8.0 Planning

- Add a user-facing export in monitor panel (CSV export action/button) instead of test-only serialization path.
- Consolidate duplicate integration-style tests where they overlap with existing GUI coverage to reduce maintenance overhead.
- Add one short troubleshooting section in top-level docs for common autonomous runtime failures (missing DLL, blocked driver service, permission).

## Recommended Next Execution Order

1. Add DLL provenance/status message in communication window.
2. Add runtime integrity preflight check before connect.
3. Add monitor CSV export UI action and tests.
4. Cleanup/merge overlapping GUI integration tests.
