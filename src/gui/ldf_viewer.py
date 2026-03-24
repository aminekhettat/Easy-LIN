"""Hierarchical LDF viewer widget for the Qt frontend.

Displays the parsed LDF content as a single expandable tree where values and
attributes are directly visible under each node.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.7.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

# pylint: disable=too-many-lines

import logging
import os

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QPushButton,
)
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QAccessibleEvent
from PySide6.QtGui import QAccessible

from src.ldf_parser import LDFEncodingType, LDFFile

log = logging.getLogger(__name__)


def _bold_font() -> QFont:
    """Return a reusable bold font for section headers."""
    f = QFont()
    f.setBold(True)
    return f


class LDFViewer(QWidget):
    """Single-pane hierarchical LDF viewer with direct attribute nodes."""

    node_selection_changed = Signal(str, list)
    """Emitted when the user changes the node checkbox selection.

    Args:
        master_name (str): the currently checked master node name.
        slave_names (list[str]): list of currently checked slave node names.
    """

    def __init__(self, ldf: LDFFile, parent=None):
        """Initialize the viewer for one parsed LDF object."""
        super().__init__(parent)
        self._ldf = ldf
        self._suppress_toggle_announcements = False
        self._deferred_reanchor_timer_id: int | None = None
        self._deferred_reanchor_item: QTreeWidgetItem | None = None
        self._debug_tree = os.environ.get("EASYLIN_DEBUG_TREE", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._master_check_item: QTreeWidgetItem | None = None
        self._slave_check_items: list[QTreeWidgetItem] = []
        self._master_name: str | None = None
        self._in_populate: bool = False
        self._node_selection_locked: bool = False
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        """Create the tree widget layout with search bar and breadcrumb."""
        self.setAccessibleName("LDF viewer")
        self.setAccessibleDescription(
            "Viewer for navigating the loaded LIN Description File hierarchy and selecting communication nodes."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- Search bar (hidden by default, toggled with Ctrl+F) ---
        self._search_bar = QWidget()
        self._search_bar.setAccessibleName("Hierarchy search bar")
        self._search_bar.setAccessibleDescription(
            "Container with controls for searching text inside the hierarchy tree."
        )
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(0, 0, 0, 4)
        search_label = QLabel("Search:")
        search_label.setAccessibleName("Search label")
        search_label.setAccessibleDescription("Label for the hierarchy tree search field.")
        search_layout.addWidget(search_label)
        self._search_edit = QLineEdit()
        self._search_edit.setAccessibleName("Search tree items")
        self._search_edit.setAccessibleDescription(
            "Type text to search the hierarchy tree, then press Enter or F3 to move through matches."
        )
        self._search_edit.setPlaceholderText("Type to search tree items...")
        self._search_edit.setStyleSheet("QLineEdit:focus { border: 2px solid #005A9C; }")
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self._search_edit.returnPressed.connect(self._find_next_match)
        search_layout.addWidget(self._search_edit)
        self._search_close_btn = QPushButton("Close")
        self._search_close_btn.setFixedWidth(60)
        self._search_close_btn.setAccessibleName("Close search bar")
        self._search_close_btn.setAccessibleDescription(
            "Hide the search bar and return keyboard focus to the hierarchy tree."
        )
        self._search_close_btn.clicked.connect(self._hide_search)
        search_layout.addWidget(self._search_close_btn)
        self._search_bar.setVisible(False)
        self._search_matches: list[QTreeWidgetItem] = []
        self._search_match_index = -1
        layout.addWidget(self._search_bar)

        # --- Breadcrumb trail ---
        self._breadcrumb = QLabel("")
        self._breadcrumb.setAccessibleName("Current position in hierarchy")
        self._breadcrumb.setAccessibleDescription(
            "Breadcrumb trail showing the current hierarchy path and sibling position."
        )
        self._breadcrumb.setWordWrap(True)
        self._breadcrumb.setStyleSheet(
            "QLabel { color: #333; padding: 2px 4px; "
            "background-color: #f0f0f0; border-radius: 3px; }"
            "QLabel:focus { border: 2px solid #005A9C; }"
        )
        layout.addWidget(self._breadcrumb)

        # --- Tree widget ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Hierarchy"])
        self._tree.setAlternatingRowColors(True)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._tree.setAccessibleName("LDF hierarchy tree")
        self._tree.setAccessibleDescription(
            "Tree view of nodes, frames, signals, encodings, schedules, and attributes"
        )
        self._tree.setStyleSheet("QTreeWidget:focus { border: 2px solid #005A9C; }")

        # --- Shortcuts ---
        self._copy_shortcut = QShortcut(QKeySequence.Copy, self._tree)
        self._copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._copy_shortcut.activated.connect(self.copy_current_item_to_clipboard)

        self._search_shortcut = QShortcut(QKeySequence.Find, self)
        self._search_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._search_shortcut.activated.connect(self._show_search)

        self._find_next_shortcut = QShortcut(QKeySequence.FindNext, self)
        self._find_next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._find_next_shortcut.activated.connect(self._find_next_match)

        self._expand_all_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Right"), self._tree)
        self._expand_all_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._expand_all_shortcut.activated.connect(self._expand_current_subtree)

        self._collapse_all_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Left"), self._tree)
        self._collapse_all_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._collapse_all_shortcut.activated.connect(self._collapse_current_subtree)

        # Keep keyboard cursor aligned with the toggled branch and narrate state changes.
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        self._tree.currentItemChanged.connect(self._on_current_item_changed)
        self._tree.itemChanged.connect(self._on_node_item_changed)
        self._tree.installEventFilter(self)

        layout.addWidget(self._tree)

    def eventFilter(self, obj, event):
        """Stabilize keyboard navigation to avoid focus jumps on branch toggles."""
        if obj is self._tree and event.type() == QEvent.Type.KeyPress:
            # Cancel any pending deferred re-anchor callback before processing new keys.
            # This prevents race conditions when Left-Right-Left sequences execute too fast.
            if self._deferred_reanchor_timer_id is not None:
                self.killTimer(self._deferred_reanchor_timer_id)
                self._deferred_reanchor_timer_id = None

            current = self._tree.currentItem()
            if current is None:
                return super().eventFilter(obj, event)

            # If current item ended up inside a collapsed branch (possible after
            # mixed mouse/keyboard interactions), re-anchor navigation to the
            # nearest visible ancestor before processing movement keys.
            anchor = self._visible_navigation_anchor(current)
            if anchor is not current:
                self._debug_tree_event("Normalize-hidden-current", anchor)
                self._tree.setCurrentItem(anchor)
                self._tree.scrollToItem(anchor, QAbstractItemView.ScrollHint.EnsureVisible)
                current = anchor

            self._debug_tree_event("KeyPress", current, key=event.key())

            if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._toggle_current_checkable_node(current):
                    return True

            if (
                event.key() == Qt.Key.Key_Down
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
            ):
                target = self._next_navigation_item(current)
                if target is not None:
                    self._debug_tree_event("Down-next-item", target)
                    self._select_and_reveal_item(target)
                    self._announce_navigation_target(target)
                else:
                    self._announce_status("No next hierarchy item at this level.")
                return True

            if event.key() == Qt.Key.Key_Up and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                target = self._previous_navigation_item(current)
                if target is not None:
                    self._debug_tree_event("Up-previous-item", target)
                    self._select_and_reveal_item(target)
                    self._announce_navigation_target(target)
                else:
                    self._announce_status("No previous hierarchy item at this level.")
                return True

            if event.key() == Qt.Key.Key_Right:
                # Right: expand current branch, then use it again to enter the first child.
                if current.childCount() > 0 and not current.isExpanded():
                    self._debug_tree_event("Right-expand", current)
                    # Suppress the toggle announcement so only keyboard-driven feedback is heard.
                    self._suppress_toggle_announcements = True
                    self._tree.expandItem(current)
                    self._suppress_toggle_announcements = False
                    return True
                if current.childCount() > 0:
                    child = current.child(0)
                    self._debug_tree_event("Right-first-child", child)
                    self._select_and_reveal_item(child)
                    self._announce_navigation_target(child)
                return True  # Always consume Right (leaf nodes too)

            if event.key() == Qt.Key.Key_Left:
                # Left: collapse current branch; if already collapsed, go to parent.
                if current.childCount() > 0 and current.isExpanded():
                    self._debug_tree_event("Left-collapse", current)
                    # Suppress the toggle announcement so only the reanchor announcement is heard.
                    self._suppress_toggle_announcements = True
                    self._tree.collapseItem(current)
                    self._suppress_toggle_announcements = False
                    # Assistive technologies may shift focus when the accessibility
                    # tree changes during collapse. Re-anchor one event loop later.
                    # Store the current item reference for the deferred callback.
                    self._deferred_reanchor_item = current
                    # A previous deferred timer was already cancelled at key-press entry.
                    self._deferred_reanchor_timer_id = self.startTimer(0)
                    return True
                parent = current.parent()
                if parent is not None:
                    self._debug_tree_event("Left-go-parent", parent)
                    self._select_and_reveal_item(parent)
                    self._announce_navigation_target(parent)
                return True  # Always consume Left (top-level collapsed nodes too)

            # Alt+Down: next sibling
            if (
                event.key() == Qt.Key.Key_Down
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            ):
                sibling = self._next_sibling(current)
                if sibling is not None:
                    self._debug_tree_event("Alt-Down-sibling", sibling)
                    self._select_and_reveal_item(sibling)
                    self._announce_navigation_target(sibling)
                return True

            # Alt+Up: previous sibling
            if event.key() == Qt.Key.Key_Up and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                sibling = self._previous_sibling(current)
                if sibling is not None:
                    self._debug_tree_event("Alt-Up-sibling", sibling)
                    self._select_and_reveal_item(sibling)
                    self._announce_navigation_target(sibling)
                return True

        return super().eventFilter(obj, event)

    def timerEvent(self, event):
        """Handle timer events for deferred re-anchor callback after collapse."""
        if event.timerId() == self._deferred_reanchor_timer_id:
            self.killTimer(self._deferred_reanchor_timer_id)
            self._deferred_reanchor_timer_id = None
            if self._deferred_reanchor_item is not None:
                self._reanchor_after_collapse(self._deferred_reanchor_item)
                self._deferred_reanchor_item = None
        else:
            super().timerEvent(event)

    def _toggle_current_checkable_node(self, item: QTreeWidgetItem) -> bool:
        """Toggle one checkable node from the keyboard, honoring lock state."""
        if not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return False
        if self._node_selection_locked or not item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self._announce_status("Node selection is locked while communication is connected.")
            return True

        target = (
            Qt.CheckState.Unchecked
            if item.checkState(0) == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        item.setCheckState(0, target)
        return True

    def _select_and_reveal_item(self, item: QTreeWidgetItem) -> None:
        """Make one tree item current and keep it visible in the viewport."""
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._debug_tree_event("SelectReveal", item)

    def _reanchor_after_collapse(self, item: QTreeWidgetItem) -> None:
        """Re-assert tree focus and current item one event loop after a collapse.

        Assistive technologies may shift OS focus when the accessibility tree
        shrinks during collapse.  This deferred call overrides that shift so
        keyboard navigation resumes from the collapsed branch without requiring
        Page Down. The screen reader is then told the new position.
        """
        self._tree.setFocus(Qt.FocusReason.OtherFocusReason)
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        # Announce the position so the screen reader knows where we landed.
        self._announce_navigation_target(item)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Keep focus on expanded item and announce the open action."""
        if self._suppress_toggle_announcements:
            return
        self._debug_tree_event("Expanded-signal", item)
        self._tree.setFocus(Qt.FocusReason.OtherFocusReason)
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._announce_tree_toggle("Opened", item)

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Keep focus on collapsed item without jarring viewport repositioning."""
        if self._suppress_toggle_announcements:
            return
        self._debug_tree_event("Collapsed-signal", item)
        self._tree.setFocus(Qt.FocusReason.OtherFocusReason)
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._announce_tree_toggle("Closed", item)

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        """Update breadcrumb and accessibility when the current item changes.

        Scrolling is handled exclusively by _select_and_reveal_item (keyboard
        navigation) and the expand/collapse handlers so the viewport is never
        repositioned by passive selection changes such as mouse clicks.
        """
        if current is not None:
            self._debug_tree_event("CurrentChanged", current)
            self._update_breadcrumb(current)
            self._fire_accessible_event(current)

    def _announce_tree_toggle(self, action: str, item: QTreeWidgetItem) -> None:
        """Emit audible + textual feedback when a branch is opened/closed."""
        QApplication.beep()
        self._announce_status(f"{action}: {item.text(0)}")
        self._debug_tree_event(f"Announce-{action}", item)

    def _debug_tree_event(
        self, event_name: str, item: QTreeWidgetItem, key: int | None = None
    ) -> None:
        """Emit structured tree-navigation diagnostics when EASYLIN_DEBUG_TREE is enabled."""
        if not self._debug_tree:
            return
        parts = []
        node = item
        while node is not None:
            parts.append(node.text(0))
            node = node.parent()
        parts.reverse()
        key_text = f" key={key}" if key is not None else ""
        log.info(
            "[TREE] %s%s | current='%s' | path=%s",
            event_name,
            key_text,
            item.text(0),
            " > ".join(parts),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _show_search(self) -> None:
        """Show the search bar and focus the search input."""
        self._search_bar.setVisible(True)
        self._search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_edit.selectAll()

    def _hide_search(self) -> None:
        """Hide the search bar and return focus to the tree."""
        self._search_bar.setVisible(False)
        self._search_matches.clear()
        self._search_match_index = -1
        self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _on_search_text_changed(self, text: str) -> None:
        """Build the list of matching items when the search text changes."""
        self._search_matches.clear()
        self._search_match_index = -1
        if not text.strip():
            return
        needle = text.strip().lower()
        self._collect_matches(self._tree.invisibleRootItem(), needle)
        if self._search_matches:
            self._search_match_index = 0
            self._select_and_reveal_item(self._search_matches[0])
            self._announce_status(
                f"Match 1 of {len(self._search_matches)}: {self._search_matches[0].text(0)}"
            )
        else:
            self._announce_status("No matches found")

    def _collect_matches(self, parent: QTreeWidgetItem, needle: str) -> None:
        """Recursively collect tree items whose text contains the needle."""
        for i in range(parent.childCount()):
            child = parent.child(i)
            if needle in child.text(0).lower():
                self._search_matches.append(child)
            self._collect_matches(child, needle)

    def _find_next_match(self) -> None:
        """Move to the next search match (wraps around)."""
        if not self._search_matches:
            return
        self._search_match_index = (self._search_match_index + 1) % len(self._search_matches)
        item = self._search_matches[self._search_match_index]
        self._select_and_reveal_item(item)
        self._announce_status(
            f"Match {self._search_match_index + 1} of {len(self._search_matches)}: {item.text(0)}"
        )

    # ------------------------------------------------------------------
    # Breadcrumb and position
    # ------------------------------------------------------------------

    def _update_breadcrumb(self, item: QTreeWidgetItem) -> None:
        """Update the breadcrumb label with the path from root to the current item."""
        parts = []
        node = item
        while node is not None:
            parts.append(node.text(0))
            node = node.parent()
        parts.reverse()
        breadcrumb_path = " > ".join(parts)

        # Sibling position
        position = self._sibling_position(item)
        if position:
            self._breadcrumb.setText(f"{position} \u2014 {breadcrumb_path}")
        else:
            self._breadcrumb.setText(breadcrumb_path)

    @staticmethod
    def _sibling_position(item: QTreeWidgetItem) -> str:
        """Return a string like 'Item 3 of 5' based on the item's position among siblings."""
        parent = item.parent()
        if parent is None:
            tree = item.treeWidget()
            if tree is None:
                return ""
            total = tree.topLevelItemCount()
            index = tree.indexOfTopLevelItem(item)
        else:
            total = parent.childCount()
            index = parent.indexOfChild(item)
        if total <= 1:
            return ""
        return f"Item {index + 1} of {total}"

    # ------------------------------------------------------------------
    # Sibling navigation
    # ------------------------------------------------------------------

    @staticmethod
    def _next_sibling(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        """Return the next sibling of the given item, or None."""
        parent = item.parent()
        if parent is None:
            tree = item.treeWidget()
            if tree is None:
                return None
            idx = tree.indexOfTopLevelItem(item)
            if idx + 1 < tree.topLevelItemCount():
                return tree.topLevelItem(idx + 1)
            return None
        idx = parent.indexOfChild(item)
        if idx + 1 < parent.childCount():
            return parent.child(idx + 1)
        return None

    @staticmethod
    def _visible_navigation_anchor(item: QTreeWidgetItem) -> QTreeWidgetItem:
        """Return the nearest visible ancestor usable as a navigation anchor."""
        node = item
        while node.parent() is not None and not node.parent().isExpanded():
            node = node.parent()
        return node

    @classmethod
    def _next_navigation_item(cls, item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        """Return the next item in depth-first visual order.

        If the current item is expanded and has children the first child is
        returned (depth-first descent).  Otherwise the traversal walks up the
        tree until a next sibling is found, mirroring the linear reading order
        used by screen readers.
        """
        if item.isExpanded() and item.childCount() > 0:
            return item.child(0)
        node = item
        while node is not None:
            sibling = cls._next_sibling(node)
            if sibling is not None:
                return sibling
            node = node.parent()
        return None

    @classmethod
    def _last_visible_descendant(cls, item: QTreeWidgetItem) -> QTreeWidgetItem:
        """Return the last visible descendant of an item in depth-first order.

        Walks to the last child of each expanded item until a collapsed node or
        a leaf is reached.  Used by Up-key navigation to land on the deepest
        visible item inside the preceding branch.
        """
        while item.isExpanded() and item.childCount() > 0:
            item = item.child(item.childCount() - 1)
        return item

    @staticmethod
    def _previous_sibling(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        """Return the previous sibling of the given item, or None."""
        parent = item.parent()
        if parent is None:
            tree = item.treeWidget()
            if tree is None:
                return None
            idx = tree.indexOfTopLevelItem(item)
            if idx > 0:
                return tree.topLevelItem(idx - 1)
            return None
        idx = parent.indexOfChild(item)
        if idx > 0:
            return parent.child(idx - 1)
        return None

    @classmethod
    def _previous_navigation_item(cls, item: QTreeWidgetItem) -> QTreeWidgetItem | None:
        """Return the previous item in depth-first visual order.

        When a previous sibling exists the traversal descends into its last
        visible descendant so Up-arrow mirrors the reverse of Down-arrow.
        When there is no previous sibling the parent branch is returned.
        """
        sibling = cls._previous_sibling(item)
        if sibling is not None:
            return cls._last_visible_descendant(sibling)
        return item.parent()

    def _announce_navigation_target(self, item: QTreeWidgetItem) -> None:
        """Send concise speech-friendly feedback for keyboard navigation targets."""
        parts = [item.text(0)]
        position = self._sibling_position(item)
        if position:
            parts.append(position)
        if item.childCount() > 0:
            parts.append("expanded" if item.isExpanded() else "collapsed")
        self._announce_status(". ".join(parts))

    # ------------------------------------------------------------------
    # Expand/collapse subtree
    # ------------------------------------------------------------------

    def _expand_current_subtree(self) -> None:
        """Recursively expand all children of the current item."""
        current = self._tree.currentItem()
        if current is None:
            return
        self._suppress_toggle_announcements = True
        try:
            self._expand_recursive(current)
        finally:
            self._suppress_toggle_announcements = False
        self._announce_status(f"Expanded all under: {current.text(0)}")

    def _collapse_current_subtree(self) -> None:
        """Recursively collapse all children of the current item."""
        current = self._tree.currentItem()
        if current is None:
            return
        self._suppress_toggle_announcements = True
        try:
            self._collapse_recursive(current)
        finally:
            self._suppress_toggle_announcements = False
        self._announce_status(f"Collapsed all under: {current.text(0)}")

    def _expand_recursive(self, item: QTreeWidgetItem) -> None:
        """Expand item and all its descendants."""
        self._tree.expandItem(item)
        for i in range(item.childCount()):
            self._expand_recursive(item.child(i))

    def _collapse_recursive(self, item: QTreeWidgetItem) -> None:
        """Collapse item and all its descendants."""
        for i in range(item.childCount()):
            self._collapse_recursive(item.child(i))
        self._tree.collapseItem(item)

    # ------------------------------------------------------------------
    # Accessible events
    # ------------------------------------------------------------------

    def _fire_accessible_event(self, item: QTreeWidgetItem) -> None:
        """Notify assistive technology about the current item change."""
        try:
            event = QAccessibleEvent(self._tree, QAccessible.Event.Focus)
            QAccessible.updateAccessibility(event)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tree building helpers
    # ------------------------------------------------------------------

    def _add_item(
        self,
        parent: QTreeWidgetItem | QTreeWidget,
        element: str,
        value: str = "",
        bold: bool = False,
    ) -> QTreeWidgetItem:
        """Add one row to the hierarchy tree."""
        label = f"{element}: {value}" if value else element
        item = QTreeWidgetItem([label])
        if bold:
            item.setFont(0, _bold_font())
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _add_property_nodes(self, parent: QTreeWidgetItem, props: list[tuple[str, str]]) -> None:
        """Append attribute/value pairs directly as children in the tree."""
        for key, val in props:
            self._add_item(parent, key, val)

    def _build_signal_encoding_map(self) -> dict[str, str]:
        """Map signal name to encoding type name for quick lookup."""
        mapping: dict[str, str] = {}
        for rep in self._ldf.signal_representations:
            for sig_name in rep.signals:
                mapping[sig_name] = rep.encoding_type
        return mapping

    def _build_encoding_lookup(self) -> dict[str, LDFEncodingType]:
        """Map encoding type name to encoding object."""
        return {enc.name: enc for enc in self._ldf.encoding_types}

    def _add_encoding_details(
        self,
        signal_item: QTreeWidgetItem,
        encoding_name: str,
        encoding_lookup: dict[str, LDFEncodingType],
    ) -> None:
        """Attach encoding details under one signal's Encoding node."""
        encoding_item = self._add_item(signal_item, "Encoding", encoding_name)
        if encoding_name == "none":
            self._add_item(encoding_item, "Details", "No signal encoding mapping")
            return

        enc = encoding_lookup.get(encoding_name)
        if enc is None:
            self._add_item(encoding_item, "Details", "Encoding definition not found")
            return

        self._add_property_nodes(
            encoding_item,
            [
                ("BCD", "yes" if enc.bcd else "no"),
                ("ASCII", "yes" if enc.ascii else "no"),
                ("Logical values count", str(len(enc.logical_values))),
                ("Physical ranges count", str(len(enc.physical_ranges))),
            ],
        )

        logical_root = self._add_item(encoding_item, "Logical values")
        if not enc.logical_values:
            self._add_item(logical_root, "none")
        for lv in enc.logical_values:
            self._add_item(logical_root, str(lv.signal_value), lv.text)

        physical_root = self._add_item(encoding_item, "Physical ranges")
        if not enc.physical_ranges:
            self._add_item(physical_root, "none")
        for pr in enc.physical_ranges:
            unit = pr.unit if pr.unit else "none"
            pr_item = self._add_item(physical_root, f"{pr.min_value}..{pr.max_value}")
            self._add_property_nodes(
                pr_item,
                [
                    ("Scale", str(pr.scale)),
                    ("Offset", str(pr.offset)),
                    ("Unit", unit),
                    ("Formula", f"physical = (raw * {pr.scale}) + {pr.offset}"),
                ],
            )

    def _frame_related_to_slave(self, frame_name: str, slave_name: str) -> bool:
        """Return whether a frame is related to a slave by publisher or subscriber links."""
        frame = self._ldf.frame_by_name(frame_name)
        if frame is None:
            return False
        if frame.publisher == slave_name:
            return True
        for ref in frame.signals:
            sig = self._ldf.signal(ref.signal_name)
            if sig and slave_name in sig.subscribers:
                return True
        return False

    @staticmethod
    def _is_diagnostic_frame_id(frame_id: int) -> bool:
        """Return whether a frame ID is reserved for LIN diagnostic traffic."""
        return frame_id in (0x3C, 0x3D)

    @staticmethod
    def _lin_protected_id(frame_id: int) -> int:
        """Compute the LIN 2.x protected identifier (appends parity bits P0/P1)."""
        fid = frame_id & 0x3F
        id0, id1, id2, id3, id4, id5 = ((fid >> i) & 1 for i in range(6))
        p0 = (id0 ^ id1 ^ id2 ^ id4) & 1
        p1 = (~(id1 ^ id3 ^ id4 ^ id5)) & 1
        return fid | (p0 << 6) | (p1 << 7)

    def _build_periodicity_map(self) -> dict[str, list[tuple[str, float]]]:
        """Map frame_name to a list of (table_name, delay_ms) from all schedule tables."""
        result: dict[str, list[tuple[str, float]]] = {}
        for table in self._ldf.schedule_tables:
            for entry in table.entries:
                result.setdefault(entry.frame_name, []).append((table.name, entry.delay))
        return result

    def _add_frame_signal_details(
        self,
        parent: QTreeWidgetItem,
        frame,
        signal_encoding: dict[str, str],
        encoding_lookup: dict[str, LDFEncodingType],
        context_node: str | None = None,
    ) -> None:
        """Attach frame signal rows with characteristics and encoding details.

        context_node: When given, a ``Direction`` property (TX/RX) is added
                      to each signal relative to that node.
        """
        if not frame.signals:
            self._add_item(parent, "Signals", "none")
            return

        for ref in frame.signals:
            sig = self._ldf.signal(ref.signal_name)
            sig_item = self._add_item(parent, ref.signal_name)
            if sig is None:
                self._add_property_nodes(
                    sig_item,
                    [
                        ("Bit offset", str(ref.bit_offset)),
                        ("Details", "Signal definition not found"),
                    ],
                )
                continue

            enc_name = signal_encoding.get(sig.name, "none")
            props: list[tuple[str, str]] = [
                ("Bit offset", str(ref.bit_offset)),
                ("Size", f"{sig.size} bit"),
                ("Initial value", str(sig.init_value)),
                ("Subscribers", ", ".join(sig.subscribers) or "none"),
            ]
            self._add_property_nodes(sig_item, props)
            self._add_encoding_details(sig_item, enc_name, encoding_lookup)

    def _populate(self) -> None:
        """Populate the full LDF hierarchy in one expandable tree."""
        ldf = self._ldf
        self._tree.clear()
        self._master_check_item = None
        self._slave_check_items = []
        self._master_name = None
        self._in_populate = True
        signal_encoding = self._build_signal_encoding_map()
        encoding_lookup = self._build_encoding_lookup()
        periodicity_map = self._build_periodicity_map()
        node_attributes_by_name = {attr.node_name: attr for attr in ldf.node_attributes}

        def _add_node_attributes(node_item: QTreeWidgetItem, node_name: str) -> None:
            """Attach parsed Node_attributes data under one node when available."""
            attr = node_attributes_by_name.get(node_name)
            if attr is None:
                return
            self._add_property_nodes(
                node_item,
                [
                    ("LIN protocol", attr.lin_protocol or "not set"),
                    ("Configured NAD", str(attr.configured_nad)),
                    ("Initial NAD", str(attr.initial_nad)),
                    (
                        "Product ID",
                        f"{attr.product_id_supplier}, {attr.product_id_function}, {attr.product_id_variant}",
                    ),
                    ("Response error signal", attr.response_error or "not set"),
                    ("P2 min", f"{attr.p2_min} ms"),
                    ("ST min", f"{attr.st_min} ms"),
                    ("N_As timeout", f"{attr.n_as_timeout} ms"),
                    ("N_Cr timeout", f"{attr.n_cr_timeout} ms"),
                ],
            )
            cfg = self._add_item(node_item, "Configurable frames")
            if not attr.configurable_frames:
                self._add_item(cfg, "none")
            for frame_name in attr.configurable_frames:
                self._add_item(cfg, frame_name)

        root = self._add_item(self._tree, "LDF cluster", ldf.source_path or "", bold=True)

        header = self._add_item(root, "Header", "", bold=True)
        self._add_property_nodes(
            header,
            [
                ("Protocol version", ldf.protocol_version),
                ("Language version", ldf.language_version),
                ("Baudrate", f"{ldf.speed} kbps"),
                ("Channel name", ldf.channel_name or "not defined"),
            ],
        )

        nodes = self._add_item(root, "Nodes", "", bold=True)
        if ldf.nodes:
            master = self._add_item(nodes, f"Master (1): {ldf.nodes.master.name}")
            master.setFlags(master.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            master.setCheckState(0, Qt.CheckState.Checked)
            master.setToolTip(0, "LIN master node — always active in the communication session.")
            self._master_check_item = master
            self._master_name = ldf.nodes.master.name
            self._add_property_nodes(
                master,
                [
                    ("Time base", f"{ldf.nodes.master.time_base} ms"),
                    ("Jitter", f"{ldf.nodes.master.jitter} ms"),
                ],
            )
            _add_node_attributes(master, ldf.nodes.master.name)
            slaves = self._add_item(nodes, f"Slaves ({len(ldf.nodes.slaves)})")
            for slave in ldf.nodes.slaves:
                slave_item = self._add_item(slaves, slave)
                slave_item.setFlags(slave_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                slave_item.setCheckState(0, Qt.CheckState.Checked)
                slave_item.setToolTip(
                    0, "Uncheck to exclude this slave from the communication session."
                )
                self._slave_check_items.append(slave_item)
                _add_node_attributes(slave_item, slave)
                slave_frames = self._add_item(slave_item, "Related frames")
                related_frames = [
                    frame for frame in ldf.frames if self._frame_related_to_slave(frame.name, slave)
                ]
                if not related_frames:
                    self._add_item(slave_frames, "none")
                for frame in related_frames:
                    pid = self._lin_protected_id(frame.frame_id)
                    direction = (
                        "TX (Slave publishes)"
                        if frame.publisher == slave
                        else "RX (Slave subscribes)"
                    )
                    periods = periodicity_map.get(frame.name, [])
                    period_text = (
                        ", ".join(f"{d} ms [{t}]" for t, d in periods)
                        if periods
                        else "not scheduled"
                    )
                    frame_item = self._add_item(
                        slave_frames,
                        frame.name,
                        f"0x{frame.frame_id:02X} ({frame.frame_size} byte(s))",
                    )
                    self._add_property_nodes(
                        frame_item,
                        [
                            ("Frame ID", f"0x{frame.frame_id:02X} ({frame.frame_id} decimal)"),
                            ("Protected ID (PID)", f"0x{pid:02X} ({pid} decimal)"),
                            ("Publisher", frame.publisher),
                            ("Direction", direction),
                            ("Frame size", f"{frame.frame_size} byte(s)"),
                            ("Periodicity", period_text),
                        ],
                    )
                    self._add_frame_signal_details(
                        frame_item, frame, signal_encoding, encoding_lookup, context_node=slave
                    )

        diagnostic_frames = [
            frame for frame in ldf.frames if self._is_diagnostic_frame_id(frame.frame_id)
        ]
        diagnostics = self._add_item(
            root,
            f"Diagnostic frames ({len(diagnostic_frames)})",
            "",
            bold=True,
        )
        for frame in diagnostic_frames:
            pid = self._lin_protected_id(frame.frame_id)
            periods = periodicity_map.get(frame.name, [])
            period_text = (
                ", ".join(f"{d} ms [{t}]" for t, d in periods) if periods else "not scheduled"
            )
            frame_item = self._add_item(
                diagnostics,
                frame.name,
                f"0x{frame.frame_id:02X} ({frame.frame_size} byte(s))",
            )
            self._add_property_nodes(
                frame_item,
                [
                    ("Frame ID", f"0x{frame.frame_id:02X} ({frame.frame_id} decimal)"),
                    ("Protected ID (PID)", f"0x{pid:02X} ({pid} decimal)"),
                    ("Publisher", frame.publisher),
                    ("Frame size", f"{frame.frame_size} byte(s)"),
                    ("Periodicity", period_text),
                ],
            )
            self._add_frame_signal_details(frame_item, frame, signal_encoding, encoding_lookup)

        schedules = self._add_item(
            root,
            f"Schedule tables ({len(ldf.schedule_tables)})",
            "",
            bold=True,
        )
        for table in ldf.schedule_tables:
            table_item = self._add_item(schedules, table.name)
            self._add_item(table_item, "Entries", str(len(table.entries)))
            for idx, entry in enumerate(table.entries, start=1):
                frame = ldf.frame_by_name(entry.frame_name)
                frame_id = f"0x{frame.frame_id:02X}" if frame else "unknown"
                entry_item = self._add_item(table_item, f"{idx}. {entry.frame_name}")
                self._add_property_nodes(
                    entry_item,
                    [
                        ("Delay", f"{entry.delay} ms"),
                        ("Frame ID", frame_id),
                    ],
                )

        # Expand all levels so every signal attribute and encoding detail is reachable
        # immediately via keyboard without any manual expand step.
        self._suppress_toggle_announcements = True
        try:
            self._tree.expandToDepth(9)
        finally:
            self._suppress_toggle_announcements = False
        self._tree.setCurrentItem(root)
        self._in_populate = False

    # ------------------------------------------------------------------
    # Node checkbox handling
    # ------------------------------------------------------------------

    def _on_node_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Enforce checkbox invariants and emit selection changes."""
        if self._in_populate or column != 0:
            return
        if item is self._master_check_item:
            if item.checkState(0) != Qt.CheckState.Checked:
                self._tree.blockSignals(True)
                item.setCheckState(0, Qt.CheckState.Checked)
                self._tree.blockSignals(False)
            return
        if item in self._slave_check_items:
            if self._node_selection_locked:
                return
            master, slaves = self.selected_nodes()
            if master is not None:
                action = "Selected" if item.checkState(0) == Qt.CheckState.Checked else "Excluded"
                if slaves:
                    self._announce_status(
                        f"{action} slave {item.text(0)}. {len(slaves)} slave(s) currently selected."
                    )
                else:
                    self._announce_status(
                        "No slave selected. Select at least one slave before connecting."
                    )
                self.node_selection_changed.emit(master, slaves)
            return
        # Any other item: silently revert any accidental check state change so
        # non-master/slave rows can never appear checked in the tree.
        if item.checkState(0) != Qt.CheckState.Unchecked:
            self._tree.blockSignals(True)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self._tree.blockSignals(False)

    def selected_nodes(self) -> tuple[str | None, list[str]]:
        """Return (master_name, [checked_slave_names]) from checkbox state."""
        slaves = [
            item.text(0)
            for item in self._slave_check_items
            if item.checkState(0) == Qt.CheckState.Checked
        ]
        return self._master_name, slaves

    def lock_node_selection(self, locked: bool) -> None:
        """Disable or re-enable node checkbox interaction (locked during communication)."""
        self._node_selection_locked = locked
        items: list[QTreeWidgetItem] = []
        if self._master_check_item is not None:
            items.append(self._master_check_item)
        items.extend(self._slave_check_items)
        for item in items:
            f = item.flags()
            if locked:
                item.setFlags(f & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(f | Qt.ItemFlag.ItemIsEnabled)

    def focus_hierarchy_tree(self) -> None:
        """Move keyboard focus to the hierarchy tree."""
        self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def focus_hierarchy_details(self) -> None:
        """Alias kept for compatibility; details are directly shown in the tree."""
        self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def copy_current_item_to_clipboard(self) -> None:
        """Copy the focused hierarchy row text to the system clipboard."""
        item = self._tree.currentItem()
        if item is None:
            self._announce_status("No hierarchy row selected to copy")
            return

        text = item.text(0).strip()
        if not text:
            self._announce_status("Selected hierarchy row is empty")
            return

        QApplication.clipboard().setText(text)
        self._announce_status(f"Copied: {text}")

    def _announce_status(self, message: str) -> None:
        """Send a short feedback message to the main window status bar when available."""
        window = self.window()
        event_announcer = getattr(window, "_announce_event", None)
        if callable(event_announcer):
            event_announcer(message)
            return
        status_getter = getattr(window, "statusBar", None)
        if callable(status_getter):
            status_getter().showMessage(message, 3000)

    def refresh(self, ldf: LDFFile) -> None:
        """Reload the viewer with a new LDF object."""
        self._ldf = ldf
        self._populate()
