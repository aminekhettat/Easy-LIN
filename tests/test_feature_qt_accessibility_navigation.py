"""
Atomic features covered:
- Build a single hierarchical Qt LDF tree with inline attributes and values
- Link each slave node to related frames
- Show frame signal characteristics and encoding attributes directly inside frame nodes
- Place diagnostic frames before schedule tables
- Avoid a duplicated top-level signals section outside nodes
- Keep tree selection anchored on expanded/collapsed items
- Keep Right-arrow expansion anchored on current item (no forced jump)
- Announce opened/closed hierarchy rows for non-visual feedback
- Toggle checkable communication nodes from keyboard (Space/Enter)
- Ignore Space/Enter on non-checkable rows and announce lock state when selection is locked
- Allow temporary zero-slave selection with clear guidance for connection step
- Focus hierarchy tree directly after LDF load
- Provide deterministic region focus and region-cycling behavior
- Keep global accessibility shortcuts configured for application-wide handling
- Track persistent status bar fields for LDF issues and communication state
- Color-code status bar fields for quick issue/health recognition
- Provide About window metadata with clickable contact links and company logo
- Traverse expanded tree in depth-first visual order with Down/Up arrow keys
- Enter first child of an expanded branch on Down; ascend to last visible descendant of the preceding sibling on Up
- Skip collapsed branch children when navigating with Down/Up
- Let Right enter the first child of an expanded branch and Left return to its parent
- Keep real bundled LDF files navigable with deterministic top-level traversal
- Prevent non-master/slave tree items from retaining an accidental check state
"""

from __future__ import annotations

# pylint: disable=too-many-lines

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QEvent, QTimerEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.ldf_parser import parse_ldf, parse_ldf_string
from src.gui.ldf_viewer import LDFViewer
import src.gui.ldf_viewer as ldf_viewer
import src.gui.main_window_qt as main_window_qt


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Provide a reusable QApplication for Qt widget tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_ldf_text() -> str:
    """Return a compact LDF sample covering key hierarchy sections."""
    return """
    LIN_description_file ;
    LIN_protocol_version = "2.1" ;
    LIN_language_version = "2.1" ;
    LIN_speed = 19.2 kbps ;
    Channel_name = "CABIN" ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S1, S2 ; }
    Signals {
      S1: 8, 0, M, S1 ;
      S2: 8, 1, M, S2 ;
    }
    Frames {
      F1 : 0x10, M, 2 { S1, 0 ; S2, 8 ; }
            MasterReq : 0x3C, M, 2 { S1, 0 ; S2, 8 ; }
    }
    Schedule_tables {
      Main { F1 delay 10 ms ; }
    }
    Signal_encoding_types {
      EncS1 {
        logical_value, 0, "Idle" ;
        physical_value, 0, 100, 0.5, -40.0, "deg C" ;
      }
    }
    Signal_representation {
      EncS1: S1 ;
    }
    Node_attributes {
      S1 {
        LIN_protocol = "2.1" ;
        configured_NAD = 0x01 ;
        initial_NAD = 0x01 ;
      }
    }
    """


