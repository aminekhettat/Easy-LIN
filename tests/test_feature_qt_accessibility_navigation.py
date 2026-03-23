"""
Atomic features covered:
- Build a single hierarchical Qt LDF tree with inline attributes and values
- Link each slave node to related frames
- Show frame signal characteristics and encoding attributes directly inside frame nodes
- Place diagnostic frames before schedule tables
- Avoid a duplicated top-level signals section outside nodes
- Keep tree selection anchored on expanded/collapsed items
- Announce opened/closed hierarchy rows for non-visual feedback
- Focus hierarchy tree directly after LDF load
- Provide deterministic region focus and region-cycling behavior
- Keep global accessibility shortcuts configured for application-wide handling
- Track persistent status bar fields for LDF issues and communication state
- Color-code status bar fields for quick issue/health recognition
- Provide About window metadata with clickable contact links and company logo
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from src.ldf_parser import parse_ldf_string
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

    encodings = None
    for i in range(root.childCount()):
        if root.child(i).text(0).startswith("Encoding types"):
            encodings = root.child(i)
            break
    assert encodings is not None
    assert encodings.childCount() >= 1

    top_level_rows = {root.child(i).text(0) for i in range(root.childCount())}
    assert not any(text.startswith("Signals (") for text in top_level_rows)


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
        if nodes.child(i).text(0) == "Slaves":
            slaves = nodes.child(i)
            break
    assert slaves is not None

    s1 = None
    for i in range(slaves.childCount()):
        if slaves.child(i).text(0) == "S1":
            s1 = slaves.child(i)
            break
    assert s1 is not None

    related_frames = s1.child(0)
    assert related_frames.text(0) == "Related frames"
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
    assert viewer._tree.accessibleName() == "LDF hierarchy tree"
    assert "Tree view" in viewer._tree.accessibleDescription()

    window = main_window_qt.MainWindow()
    window.show()
    comm = window._comm_window._comm_panel
    assert comm._refresh_btn.accessibleName() == "Refresh hardware channels"
    assert comm._send_btn.accessibleName() == "Send frame"
    assert comm._sched_start_btn.accessibleName() == "Run schedule"


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
        window, "_announce_event", lambda message, timeout_ms=5000: events.append(message)
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
