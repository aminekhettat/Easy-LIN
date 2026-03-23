"""Standalone communication window for Easy-LIN.

Wraps the :class:`CommunicationPanel` in its own top-level window so that
LDF analysis and hardware communication are managed independently.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.6.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
        in LICENSE.
"""

from PySide6.QtCore import Signal, QSettings, QTimer
from PySide6.QtWidgets import QMainWindow

from src.gui.communication_panel import CommunicationPanel
from src.ldf_parser import LDFFile


class CommunicationWindow(QMainWindow):
    """Top-level window hosting the hardware communication panel."""

    status_message = Signal(str)
    """Re-emitted from the inner communication panel."""

    communication_state_changed = Signal(str)
    """Re-emitted from the inner communication panel."""

    def __init__(self, parent=None) -> None:
        """Initialize the communication window with an embedded panel."""
        super().__init__(parent)
        self.setWindowTitle("Easy-LIN \u2014 Communication")
        self.setMinimumSize(500, 600)
        self.setObjectName("CommunicationWindow")

        self._comm_panel = CommunicationPanel()
        self._comm_panel.status_message.connect(self.status_message)
        self._comm_panel.communication_state_changed.connect(self.communication_state_changed)
        self.setCentralWidget(self._comm_panel)

        self._settings = QSettings("Easy-LIN", "Easy-LIN")
        self._pending_ldf: LDFFile | None = None
        self._pending_selection: tuple[str, list[str]] | None = None
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_pending_updates)
        self._restore_geometry()

    def load_ldf(self, ldf: LDFFile) -> None:
        """Forward a parsed LDF file to the communication panel."""
        self._comm_panel.load_ldf(ldf)

    def configure_selection(self, master: str, slaves: list[str]) -> None:
        """Forward selected communication nodes to the communication panel."""
        self._comm_panel.configure_selection(master, slaves)

    def queue_ldf(self, ldf: LDFFile) -> None:
        """Queue an LDF update for deferred delivery to the communication panel."""
        self._pending_ldf = ldf
        self._schedule_sync()

    def queue_selection(self, master: str, slaves: list[str]) -> None:
        """Queue a selection update for deferred delivery to the communication panel."""
        self._pending_selection = (master, list(slaves))
        self._schedule_sync()

    def _schedule_sync(self) -> None:
        """Coalesce cross-window updates onto the next GUI event-loop tick."""
        if not self._sync_timer.isActive():
            self._sync_timer.start(0)

    def _flush_pending_updates(self) -> None:
        """Apply any queued LDF and node-selection updates in a stable order."""
        if self._pending_ldf is not None:
            self._comm_panel.load_ldf(self._pending_ldf)
            self._pending_ldf = None
        if self._pending_selection is not None:
            master, slaves = self._pending_selection
            self._comm_panel.configure_selection(master, slaves)
            self._pending_selection = None

    def focus_primary_control(self) -> None:
        """Delegate focus to the communication panel's first control."""
        self.show()
        self.raise_()
        self._comm_panel.focus_primary_control()

    def _restore_geometry(self) -> None:
        """Restore window geometry from persistent settings."""
        geom = self._settings.value("comm_geometry")
        if geom:
            self.restoreGeometry(geom)

    def closeEvent(self, event) -> None:
        """Hide the window instead of destroying it for instant reopen."""
        self._settings.setValue("comm_geometry", self.saveGeometry())
        self._comm_panel.stop_csv_logging()
        event.ignore()
        self.hide()