def test_qt_hierarchy_view_contains_inline_values(qapp: QApplication, sample_ldf_text: str) -> None:
    """Ensure the single Qt hierarchy tree embeds values/attributes as child rows."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    tree = viewer._tree
    root = tree.topLevelItem(0)

    assert root.text(0) == "LDF cluster"

    header = root.child(0)
    assert header.text(0) == "Header"
    header_rows = {header.child(i).text(0) for i in range(header.childCount())}
    assert "Protocol version: 2.1" in header_rows
    assert "Baudrate: 19.2 kbps" in header_rows

    top_level_rows = {root.child(i).text(0) for i in range(root.childCount())}
    assert not any(text.startswith("Signals (") for text in top_level_rows)
    assert not any(text.startswith("Encoding types (") for text in top_level_rows)
    assert not any(text.startswith("Signal representations (") for text in top_level_rows)
    assert not any(text.startswith("Node attributes (") for text in top_level_rows)


def test_qt_hierarchy_embeds_node_attributes_inside_each_node(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure node attributes are shown under each node instead of a separate top-level section."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    nodes = root.child(1)
    assert nodes.text(0) == "Nodes"

    master = nodes.child(0)
    assert master.text(0).startswith("Master (1):")

    slaves = nodes.child(1)
    assert slaves.text(0) == "Slaves (2)"
    s1 = slaves.child(0)
    assert s1.text(0) == "S1"

    rows = {s1.child(i).text(0) for i in range(s1.childCount())}
    assert "LIN protocol: 2.1" in rows
    assert "Configured NAD: 1" in rows
    assert "Initial NAD: 1" in rows
    assert "Configurable frames" in rows
    assert "Related frames" in rows


def test_qt_hierarchy_slave_contains_related_frames_and_signal_encoding(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure each slave lists related frames with signal characteristics and encoding."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    nodes = None
    for i in range(root.childCount()):
        if root.child(i).text(0) == "Nodes":
            nodes = root.child(i)
            break
    assert nodes is not None

    slaves = None
    for i in range(nodes.childCount()):
        if nodes.child(i).text(0).startswith("Slaves ("):
            slaves = nodes.child(i)
            break
    assert slaves is not None

    s1 = None
    for i in range(slaves.childCount()):
        if slaves.child(i).text(0) == "S1":
            s1 = slaves.child(i)
            break
    assert s1 is not None

    related_frames = None
    for i in range(s1.childCount()):
        if s1.child(i).text(0) == "Related frames":
            related_frames = s1.child(i)
            break
    assert related_frames is not None
    frame_names = {
        related_frames.child(i).text(0).split(":", 1)[0] for i in range(related_frames.childCount())
    }

    assert "F1" in frame_names

    f1_item = None
    for i in range(related_frames.childCount()):
        if related_frames.child(i).text(0).startswith("F1:"):
            f1_item = related_frames.child(i)
            break

    assert f1_item is not None

    for i in range(f1_item.childCount()):
        if f1_item.child(i).text(0) == "S1":
            s1_signal = f1_item.child(i)
            break
    assert s1_signal is not None

    detail_rows = {s1_signal.child(i).text(0) for i in range(s1_signal.childCount())}
    assert "Size: 8 bit" in detail_rows

    encoding_item = None
    for i in range(s1_signal.childCount()):
        if s1_signal.child(i).text(0) == "Encoding: EncS1":
            encoding_item = s1_signal.child(i)
            break
    assert encoding_item is not None

    encoding_rows = {encoding_item.child(i).text(0) for i in range(encoding_item.childCount())}
    assert "BCD: no" in encoding_rows
    assert "ASCII: no" in encoding_rows
    assert "Logical values count: 1" in encoding_rows
    assert "Physical ranges count: 1" in encoding_rows

    logical_values_node = None
    physical_ranges_node = None
    for i in range(encoding_item.childCount()):
        text = encoding_item.child(i).text(0)
        if text == "Logical values":
            logical_values_node = encoding_item.child(i)
        if text == "Physical ranges":
            physical_ranges_node = encoding_item.child(i)
    assert logical_values_node is not None
    assert physical_ranges_node is not None

    logical_rows = {
        logical_values_node.child(i).text(0) for i in range(logical_values_node.childCount())
    }
    assert "0: Idle" in logical_rows

    first_range = physical_ranges_node.child(0)
    range_rows = {first_range.child(i).text(0) for i in range(first_range.childCount())}
    assert "Scale: 0.5" in range_rows
    assert "Offset: -40.0" in range_rows
    assert "Unit: deg C" in range_rows


def test_qt_hierarchy_and_controls_have_accessible_names(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure key widgets expose accessible names/descriptions for assistive tech."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    assert viewer.accessibleName() == "LDF viewer"
    assert "navigating the loaded LIN Description File hierarchy" in viewer.accessibleDescription()
    assert viewer._search_bar.accessibleName() == "Hierarchy search bar"
    assert "searching text inside the hierarchy tree" in viewer._search_bar.accessibleDescription()
    assert viewer._tree.accessibleName() == "LDF hierarchy tree"
    assert "Tree view" in viewer._tree.accessibleDescription()
    assert viewer._breadcrumb.accessibleName() == "Current position in hierarchy"
    assert "Breadcrumb trail" in viewer._breadcrumb.accessibleDescription()

    window = main_window_qt.MainWindow()
    window.show()
    assert window.accessibleName() == "Easy-LIN main window"
    assert "Main application window" in window.accessibleDescription()
    assert window._placeholder.accessibleName() == "Welcome placeholder"
    assert window._sb_ldf.accessibleDescription().startswith("Summarizes the currently loaded LDF")
    assert window._comm_window.accessibleName() == "Communication window"
    comm = window._comm_window._comm_panel
    assert comm._refresh_btn.accessibleName() == "Refresh hardware channels"
    assert "Vector LIN hardware channel" in comm._channel_combo.accessibleDescription()
    assert comm._frame_combo.accessibleName() == "LIN frame selection"
    assert comm._data_edit.accessibleName() == "Frame payload bytes"
    assert "hexadecimal values" in comm._data_edit.accessibleDescription()
    assert comm._send_btn.accessibleName() == "Send frame"
    assert comm._sched_start_btn.accessibleName() == "Run schedule"
    assert comm._changed_only_chk.accessibleName() == "Show only changed received frames"
    assert "payload changed" in comm._changed_only_chk.accessibleDescription()
    assert comm._monitor._table.accessibleName() == "Received LIN frame monitor"
    assert "timestamp in milliseconds" in comm._monitor._table.accessibleDescription()


def test_qt_hierarchy_diagnostics_precede_schedule_tables(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure diagnostic frames section is rendered before schedule tables."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    diag_index = -1
    sched_index = -1
    for i in range(root.childCount()):
        text = root.child(i).text(0)
        if text.startswith("Diagnostic frames"):
            diag_index = i
        if text.startswith("Schedule tables"):
            sched_index = i

    assert diag_index != -1
    assert sched_index != -1
    assert diag_index < sched_index


def test_qt_hierarchy_focus_helpers_focus_tree(qapp: QApplication, sample_ldf_text: str) -> None:
    """Ensure hierarchy focus helpers place keyboard focus in the tree."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    viewer.focus_hierarchy_tree()
    qapp.processEvents()
    assert viewer._tree.hasFocus()

    viewer.focus_hierarchy_details()
    qapp.processEvents()
    assert viewer._tree.hasFocus()


