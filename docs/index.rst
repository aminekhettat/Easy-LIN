Easy-LIN Documentation
======================

Easy-LIN is an accessibility-first Python application for LIN engineering,
built with PySide6. The documentation below covers the public entry points,
source modules, communication window, tooling, and automated tests for
version 0.7.0.

RGAA 4.1.2 (automatable criteria scope): 100% compliant on implemented
automatic checks (16/16), validated by automated tests.

Accessibility enhancements in 0.7.0:

- Type-ahead search in the hierarchy tree (Ctrl+F)
- Breadcrumb trail showing current position
- Sibling navigation (Alt+Up/Down)
- Expand/collapse all (Ctrl+Shift+Right/Left)
- Position announcements ("Item 3 of 5")
- QAccessible event notifications for screen readers
- Node checkbox preselection rules for communication (one master, at least one slave)
- Node checkbox locking while communication is connected
- Single-instance application startup protection
- Accessible names and descriptions on application-owned windows, dialogs, toolbars, containers, monitor widgets, and major controls

Planned releases:

- 0.7.1 for runtime hardening and diagnostics
- 0.8.0 for the next larger communication workflow increment

The communication panel is now a separate window (View > Communication
Window or Ctrl+Shift+C), allowing independent management of LDF analysis
and hardware communication.

.. note::

   Easy-LIN is distributed under the Easy-LIN Source-Available License
   Version 1.0. Refer to the repository LICENSE file for usage restrictions,
   warranty exclusions, and liability limitations.

Contents
--------

.. toctree::
   :maxdepth: 2

   overview
   api
