Overview
========

Project Metadata
----------------

- Author: Amine Khettat
- Company: BLIND SYSTEMS
- Website: https://www.blindsystems.org
- Version: 0.6.0

Main Capabilities
-----------------

- Parse LIN Description Files and present them in an accessible hierarchy tree
  with breadcrumb navigation, type-ahead search, and screen reader support.
- Connect to Vector-backed LIN hardware with a simulation fallback, managed in
  a separate communication window.
- Validate parsed LDF content with practical consistency rules.
- Protect confidential local LDF assets from accidental commit or push.

Architecture
------------

- **GUI toolkit:** PySide6 (Qt 6)
- **Main window:** LDF viewer with hierarchy tree, search bar, and breadcrumb
- **Communication window:** Separate top-level window for hardware controls and
  live frame monitoring
- **Core:** Framework-agnostic parser, presenter, and consistency modules

Accessibility Features (0.6.0)
------------------------------

- Keyboard-driven navigation with documented shortcuts
- Type-ahead search (Ctrl+F) with match count announcements
- Breadcrumb trail showing current position in the hierarchy
- Sibling navigation (Alt+Up/Down) with position announcements
- Expand/collapse all children (Ctrl+Shift+Right/Left)
- QAccessible events for screen reader notification
- RGAA 4.1.2 automatic compliance (16/16 checks)

Runtime and Selection Safeguards (0.6.0)
----------------------------------------

- Single-instance guard prevents launching a second Easy-LIN process.
- Communication startup requires one selected master node and at least one selected slave node.
- Node checkbox selection is locked while communication is connected.
- Node checkbox selection is unlocked when communication returns to disconnected state.

Build The HTML Documentation
----------------------------

From the repository root, run:

.. code-block:: powershell

   .\.venv\Scripts\python.exe -m sphinx -b html docs docs\_build\html

The generated site is written under ``docs\_build\html``.