def test_qt_copy_focused_hierarchy_line_to_clipboard(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure the focused hierarchy line can be copied with the viewer helper."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    protocol_row = header.child(0)
    viewer._tree.setCurrentItem(protocol_row)

    viewer.copy_current_item_to_clipboard()
    copied_text = qapp.clipboard().text()
    assert copied_text == "Protocol version: 2.1"


def test_qt_tree_expand_collapse_keeps_current_item_anchored(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure toggling a branch moves the current item to that branch instead of root."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    viewer._tree.setCurrentItem(root)
    assert viewer._tree.currentItem() is root

    viewer._tree.collapseItem(header)
    qapp.processEvents()
    assert viewer._tree.currentItem() is header

    viewer._tree.expandItem(header)
    qapp.processEvents()
    assert viewer._tree.currentItem() is header


def test_qt_tree_expand_collapse_announces_open_and_close(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure branch toggles announce "Opened" and "Closed" status messages."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    messages: list[str] = []
    monkeypatch.setattr(viewer, "_announce_status", lambda message: messages.append(message))

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)

    viewer._tree.collapseItem(header)
    qapp.processEvents()
    viewer._tree.expandItem(header)
    qapp.processEvents()

    assert any(msg.startswith("Closed: Header") for msg in messages)
    assert any(msg.startswith("Opened: Header") for msg in messages)


def test_qt_tree_toggle_announcements_reach_main_window_event_channel(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure tree toggle feedback uses MainWindow latest-event channel."""
    ldf = parse_ldf_string(sample_ldf_text)
    window = main_window_qt.MainWindow()
    viewer = LDFViewer(ldf)
    window.setCentralWidget(viewer)
    window.show()

    events: list[str] = []
    monkeypatch.setattr(
        window,
        "_announce_event",
        lambda message, timeout_ms=5000, assertive=False: events.append(message),
    )

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    viewer._tree.collapseItem(header)
    qapp.processEvents()

    assert any(msg.startswith("Closed: Header") for msg in events)


def test_qt_tree_toggle_triggers_beep(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure expand/collapse emits an audible cue for non-visual users."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    beeps: list[str] = []
    monkeypatch.setattr(ldf_viewer.QApplication, "beep", lambda: beeps.append("beep"))

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    viewer._tree.collapseItem(header)
    qapp.processEvents()

    assert beeps


def test_qt_tree_left_key_collapses_without_jumping_to_top(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Left collapses current branch while keeping current item anchored."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    viewer._tree.expandItem(nodes)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    assert viewer._tree.currentItem() is nodes
    assert nodes.isExpanded()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    # The branch should collapse but keyboard focus must remain on that branch.
    assert viewer._tree.currentItem() is nodes
    assert not nodes.isExpanded()


def test_qt_tree_right_key_expands_without_forcing_child_navigation(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Right expands a branch but keeps keyboard focus on that branch."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    viewer._tree.collapseItem(nodes)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    assert viewer._tree.currentItem() is nodes
    assert nodes.isExpanded()


def test_qt_tree_down_key_skips_collapsed_branch_children(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Down skips past collapsed branches and moves to the next sibling."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    diagnostics = root.child(2)
    schedules = root.child(3)

    # Collapse all intermediate sections so Down moves between siblings without
    # descending into any expanded subtree.
    viewer._tree.collapseItem(nodes)
    viewer._tree.collapseItem(diagnostics)
    viewer._tree.collapseItem(schedules)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)

    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()
    assert viewer._tree.currentItem() is diagnostics

    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()
    assert viewer._tree.currentItem() is schedules


def test_qt_tree_up_key_returns_to_previous_collapsed_sibling(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Up returns to the collapsed previous sibling (which is itself its last descendant)."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    diagnostics = root.child(2)
    schedules = root.child(3)

    # Collapse diagnostics so _last_visible_descendant returns diagnostics itself.
    viewer._tree.collapseItem(diagnostics)
    viewer._tree.setCurrentItem(schedules)
    qapp.processEvents()

    up = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, up)
    qapp.processEvents()

    assert viewer._tree.currentItem() is diagnostics


def test_qt_tree_down_key_enters_first_child_of_expanded_branch(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Down enters the first child of an expanded branch (depth-first descent)."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)  # "Header" — expanded after _populate
    first_header_child = header.child(0)  # "Protocol version: 2.1"

    assert header.isExpanded()
    viewer._tree.setCurrentItem(header)
    qapp.processEvents()

    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()

    assert viewer._tree.currentItem() is first_header_child


def test_qt_tree_up_key_descends_into_last_visible_descendant_of_expanded_sibling(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Up lands on the last visible descendant of the preceding expanded sibling."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)  # expanded, its children are all leaf nodes
    nodes = root.child(1)
    last_header_child = header.child(header.childCount() - 1)  # "Channel name: CABIN"

    assert header.isExpanded()
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    up = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, up)
    qapp.processEvents()

    # Up from "Nodes" should land on the last visible descendant of "Header"
    assert viewer._tree.currentItem() is last_header_child


def test_qt_tree_up_key_goes_to_parent_when_no_previous_sibling(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Up moves to the parent branch when the item has no previous sibling."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    first_header_child = header.child(0)  # no previous sibling

    viewer._tree.setCurrentItem(first_header_child)
    qapp.processEvents()

    up = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, up)
    qapp.processEvents()

    assert viewer._tree.currentItem() is header


def test_qt_tree_right_key_enters_first_child_when_branch_is_expanded(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Right on an expanded branch moves into its first child for explicit descent."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    diagnostics = root.child(2)
    first_diagnostic = diagnostics.child(0)

    assert diagnostics.isExpanded()
    viewer._tree.setCurrentItem(diagnostics)
    qapp.processEvents()

    right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, right)
    qapp.processEvents()

    assert viewer._tree.currentItem() is first_diagnostic


def test_qt_tree_left_key_on_child_returns_to_parent_branch(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Left on a child row moves back to its parent branch."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    diagnostics = root.child(2)
    first_diagnostic = diagnostics.child(0)
    first_leaf = first_diagnostic.child(0)

    viewer._tree.setCurrentItem(first_leaf)
    qapp.processEvents()

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, left)
    qapp.processEvents()

    assert viewer._tree.currentItem() is first_diagnostic


@pytest.mark.parametrize(
    "ldf_path",
    sorted(Path("LDF").glob("*.ldf")),
    ids=lambda path: path.name,
)
def test_real_ldf_top_level_navigation_is_deterministic(
    qapp: QApplication,
    ldf_path: Path,
) -> None:
    """Ensure bundled LDF files keep top-level traversal stable for screen readers."""
    ldf = parse_ldf(str(ldf_path))
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    assert root.childCount() >= 4

    nodes = root.child(1)
    diagnostics = root.child(2)
    schedules = root.child(3)

    # Collapse all intermediate sections so Down skips their content and moves
    # between top-level siblings deterministically on every LDF file.
    viewer._tree.collapseItem(nodes)
    viewer._tree.collapseItem(diagnostics)
    viewer._tree.collapseItem(schedules)
    viewer._tree.setCurrentItem(nodes)  # set AFTER collapseItem calls to avoid focus drift
    qapp.processEvents()

    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)

    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()
    assert viewer._tree.currentItem() is diagnostics

    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()
    assert viewer._tree.currentItem() is schedules


def test_real_cpc_collapse_nodes_then_down_reaches_diagnostics_directly(
    qapp: QApplication,
) -> None:
    """Ensure one Down key reaches diagnostics right after collapsing Nodes on CPC LDF."""
    ldf_candidates = sorted(Path("LDF").glob("*.ldf"))
    if not ldf_candidates:
        pytest.skip("No local LDF files available for real-file navigation test")
    ldf_path = ldf_candidates[0]
    ldf = parse_ldf(str(ldf_path))
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    diagnostics = root.child(2)
    assert nodes.text(0) == "Nodes"
    assert diagnostics.text(0).startswith("Diagnostic frames")

    # Reproduce mixed navigation: focus a deep node entry, then collapse Nodes.
    slaves_root = nodes.child(1)
    first_slave = slaves_root.child(0)
    viewer._tree.setCurrentItem(first_slave)
    qapp.processEvents()

    viewer._tree.collapseItem(nodes)
    qapp.processEvents()

    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()

    assert viewer._tree.currentItem() is diagnostics


def test_qt_tree_left_key_on_true_top_level_item_does_not_lose_position(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Left on the true top-level root (no Qt parent) must be consumed and stay on that item.

    topLevelItem(0) has parent() == None.  Before this fix the Left key fell
    through to Qt's native handler which could silently move focus elsewhere.
    """
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    assert root.parent() is None, "root must have no parent for this scenario"

    # Collapse root so Left's 'already collapsed' branch fires (no parent branch).
    viewer._tree.collapseItem(root)
    viewer._tree.setCurrentItem(root)
    qapp.processEvents()

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, left)
    qapp.processEvents()

    # Must stay on root — nothing to navigate to.
    assert viewer._tree.currentItem() is root


def test_qt_tree_left_key_reanchor_fires_after_collapse(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """After Left collapse the deferred re-anchor leaves current item on the collapsed node."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    viewer._tree.expandItem(nodes)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, left)
    qapp.processEvents()  # processEvents fires the QTimer.singleShot(0, ...) callback

    assert not nodes.isExpanded()
    assert viewer._tree.currentItem() is nodes


def test_qt_tree_after_left_collapse_down_reaches_next_sibling(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """After Left-collapsing a section, Down must navigate to the next sibling section.

    This is the primary use-case regression: blind users pressing Left to close
    a section must be able to immediately press Down to reach the next section.
    """
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    diagnostics = root.child(2)

    # Start deep inside Nodes, then Left-collapse.
    viewer._tree.setCurrentItem(nodes)
    viewer._tree.expandItem(nodes)
    qapp.processEvents()

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, left)
    qapp.processEvents()  # fires the deferred re-anchor

    assert not nodes.isExpanded()

    down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, down)
    qapp.processEvents()

    assert viewer._tree.currentItem() is diagnostics


def test_qt_tree_left_right_left_sequence_cancels_deferred_reanchor(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure rapid Left-Right-Left key sequences don't lose focus due to deferred re-anchor races.

    Regression test for: when Left schedules a deferred re-anchor callback,
    and Right is pressed before the callback fires, the Right handler should
    successfully navigate without interference from the pending deferred callback.
    """
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)

    # Expand Nodes first so it can be collapsed by Left.
    viewer._tree.expandItem(nodes)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)

    # Press Left to collapse Nodes and schedule deferred re-anchor.
    QApplication.sendEvent(viewer._tree, left)
    # Do NOT process events yet — deferred callback is scheduled but not fired.

    # Press Right before deferred re-anchor fires.
    # This should be handled correctly (Right should expand Nodes again).
    QApplication.sendEvent(viewer._tree, right)

    # Now process events — deferred re-anchor callback should be cancelled by Right's key press.
    qapp.processEvents()

    # Current item should still be on Nodes, and it should be expanded by Right.
    assert viewer._tree.currentItem() is nodes
    assert nodes.isExpanded()

    # Press Left again to collapse — should work correctly.
    QApplication.sendEvent(viewer._tree, left)
    qapp.processEvents()

    assert not nodes.isExpanded()
    assert viewer._tree.currentItem() is nodes


def test_qt_tree_right_key_on_leaf_node_does_not_lose_focus(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Right arrow on a leaf (no children) must be consumed without losing focus."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    leaf = header.child(0)  # first header property — leaf node

    viewer._tree.setCurrentItem(leaf)
    qapp.processEvents()

    right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    consumed = QApplication.sendEvent(viewer._tree, right)
    qapp.processEvents()

    assert consumed
    assert viewer._tree.currentItem() is leaf  # stays on the leaf


def test_qt_tree_normalizes_hidden_current_item_before_key_navigation(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure key handling re-anchors a hidden current item to a visible anchor first."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    hidden = root.child(0).child(0)
    viewer._tree.setCurrentItem(hidden)
    qapp.processEvents()

    # Force the event-filter normalization branch (anchor != current).
    viewer._visible_navigation_anchor = lambda _item: root  # type: ignore[assignment]
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    assert viewer._tree.currentItem() is root


def test_qt_tree_visible_navigation_anchor_walks_up_collapsed_ancestors(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure hidden descendants resolve to the nearest visible collapsed ancestor."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    leaf = header.child(0)
    viewer._tree.collapseItem(header)

    anchor = viewer._visible_navigation_anchor(leaf)
    assert anchor is header


def test_qt_tree_left_collapse_replaces_existing_deferred_reanchor_timer(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Left-collapse cancels an existing deferred timer before scheduling a new one."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    viewer._tree.expandItem(nodes)
    viewer._tree.setCurrentItem(nodes)
    qapp.processEvents()

    previous_timer = viewer.startTimer(1000)
    viewer._deferred_reanchor_timer_id = previous_timer

    left = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, left)

    assert viewer._deferred_reanchor_timer_id is not None
    assert viewer._deferred_reanchor_timer_id != previous_timer

    # Cleanup the newly scheduled deferred timer to avoid side effects.
    viewer.killTimer(viewer._deferred_reanchor_timer_id)
    viewer._deferred_reanchor_timer_id = None


def test_qt_tree_timer_event_passes_unknown_timer_to_super(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure timerEvent delegates unknown timer IDs to QObject timer handling."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    # Must not raise; executes the non-deferred timerEvent branch.
    viewer.timerEvent(QTimerEvent(424242))


def test_qt_tree_space_toggles_slave_check_state(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure Space toggles the current slave checkbox for keyboard-only usage."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    slaves_root = nodes.child(1)
    slave_item = slaves_root.child(0)

    viewer._tree.setCurrentItem(slave_item)
    qapp.processEvents()
    assert slave_item.checkState(0) == Qt.CheckState.Checked

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()
    assert slave_item.checkState(0) == Qt.CheckState.Unchecked

    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()
    assert slave_item.checkState(0) == Qt.CheckState.Checked


def test_qt_tree_can_uncheck_all_slaves_and_reports_empty_selection(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure users can uncheck all slaves and still receive clear selection state."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    emitted: list[tuple[str, list[str]]] = []
    viewer.node_selection_changed.connect(lambda m, s: emitted.append((m, list(s))))

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    slaves_root = nodes.child(1)
    first_slave = slaves_root.child(0)
    second_slave = slaves_root.child(1)

    viewer._tree.setCurrentItem(first_slave)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    viewer._tree.setCurrentItem(second_slave)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    master, slaves = viewer.selected_nodes()
    assert master == "M"
    assert slaves == []
    assert emitted
    assert emitted[-1] == ("M", [])


def test_qt_tree_space_is_ignored_for_non_checkable_row(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure non-checkable rows are ignored by the keyboard toggle helper."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    non_checkable = viewer._tree.topLevelItem(0)
    non_checkable.setFlags(non_checkable.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

    assert viewer._toggle_current_checkable_node(non_checkable) is False


def test_qt_tree_non_master_slave_item_check_state_is_reverted(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure any accidental check state on a non-master/slave item is silently reverted."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    # A regular property leaf (e.g. "Protocol version: 2.1") should never stay checked.
    root = viewer._tree.topLevelItem(0)
    header = root.child(0)
    proto_row = header.child(0)  # "Protocol version: 2.1"

    # Force a check state on a non-master/slave item (simulates an accidental click).
    proto_row.setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()

    # _on_node_item_changed should have reverted it immediately.
    assert proto_row.checkState(0) == Qt.CheckState.Unchecked


def test_navigate_from_master_to_slaves(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Verify that pressing Down from Master navigates to Slaves, not diagnostic frames."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)  # "Nodes" is 2nd top-level item (after Header)
    assert nodes.text(0) == "Nodes"

    master = nodes.child(0)
    assert "Master" in master.text(0)

    slaves = nodes.child(1)
    assert slaves.text(0).startswith("Slaves (")

    # Collapse Master and verify it's still on Master
    viewer._tree.setCurrentItem(master)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    # Verify Master is still selected after collapse
    assert viewer._tree.currentItem() == master
    assert not master.isExpanded()

    # Now navigate Down from collapsed Master
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    # Should navigate to Slaves (next sibling), not jump to Diagnostic frames
    assert viewer._tree.currentItem() == slaves
    assert slaves.isExpanded()


def test_qt_tree_space_announces_when_selection_is_locked(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure keyboard toggles announce lock state when communication lock is active."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)
    viewer.show()

    root = viewer._tree.topLevelItem(0)
    nodes = root.child(1)
    slaves_root = nodes.child(1)
    slave_item = slaves_root.child(0)

    messages: list[str] = []
    monkeypatch.setattr(viewer, "_announce_status", lambda message: messages.append(message))

    viewer.lock_node_selection(True)
    viewer._tree.setCurrentItem(slave_item)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewer._tree, event)
    qapp.processEvents()

    assert slave_item.checkState(0) == Qt.CheckState.Checked
    assert messages
    assert "Node selection is locked" in messages[-1]


def test_qt_tree_programmatic_expand_is_quiet_when_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Automatic expand mode must not trigger user-facing select/announce side effects."""
    ldf = parse_ldf_string(sample_ldf_text)
    viewer = LDFViewer(ldf)

    root = viewer._tree.topLevelItem(0)
    header = root.child(0)

    calls: list[str] = []
    monkeypatch.setattr(viewer, "_select_and_reveal_item", lambda _item: calls.append("select"))
    monkeypatch.setattr(viewer, "_announce_tree_toggle", lambda _a, _i: calls.append("announce"))

    viewer._suppress_toggle_announcements = True
    viewer._on_item_expanded(header)
    viewer._on_item_collapsed(header)

    assert calls == []


def test_main_window_focuses_tree_after_ldf_load(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure loading an LDF focuses the hierarchy tree immediately."""
    ldf = parse_ldf_string(sample_ldf_text)

    monkeypatch.setattr(main_window_qt, "parse_ldf", lambda _path: ldf)
    # Bypass the validation-gate dialog so the file loads regardless of warnings.
    monkeypatch.setattr(main_window_qt.MainWindow, "_show_ldf_issues_dialog", lambda *_: True)

    window = main_window_qt.MainWindow()
    window.show()
    window._load_ldf("dummy.ldf")
    qapp.processEvents()

    viewer = window.centralWidget()
    assert isinstance(viewer, LDFViewer)
    assert viewer._tree.hasFocus()
    assert window._sb_ldf.text().startswith("LDF: LIN 2.1 | 19.2 kbps | Frames: 2")
    assert window._sb_issues.text().startswith("LDF issues: Warnings:")


def test_main_window_status_bar_tracks_communication_and_events(
    qapp: QApplication,
) -> None:
    """Ensure persistent status fields reflect communication and event updates."""
    window = main_window_qt.MainWindow()
    window.show()

    window._comm_window.communication_state_changed.emit("Connected")
    window._comm_window.status_message.emit("Connected to LIN hardware.")
    qapp.processEvents()

    assert window._sb_comm.text() == "Comm: Connected"
    assert "Connected to LIN hardware." in window._sb_event.text()
    assert "#1F7A1F" in window._sb_comm.styleSheet()


def test_main_window_status_bar_colors_reflect_ldf_issue_levels(
    qapp: QApplication,
) -> None:
    """Ensure issue counts drive warning/error color coding in status fields."""
    window = main_window_qt.MainWindow()
    window.show()

    window._set_ldf_issues_status(warning_count=0, error_count=0)
    assert "#1F7A1F" in window._sb_issues.styleSheet()

    window._set_ldf_issues_status(warning_count=2, error_count=0)
    assert "#9A6700" in window._sb_issues.styleSheet()

    window._set_ldf_issues_status(warning_count=0, error_count=1)
    assert "#B00020" in window._sb_issues.styleSheet()


def test_main_window_status_bar_colors_reflect_comm_states(
    qapp: QApplication,
) -> None:
    """Ensure communication state updates apply the expected status color mapping."""
    window = main_window_qt.MainWindow()
    window.show()

    window._set_comm_status("Disconnected")
    assert "#4A4A4A" in window._sb_comm.styleSheet()

    window._set_comm_status("No hardware")
    assert "#9A6700" in window._sb_comm.styleSheet()

    window._set_comm_status("Error")
    assert "#B00020" in window._sb_comm.styleSheet()


def test_main_window_region_cycle_and_shortcut_contexts(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure region cycling works and shortcuts are application-wide."""
    ldf = parse_ldf_string(sample_ldf_text)

    window = main_window_qt.MainWindow()
    window.show()

    viewer = LDFViewer(ldf)
    window.setCentralWidget(viewer)

    window._focus_ldf_tree()
    qapp.processEvents()
    assert window._region_cycle_index == 0

    window._focus_next_region()
    qapp.processEvents()
    assert window._region_cycle_index == 1

    window._focus_previous_region()
    qapp.processEvents()
    assert window._region_cycle_index == 0

    assert window._shortcut_focus_tree.context() == Qt.ShortcutContext.ApplicationShortcut
    assert window._shortcut_focus_details.context() == Qt.ShortcutContext.ApplicationShortcut
    assert window._shortcut_next_region.context() == Qt.ShortcutContext.ApplicationShortcut
    assert window._shortcut_prev_region.context() == Qt.ShortcutContext.ApplicationShortcut


def test_about_html_contains_metadata_and_clickable_links() -> None:
    """Ensure About content includes required company metadata and clickable links."""
    html = main_window_qt.MainWindow._build_about_html()

    assert "Author:</b> Amine Khettat" in html
    assert "Company:</b> BLIND SYSTEMS" in html
    assert "Copyright (c) 2026 Amine Khettat" in html
    assert "href='mailto:contact@blindsystems.org'" in html
    assert "href='https://www.blindsystems.org'" in html


def test_about_logo_url_is_defined() -> None:
    """Ensure About dialog has a bundled local logo path for offline use."""
    assert main_window_qt.APP_COMPANY_LOGO_PATH.endswith("blind_systems_logo.png")
    assert os.path.exists(main_window_qt.APP_COMPANY_LOGO_PATH)
