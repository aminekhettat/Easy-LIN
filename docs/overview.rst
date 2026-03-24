Overview
========

Project Metadata
----------------

- Author: Amine Khettat
- Company: BLIND SYSTEMS
- Website: https://www.blindsystems.org
- Version: see Release Roadmap

Main Capabilities
-----------------

- Parse LIN Description Files and expose protocol/frame/signal structure in a
  navigable hierarchy.
- Operate LIN communication on Vector-backed channels from a dedicated runtime
  window.
- Validate parsed LDF content with practical consistency rules.
- Protect confidential local LDF assets from accidental commit or push.

Architecture
------------

- **GUI toolkit:** PySide6 (Qt 6)
- **Main window:** LDF viewer with hierarchy tree, search bar, and breadcrumb
- **Communication window:** Separate top-level window for hardware controls and
  live frame monitoring and start/stop CSV logging
- **Core:** Framework-agnostic parser, presenter, and consistency modules

Primary Engineering Objective
-----------------------------

- Reduce time from LDF intake to executable LIN communication workflows.
- Keep parsing, validation, runtime control, and telemetry capture in one tool.
- Maintain deterministic behavior through explicit runtime safeguards and
  status tracking.

Runtime and Selection Safeguards
----------------------------------------

- Single-instance guard prevents launching a second Easy-LIN process.
- Communication startup requires one selected master node and at least one selected slave node.
- Node checkbox selection is locked while communication is connected.
- Node checkbox selection is unlocked when communication returns to disconnected state.

Accessibility Support
-----------------------------

Accessibility is implemented as a dedicated support layer on top of the core
technical workflows above.

- Keyboard-driven navigation with documented shortcuts
- Type-ahead search (Ctrl+F) with match count announcements
- Breadcrumb trail showing current position in the hierarchy
- Sibling navigation (Alt+Up/Down) with position announcements
- Expand/collapse all children (Ctrl+Shift+Right/Left)
- QAccessible events for screen reader notification
- RGAA 4.1.2 automatic compliance (16/16 checks)
- Accessible names and descriptions on application-owned windows, dialogs, major controls, monitor widgets, and hierarchy support elements

Release Roadmap
---------------

- Current release: 0.8.3
- Next patch release: 0.7.3, focused on runtime diagnostics, integrity checks, and troubleshooting guidance
- Next minor release: 0.8.0, focused on the next larger communication workflow increment after the 0.7.x hardening line

LIN Runtime Workflows
---------------------

- **Master-only workflow**

  - Open driver and port with init access.
  - Configure LIN channel parameters, DLC/checksum policy, and notification.
  - Activate channel, send master requests, and receive LIN message events.

- **Master + runtime slave workflow**

  - Configure slave responses for selected LIN IDs via runtime API.
  - Toggle individual slave tasks on/off during measurement.
  - Keep scheduler/request flow active while updating slave data.

- **Sleep/wakeup workflow**

  - Enter sleep mode with optional wake-up ID policy.
  - Transmit wake-up pattern and continue normal communication sequence.

- **Live CSV capture workflow**

  - Start logging directly from the communication window without stopping acquisition.
  - Write a metadata section first so the CSV captures LDF file context and selected master/slave names.
  - Append each received frame to a CSV row with wall-clock timestamp, transfer direction, frame ID, DLC, status, checksum, and hex payload.
  - Stop logging at any time; active logging is also closed when the communication window is hidden.

- **Asynchronous viewer/communication synchronization**

  - LDF loads and node-selection changes are queued and coalesced before they reach the communication window.
  - This avoids blocking the parsing/viewer workflow while still keeping the communication state aligned with the latest LDF and node-selection context.
  - The communication panel accepts only the active LDF master and its declared slaves, so stale selections from another network are discarded before they can gate runtime actions.

Hardware Support Assumptions
----------------------------

- Supported target is any Windows Vector interface exposing LIN-capable channels via XL Driver Library.
- Discovery is dynamic from the active driver configuration and not restricted to a single device family.
- LIN startup requires init access and reports explicit failure if permission is not granted.

Build The HTML Documentation
----------------------------

From the repository root, run:

.. code-block:: powershell

   .\.venv\Scripts\python.exe -m sphinx -b html docs docs\_build\html

The generated site is written under ``docs\_build\html``.
