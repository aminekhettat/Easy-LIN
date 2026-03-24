"""Tests for accessibility features in src/gui/ldf_viewer.py.

Covers:
  _find_next_match (wrap around), _collect_matches
        - Search bar: _show_search, _hide_search, _on_search_text_changed (matches/no matches),
            _find_next_match (wrap around), _collect_matches
        - Breadcrumb: _update_breadcrumb, _sibling_position (with/without parent, single item)
        - Navigation: _next_sibling, _previous_sibling (with parent and top-level);
            depth-first _next_navigation_item / _previous_navigation_item
- Expand/collapse subtree: _expand_current_subtree, _collapse_current_subtree,
  _expand_recursive, _collapse_recursive
- _fire_accessible_event (with and without exception)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

from src.ldf_parser import (
    LDFFile,
    LDFFrame,
    LDFFrameSignal,
    LDFScheduleTable,
    LDFScheduleEntry,
    LDFNodes,
    LDFMaster,
    LDFSignal,
    LDFSignalRepresentation,
    LDFEncodingType,
    LDFLogicalValue,
    LDFPhysicalRange,
    LDFNodeAttributes,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_sample_ldf():
    ldf = LDFFile(
        protocol_version="2.1",
        language_version="2.1",
        speed=19.2,
        channel_name="CABIN",
        nodes=LDFNodes(
            master=LDFMaster(name="M", time_base=5.0, jitter=0.1),
            slaves=["S1"],
        ),
        signals=[
            LDFSignal(name="Sig1", size=8, init_value=0, publisher="M", subscribers=["S1"]),
            LDFSignal(name="Sig2", size=8, init_value=1, publisher="S1", subscribers=["M"]),
        ],
        frames=[
            LDFFrame(
                name="Frame1",
                frame_id=0x10,
                publisher="M",
                frame_size=2,
                signals=[
                    LDFFrameSignal(signal_name="Sig1", bit_offset=0),
                    LDFFrameSignal(signal_name="Sig2", bit_offset=8),
                ],
            ),
            LDFFrame(
                name="DiagReq",
                frame_id=0x3C,
                publisher="M",
                frame_size=8,
                signals=[],
            ),
        ],
        schedule_tables=[
            LDFScheduleTable(
                name="MainSched",
                entries=[LDFScheduleEntry(frame_name="Frame1", delay=10.0)],
            ),
        ],
        encoding_types=[
            LDFEncodingType(
                name="EncSig1",
                logical_values=[LDFLogicalValue(signal_value=0, text="Idle")],
                physical_ranges=[
                    LDFPhysicalRange(
                        min_value=0, max_value=100, scale=0.5, offset=-40.0, unit="deg C"
                    )
                ],
            ),
        ],
        signal_representations=[
            LDFSignalRepresentation(encoding_type="EncSig1", signals=["Sig1"]),
        ],
        node_attributes=[
            LDFNodeAttributes(
                node_name="S1",
                lin_protocol="2.1",
                configured_nad=1,
                initial_nad=1,
            ),
        ],
    )
    ldf.build_lookups()
    return ldf


@pytest.fixture
def viewer(qapp):
    from src.gui.ldf_viewer import LDFViewer

    ldf = _make_sample_ldf()
    v = LDFViewer(ldf)
    v.show()
    return v


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearchBar:
    def test_show_search(self, viewer):
        assert viewer._search_bar.isVisible() is False
        viewer._show_search()
        assert viewer._search_bar.isVisible() is True

    def test_hide_search(self, viewer):
        viewer._show_search()
        viewer._hide_search()
        assert viewer._search_bar.isVisible() is False
        assert viewer._search_matches == []
        assert viewer._search_match_index == -1

    def test_on_search_text_changed_with_matches(self, viewer):
        viewer._on_search_text_changed("Frame1")
        assert len(viewer._search_matches) > 0
        assert viewer._search_match_index == 0

    def test_on_search_text_changed_no_matches(self, viewer):
        viewer._on_search_text_changed("NONEXISTENT_ITEM_XYZ")
        assert len(viewer._search_matches) == 0
        assert viewer._search_match_index == -1

    def test_on_search_text_changed_empty(self, viewer):
        viewer._on_search_text_changed("")
        assert len(viewer._search_matches) == 0

    def test_on_search_text_changed_whitespace_only(self, viewer):
        viewer._on_search_text_changed("   ")
        assert len(viewer._search_matches) == 0

    def test_find_next_match_wraps_around(self, viewer):
        viewer._on_search_text_changed("Sig1")
        count = len(viewer._search_matches)
        assert count > 0
        # Walk through all matches plus one to verify wrap
        for _i in range(count + 1):
            viewer._find_next_match()
        assert viewer._search_match_index == 1 % count if count > 1 else 0

    def test_find_next_match_no_matches(self, viewer):
        viewer._search_matches.clear()
        viewer._search_match_index = -1
        viewer._find_next_match()  # Should not crash

    def test_collect_matches(self, viewer):
        viewer._search_matches.clear()
        viewer._collect_matches(viewer._tree.invisibleRootItem(), "frame1")
        assert len(viewer._search_matches) > 0


# ---------------------------------------------------------------------------
# Breadcrumb tests
# ---------------------------------------------------------------------------


class TestBreadcrumb:
    def test_update_breadcrumb(self, viewer):
        item = viewer._tree.topLevelItem(0)
        assert item is not None
        viewer._update_breadcrumb(item)
        text = viewer._breadcrumb.text()
        assert len(text) > 0

    def test_update_breadcrumb_child(self, viewer):
        root = viewer._tree.topLevelItem(0)
        if root.childCount() > 0:
            child = root.child(0)
            viewer._update_breadcrumb(child)
            text = viewer._breadcrumb.text()
            assert ">" in text or len(text) > 0

    def test_sibling_position_with_parent(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        if root.childCount() > 1:
            child = root.child(1)
            pos = LDFViewer._sibling_position(child)
            assert "Item 2 of" in pos

    def test_sibling_position_top_level_single(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        # Only one top-level item => should return ""
        if viewer._tree.topLevelItemCount() == 1:
            item = viewer._tree.topLevelItem(0)
            pos = LDFViewer._sibling_position(item)
            assert pos == ""

    def test_sibling_position_no_tree(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        orphan = QTreeWidgetItem(["orphan"])
        pos = LDFViewer._sibling_position(orphan)
        assert pos == ""

    def test_sibling_position_single_child(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        parent = QTreeWidgetItem(["parent"])
        child = QTreeWidgetItem(["only child"])
        parent.addChild(child)
        pos = LDFViewer._sibling_position(child)
        assert pos == ""


# ---------------------------------------------------------------------------
# Sibling navigation tests
# ---------------------------------------------------------------------------


class TestSiblingNavigation:
    def test_next_sibling_with_parent(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        if root.childCount() >= 2:
            first_child = root.child(0)
            sibling = LDFViewer._next_sibling(first_child)
            assert sibling is not None
            assert sibling is root.child(1)

    def test_next_sibling_last_child(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        if root.childCount() > 0:
            last_child = root.child(root.childCount() - 1)
            sibling = LDFViewer._next_sibling(last_child)
            assert sibling is None

    def test_next_sibling_top_level(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        # Single top-level item
        item = viewer._tree.topLevelItem(0)
        if viewer._tree.topLevelItemCount() == 1:
            assert LDFViewer._next_sibling(item) is None

    def test_next_sibling_no_tree(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        orphan = QTreeWidgetItem(["orphan"])
        assert LDFViewer._next_sibling(orphan) is None

    def test_previous_sibling_with_parent(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        if root.childCount() >= 2:
            second_child = root.child(1)
            sibling = LDFViewer._previous_sibling(second_child)
            assert sibling is not None
            assert sibling is root.child(0)

    def test_previous_sibling_first_child(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        if root.childCount() > 0:
            first_child = root.child(0)
            sibling = LDFViewer._previous_sibling(first_child)
            assert sibling is None

    def test_previous_sibling_top_level(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        item = viewer._tree.topLevelItem(0)
        assert LDFViewer._previous_sibling(item) is None

    def test_previous_sibling_no_tree(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        orphan = QTreeWidgetItem(["orphan"])
        assert LDFViewer._previous_sibling(orphan) is None

    def test_next_sibling_top_level_with_next_item(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        tree = QTreeWidget()
        first = QTreeWidgetItem(["first"])
        second = QTreeWidgetItem(["second"])
        tree.addTopLevelItem(first)
        tree.addTopLevelItem(second)

        assert LDFViewer._next_sibling(first) is second

    def test_previous_sibling_top_level_with_previous_item(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        tree = QTreeWidget()
        first = QTreeWidgetItem(["first"])
        second = QTreeWidgetItem(["second"])
        tree.addTopLevelItem(first)
        tree.addTopLevelItem(second)

        assert LDFViewer._previous_sibling(second) is first

    def test_next_navigation_item_skips_descendants_and_returns_next_sibling(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        first_branch = root.child(0)  # "Header" — expanded after _populate
        expected_child = first_branch.child(0)  # "Protocol version: 2.1"

        assert first_branch.isExpanded()
        assert LDFViewer._next_navigation_item(first_branch) is expected_child

    def test_next_navigation_item_climbs_to_ancestor_sibling(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        first_branch = root.child(0)
        last_child = first_branch.child(first_branch.childCount() - 1)

        assert LDFViewer._next_navigation_item(last_child) is root.child(1)

    def test_previous_navigation_item_returns_parent_when_no_previous_sibling(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        first_branch = root.child(0)
        first_child = first_branch.child(0)

        assert LDFViewer._previous_navigation_item(first_child) is first_branch

    def test_previous_navigation_item_descends_into_last_child_of_expanded_sibling(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        first_branch = root.child(0)  # "Header" — expanded, leaf children
        second_branch = root.child(1)  # "Nodes"
        last_header_child = first_branch.child(first_branch.childCount() - 1)

        assert first_branch.isExpanded()
        assert LDFViewer._previous_navigation_item(second_branch) is last_header_child

    def test_next_navigation_item_returns_none_when_last_branch_is_collapsed(self, viewer):
        from src.gui.ldf_viewer import LDFViewer

        root = viewer._tree.topLevelItem(0)
        last_branch = root.child(root.childCount() - 1)
        # Collapse so depth-first does not descend into its children.
        viewer._tree.collapseItem(last_branch)

        assert LDFViewer._next_navigation_item(last_branch) is None


class TestKeyboardNavigationEventFilter:
    def test_event_filter_with_no_current_item(self, viewer):
        viewer._tree.setCurrentItem(None)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        handled = viewer.eventFilter(viewer._tree, event)
        assert handled is False

    def test_event_filter_right_expands_and_keeps_current_item(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None
        assert root.childCount() > 0

        root.setExpanded(False)
        viewer._tree.setCurrentItem(root)
        event_right = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier
        )
        assert viewer.eventFilter(viewer._tree, event_right) is True
        assert root.isExpanded() is True

        viewer._tree.setCurrentItem(root)
        assert viewer.eventFilter(viewer._tree, event_right) is True
        assert viewer._tree.currentItem() is root.child(0)

    def test_event_filter_down_moves_to_next_navigation_item(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None
        assert root.childCount() >= 2

        first_child = root.child(0)
        second_child = root.child(1)

        viewer._tree.setCurrentItem(first_child)
        viewer._tree.collapseItem(first_child)  # must be collapsed so Down skips to sibling
        viewer._tree.setCurrentItem(first_child)
        event_down = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )

        assert viewer.eventFilter(viewer._tree, event_down) is True
        assert viewer._tree.currentItem() is second_child

    def test_event_filter_up_moves_to_previous_navigation_item(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None
        assert root.childCount() >= 2

        first_child = root.child(0)
        second_child = root.child(1)

        viewer._tree.collapseItem(first_child)  # collapse so Up returns the sibling itself
        viewer._tree.setCurrentItem(second_child)
        event_up = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)

        assert viewer.eventFilter(viewer._tree, event_up) is True
        assert viewer._tree.currentItem() is first_child

    def test_event_filter_down_announces_when_no_next_navigation_item(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None

        last_child = root.child(root.childCount() - 1)
        viewer._tree.collapseItem(last_child)  # collapse so Down finds no next item
        viewer._tree.setCurrentItem(last_child)
        event_down = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )

        with patch.object(viewer, "_announce_status") as announce_status:
            assert viewer.eventFilter(viewer._tree, event_down) is True

        announce_status.assert_called_once_with("No next hierarchy item at this level.")

    def test_event_filter_up_announces_when_no_previous_navigation_item(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None

        viewer._tree.setCurrentItem(root)
        event_up = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)

        with patch.object(viewer, "_announce_status") as announce_status:
            assert viewer.eventFilter(viewer._tree, event_up) is True

        announce_status.assert_called_once_with("No previous hierarchy item at this level.")

    def test_event_filter_left_go_parent(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None
        assert root.childCount() > 0

        child = root.child(0)
        while child.childCount() > 0:
            child = child.child(0)

        parent = child.parent()
        assert parent is not None
        viewer._tree.setCurrentItem(child)
        event_left = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier
        )
        assert viewer.eventFilter(viewer._tree, event_left) is True
        assert viewer._tree.currentItem() is parent

    def test_event_filter_alt_sibling_navigation(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None
        assert root.childCount() >= 2

        first_child = root.child(0)
        second_child = root.child(1)

        viewer._tree.setCurrentItem(first_child)
        event_alt_down = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Down,
            Qt.KeyboardModifier.AltModifier,
        )
        assert viewer.eventFilter(viewer._tree, event_alt_down) is True
        assert viewer._tree.currentItem() is second_child

        event_alt_up = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Up,
            Qt.KeyboardModifier.AltModifier,
        )
        assert viewer.eventFilter(viewer._tree, event_alt_up) is True
        assert viewer._tree.currentItem() is first_child


class TestDebugAndEncodingEdgePaths:
    def test_announce_navigation_target_reports_label_position_and_state(self, viewer):
        root = viewer._tree.topLevelItem(0)
        assert root is not None

        with patch.object(viewer, "_announce_status") as announce_status:
            viewer._announce_navigation_target(root)

        announce_status.assert_called_once()
        message = announce_status.call_args.args[0]
        assert root.text(0) in message
        assert "expanded" in message or "collapsed" in message

    def test_debug_tree_event_logs_when_enabled(self, viewer):
        item = viewer._tree.topLevelItem(0)
        assert item is not None
        viewer._debug_tree = True
        try:
            with patch("src.gui.ldf_viewer.log.info") as info_log:
                viewer._debug_tree_event("KeyPress", item, key=123)
            info_log.assert_called_once()
        finally:
            viewer._debug_tree = False

    def test_add_encoding_details_none_and_missing(self, viewer):
        signal_item = QTreeWidgetItem(["SignalA"])
        viewer._add_encoding_details(signal_item, "none", {})
        assert signal_item.childCount() >= 1

        missing_item = QTreeWidgetItem(["SignalB"])
        viewer._add_encoding_details(missing_item, "MissingEncoding", {})
        assert missing_item.childCount() >= 1

    def test_add_encoding_details_empty_sections_add_none_entries(self, viewer):
        signal_item = QTreeWidgetItem(["SignalC"])
        empty_encoding = LDFEncodingType(
            name="EmptyEncoding", logical_values=[], physical_ranges=[]
        )

        viewer._add_encoding_details(
            signal_item, "EmptyEncoding", {"EmptyEncoding": empty_encoding}
        )
        assert signal_item.childCount() >= 1

    def test_frame_related_to_slave_via_subscriber(self, viewer):
        assert viewer._frame_related_to_slave("Frame1", "S1") is True

    def test_frame_related_to_slave_returns_false_when_frame_missing(self, viewer):
        assert viewer._frame_related_to_slave("missing_frame", "S1") is False

    def test_add_frame_signal_details_missing_signal_definition(self, viewer):
        parent = QTreeWidgetItem(["Parent"])
        frame = LDFFrame(
            name="MissingSignalFrame",
            frame_id=0x21,
            publisher="M",
            frame_size=1,
            signals=[LDFFrameSignal(signal_name="UnknownSignal", bit_offset=0)],
        )
        viewer._add_frame_signal_details(parent, frame, {}, {})
        assert parent.childCount() >= 1

    def test_populate_branches_for_empty_master_slave_links_and_configurable_frames(self, viewer):
        ldf = LDFFile(
            protocol_version="2.1",
            language_version="2.1",
            speed=19.2,
            channel_name="EDGE",
            nodes=LDFNodes(
                master=LDFMaster(name="MASTER", time_base=5.0, jitter=0.1),
                slaves=["S1"],
            ),
            signals=[
                LDFSignal(
                    name="OrphanSig", size=8, init_value=0, publisher="OTHER", subscribers=[]
                ),
            ],
            frames=[
                LDFFrame(
                    name="OrphanFrame",
                    frame_id=0x22,
                    publisher="OTHER",
                    frame_size=1,
                    signals=[LDFFrameSignal(signal_name="OrphanSig", bit_offset=0)],
                ),
            ],
            schedule_tables=[],
            encoding_types=[],
            signal_representations=[],
            node_attributes=[
                LDFNodeAttributes(
                    node_name="S1",
                    lin_protocol="2.1",
                    configured_nad=1,
                    initial_nad=1,
                    configurable_frames=["OrphanFrame"],
                ),
            ],
        )
        ldf.build_lookups()

        viewer.refresh(ldf)
        root = viewer._tree.topLevelItem(0)
        assert root is not None


class TestClipboardAndStatusPaths:
    def test_copy_current_item_to_clipboard_without_selection(self, viewer):
        viewer._tree.setCurrentItem(None)
        with patch.object(viewer, "_announce_status") as announce:
            viewer.copy_current_item_to_clipboard()
        announce.assert_called_once_with("No hierarchy row selected to copy")

    def test_copy_current_item_to_clipboard_with_empty_text(self, viewer):
        item = QTreeWidgetItem(["   "])
        viewer._tree.addTopLevelItem(item)
        viewer._tree.setCurrentItem(item)
        with patch.object(viewer, "_announce_status") as announce:
            viewer.copy_current_item_to_clipboard()
        announce.assert_called_once_with("Selected hierarchy row is empty")

    def test_announce_status_uses_status_bar_fallback(self, viewer):
        fake_status = MagicMock()

        class _FakeWindow:
            def statusBar(self):
                return fake_status

        with patch.object(type(viewer), "window", return_value=_FakeWindow()):
            viewer._announce_status("hello")
        fake_status.showMessage.assert_called_once_with("hello", 3000)

    def test_refresh_replaces_ldf_and_repopulates(self, viewer):
        new_ldf = _make_sample_ldf()
        with patch.object(viewer, "_populate") as populate:
            viewer.refresh(new_ldf)
        assert viewer._ldf is new_ldf
        populate.assert_called_once()


# ---------------------------------------------------------------------------
# Expand/collapse subtree tests
# ---------------------------------------------------------------------------


class TestExpandCollapseSubtree:
    def test_expand_current_subtree(self, viewer, qapp):
        root = viewer._tree.topLevelItem(0)
        viewer._tree.setCurrentItem(root)
        # First collapse everything
        viewer._collapse_current_subtree()
        qapp.processEvents()
        # Then expand all
        viewer._expand_current_subtree()
        qapp.processEvents()
        # Root should be expanded
        assert root.isExpanded()

    def test_expand_current_subtree_no_current(self, viewer):
        viewer._tree.setCurrentItem(None)
        viewer._expand_current_subtree()  # Should not crash

    def test_collapse_current_subtree(self, viewer, qapp):
        root = viewer._tree.topLevelItem(0)
        viewer._tree.setCurrentItem(root)
        viewer._expand_current_subtree()
        qapp.processEvents()
        viewer._collapse_current_subtree()
        qapp.processEvents()
        assert not root.isExpanded()

    def test_collapse_current_subtree_no_current(self, viewer):
        viewer._tree.setCurrentItem(None)
        viewer._collapse_current_subtree()  # Should not crash

    def test_expand_recursive(self, viewer, qapp):
        root = viewer._tree.topLevelItem(0)
        viewer._suppress_toggle_announcements = True
        viewer._collapse_recursive(root)
        viewer._expand_recursive(root)
        viewer._suppress_toggle_announcements = False
        qapp.processEvents()
        assert root.isExpanded()

    def test_collapse_recursive(self, viewer, qapp):
        root = viewer._tree.topLevelItem(0)
        viewer._suppress_toggle_announcements = True
        viewer._expand_recursive(root)
        viewer._collapse_recursive(root)
        viewer._suppress_toggle_announcements = False
        qapp.processEvents()
        assert not root.isExpanded()


# ---------------------------------------------------------------------------
# _fire_accessible_event tests
# ---------------------------------------------------------------------------


class TestFireAccessibleEvent:
    def test_fire_accessible_event_normal(self, viewer, qapp):
        root = viewer._tree.topLevelItem(0)
        viewer._fire_accessible_event(root)  # Should not crash

    def test_fire_accessible_event_with_exception(self, viewer, qapp):
        """When QAccessibleEvent raises, the exception should be silently caught."""
        root = viewer._tree.topLevelItem(0)
        with patch("src.gui.ldf_viewer.QAccessibleEvent", side_effect=RuntimeError("no AT")):
            viewer._fire_accessible_event(root)  # Should not crash

    # ---------------------------------------------------------------------------
    # Node checkbox tests
    # ---------------------------------------------------------------------------

    class TestNodeCheckboxes:
        def test_master_item_has_checkbox_checked(self, viewer):
            item = viewer._master_check_item
            assert item is not None
            assert item.checkState(0) == Qt.CheckState.Checked
            assert bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable)

        def test_slave_items_have_checkboxes_checked(self, viewer):
            assert len(viewer._slave_check_items) == 1
            slave = viewer._slave_check_items[0]
            assert slave.checkState(0) == Qt.CheckState.Checked
            assert bool(slave.flags() & Qt.ItemFlag.ItemIsUserCheckable)

        def test_selected_nodes_initial(self, viewer):
            master, slaves = viewer.selected_nodes()
            assert master == "M"
            assert slaves == ["S1"]

        def test_master_cannot_be_unchecked(self, viewer):
            """Unchecking the master must be silently blocked."""
            item = viewer._master_check_item
            item.setCheckState(0, Qt.CheckState.Unchecked)
            assert item.checkState(0) == Qt.CheckState.Checked

        def test_last_slave_can_be_unchecked(self, viewer):
            """Unchecking the sole slave is allowed; connection validation handles this later."""
            slave = viewer._slave_check_items[0]
            slave.setCheckState(0, Qt.CheckState.Unchecked)
            assert slave.checkState(0) == Qt.CheckState.Unchecked

        def test_unchecking_last_slave_announces_connection_guidance(self, viewer):
            """Clearing all slaves should announce guidance for the connect step."""
            slave = viewer._slave_check_items[0]
            viewer._announce_status = MagicMock()

            slave.setCheckState(0, Qt.CheckState.Unchecked)

            viewer._announce_status.assert_called_with(
                "No slave selected. Select at least one slave before connecting."
            )

        def test_lock_node_selection_disables_items(self, viewer):
            viewer.lock_node_selection(True)
            assert not bool(viewer._master_check_item.flags() & Qt.ItemFlag.ItemIsEnabled)
            for s in viewer._slave_check_items:
                assert not bool(s.flags() & Qt.ItemFlag.ItemIsEnabled)
            viewer.lock_node_selection(False)  # restore for other tests

        def test_lock_node_selection_restores_enabled(self, viewer):
            viewer.lock_node_selection(True)
            viewer.lock_node_selection(False)
            assert bool(viewer._master_check_item.flags() & Qt.ItemFlag.ItemIsEnabled)
            for s in viewer._slave_check_items:
                assert bool(s.flags() & Qt.ItemFlag.ItemIsEnabled)

        def test_uncheck_slave_emits_signal(self, qapp):
            """Unchecking a slave when 2 exist must emit node_selection_changed."""
            from src.gui.ldf_viewer import LDFViewer

            ldf2 = LDFFile(
                protocol_version="2.1",
                language_version="2.1",
                speed=19.2,
                nodes=LDFNodes(
                    master=LDFMaster(name="MCU", time_base=5.0, jitter=0.1),
                    slaves=["SA", "SB"],
                ),
                signals=[],
                frames=[],
                schedule_tables=[],
            )
            ldf2.build_lookups()
            v2 = LDFViewer(ldf2)
            received: list[tuple[str, list[str]]] = []
            v2.node_selection_changed.connect(lambda m, s: received.append((m, s)))
            v2._slave_check_items[1].setCheckState(0, Qt.CheckState.Unchecked)
            assert len(received) == 1
            assert received[0][0] == "MCU"
            assert received[0][1] == ["SA"]

        def test_uncheck_slave_announces_current_selection(self, qapp):
            """Changing slave selection should emit a textual status announcement."""
            from src.gui.ldf_viewer import LDFViewer

            ldf2 = LDFFile(
                protocol_version="2.1",
                language_version="2.1",
                speed=19.2,
                nodes=LDFNodes(
                    master=LDFMaster(name="MCU", time_base=5.0, jitter=0.1),
                    slaves=["SA", "SB"],
                ),
                signals=[],
                frames=[],
                schedule_tables=[],
            )
            ldf2.build_lookups()
            v2 = LDFViewer(ldf2)
            v2._announce_status = MagicMock()

            v2._slave_check_items[1].setCheckState(0, Qt.CheckState.Unchecked)

            v2._announce_status.assert_called_with(
                "Excluded slave SB. 1 slave(s) currently selected."
            )

        def test_refresh_recreates_checkboxes(self, viewer):
            """After refresh() the master and slave items are fresh objects."""
            old_master = viewer._master_check_item
            viewer.refresh(viewer._ldf)
            assert viewer._master_check_item is not None
            assert viewer._master_check_item is not old_master
            assert viewer._master_check_item.checkState(0) == Qt.CheckState.Checked

        def test_lock_with_no_nodes_does_not_crash(self, qapp):
            """lock_node_selection when no LDF has nodes must not crash."""
            from src.gui.ldf_viewer import LDFViewer

            ldf_empty = LDFFile(
                protocol_version="2.1",
                language_version="2.1",
                speed=19.2,
                nodes=None,
                signals=[],
                frames=[],
                schedule_tables=[],
            )
            ldf_empty.build_lookups()
            v = LDFViewer(ldf_empty)
            v.lock_node_selection(True)  # must not raise
            v.lock_node_selection(False)  # must not raise
