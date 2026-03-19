Overview
========

Project Metadata
----------------

- Author: Amine Khettat
- Company: BLIND SYSTEMS
- Website: https://www.blindsystems.org
- Version: 0.5.0

Main Capabilities
-----------------

- Parse LIN Description Files and present them in accessible tree and text views.
- Connect to Vector-backed LIN hardware with a simulation fallback.
- Validate parsed LDF content with practical consistency rules.
- Protect confidential local LDF assets from accidental commit or push.

Build The HTML Documentation
----------------------------

From the repository root, run:

.. code-block:: powershell

   .\.venv\Scripts\python.exe -m sphinx -b html docs docs\_build\html

The generated site is written under ``docs\_build\html``.
