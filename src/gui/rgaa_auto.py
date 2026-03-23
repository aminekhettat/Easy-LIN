"""Automatic RGAA-equivalent accessibility checks for the Qt GUI.

This module scopes checks to criteria that are objectively testable in code for
this desktop application (labels, keyboard access, focus visibility, and status
messaging semantics).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt


@dataclass(frozen=True)
class RGAAAutoComplianceReport:
    """Result of automatic RGAA-equivalent checks."""

    passed: int
    total: int

    @property
    def percentage(self) -> float:
        """Return compliance percentage in the ``0..100`` range."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0


def evaluate_main_window_automatic_rgaa(main_window) -> RGAAAutoComplianceReport:
    """Evaluate deterministic accessibility checks for the Qt main window."""
    checks = []

    viewer = getattr(main_window, "centralWidget", lambda: None)()
    tree = getattr(viewer, "_tree", None)

    # Access comm panel through communication window when separated
    comm_window = getattr(main_window, "_comm_window", None)
    comm = getattr(comm_window, "_comm_panel", None) if comm_window else None
    if comm is None:
        comm = getattr(main_window, "_comm_panel", None)

    checks.append(tree is not None)
    checks.append(bool(getattr(tree, "accessibleName", lambda: "")().strip()) if tree else False)
    checks.append(
        bool(getattr(tree, "accessibleDescription", lambda: "")().strip()) if tree else False
    )
    checks.append(tree.focusPolicy() == Qt.FocusPolicy.StrongFocus if tree else False)
    checks.append(":focus" in tree.styleSheet() if tree else False)

    # Keyboard shortcut checks (RGAA navigation keyboard spirit)
    shortcuts = [
        getattr(main_window, "_shortcut_focus_tree", None),
        getattr(main_window, "_shortcut_focus_details", None),
        getattr(main_window, "_shortcut_next_region", None),
        getattr(main_window, "_shortcut_prev_region", None),
    ]
    checks.append(all(shortcut is not None for shortcut in shortcuts))
    checks.append(
        all(shortcut.context() == Qt.ShortcutContext.ApplicationShortcut for shortcut in shortcuts if shortcut)
    )

    # Ensure no single-character shortcut exists among main shortcuts.
    checks.append(
        all(
            len(shortcut.key().toString().replace("+", "").strip()) > 1
            for shortcut in shortcuts
            if shortcut and shortcut.key().toString().strip()
        )
    )

    # Labeling checks (RGAA form/script assistive-tech spirit)
    checks.append(bool(comm and comm._refresh_btn.accessibleName().strip()))
    checks.append(bool(comm and comm._connect_btn.accessibleName().strip()))
    checks.append(bool(comm and comm._channel_combo.accessibleName().strip()))
    checks.append(bool(comm and comm._channel_combo.accessibleDescription().strip()))
    checks.append(bool(comm and comm._send_btn.accessibleName().strip()))
    checks.append(bool(comm and comm._frame_combo.accessibleName().strip()))
    checks.append(bool(comm and comm._data_edit.accessibleName().strip()))
    checks.append(bool(comm and comm._data_edit.accessibleDescription().strip()))
    checks.append(bool(comm and comm._sched_start_btn.accessibleName().strip()))
    checks.append(bool(comm and comm._sched_stop_btn.accessibleName().strip()))
    checks.append(bool(comm and comm._sched_combo.accessibleName().strip()))
    checks.append(bool(comm and comm._changed_only_chk.accessibleDescription().strip()))
    checks.append(bool(comm and comm._monitor._table.accessibleName().strip()))
    checks.append(bool(comm and comm._monitor._table.accessibleDescription().strip()))

    # Status information must be textual, not color-only.
    checks.append(main_window._sb_comm.text().startswith("Comm:"))
    checks.append(main_window._sb_issues.text().startswith("LDF issues:"))
    checks.append(main_window._sb_event.text().startswith("Last event:"))

    passed = sum(1 for check in checks if check)
    return RGAAAutoComplianceReport(passed=passed, total=len(checks))
