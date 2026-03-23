"""
Atomic features covered:
- Evaluate deterministic RGAA-equivalent automatic checks for Qt main window
- Enforce keyboard shortcut accessibility constraints for major regions
- Enforce explicit accessible names on actionable communication controls
- Enforce textual status semantics so information is not color-only
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from src.ldf_parser import parse_ldf_string
from src.gui.ldf_viewer import LDFViewer
from src.gui.main_window_qt import MainWindow
from src.gui.rgaa_auto import evaluate_main_window_automatic_rgaa


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
    """Return a compact LDF sample to initialize the hierarchy tree."""
    return """
    LIN_description_file ;
    LIN_protocol_version = "2.1" ;
    LIN_language_version = "2.1" ;
    LIN_speed = 19.2 kbps ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S1 ; }
    Signals { S1: 8, 0, M, S1 ; }
    Frames { F1 : 0x10, M, 1 { S1, 0 ; } }
    Schedule_tables { Main { F1 delay 10 ms ; } }
    """


def test_rgaa_automatic_compliance_is_fully_met(
    qapp: QApplication,
    sample_ldf_text: str,
) -> None:
    """Ensure all implemented automatic RGAA-equivalent checks pass."""
    ldf = parse_ldf_string(sample_ldf_text)

    window = MainWindow()
    window.show()
    window.setCentralWidget(LDFViewer(ldf))
    qapp.processEvents()

    report = evaluate_main_window_automatic_rgaa(window)

    assert report.total > 0
    assert report.passed == report.total
    assert report.percentage == 100.0
