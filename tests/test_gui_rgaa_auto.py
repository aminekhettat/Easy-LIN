"""Tests for src/gui/rgaa_auto.py.

Covers:
- RGAAAutoComplianceReport: percentage with total=0, with normal values
- evaluate_main_window_automatic_rgaa:
  - With comm_window (new architecture) vs comm_panel (legacy fallback)
  - With missing tree (no LDF loaded)
  - With missing comm panel
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.gui.rgaa_auto import RGAAAutoComplianceReport, evaluate_main_window_automatic_rgaa


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# RGAAAutoComplianceReport tests
# ---------------------------------------------------------------------------

class TestRGAAAutoComplianceReport:
    def test_percentage_zero_total(self):
        report = RGAAAutoComplianceReport(passed=0, total=0)
        assert report.percentage == 0.0

    def test_percentage_normal(self):
        report = RGAAAutoComplianceReport(passed=8, total=10)
        assert report.percentage == pytest.approx(80.0)

    def test_percentage_all_passed(self):
        report = RGAAAutoComplianceReport(passed=15, total=15)
        assert report.percentage == pytest.approx(100.0)

    def test_percentage_none_passed(self):
        report = RGAAAutoComplianceReport(passed=0, total=5)
        assert report.percentage == pytest.approx(0.0)

    def test_frozen(self):
        report = RGAAAutoComplianceReport(passed=3, total=5)
        with pytest.raises(AttributeError):
            report.passed = 10


# ---------------------------------------------------------------------------
# evaluate_main_window_automatic_rgaa tests
# ---------------------------------------------------------------------------

@pytest.fixture
def main_window_with_ldf(qapp):
    """Create a MainWindow with a loaded LDF for full RGAA evaluation."""
    with patch("src.gui.communication_panel.LINMaster") as MockMaster:
        master_inst = MagicMock()
        master_inst.is_connected = False
        MockMaster.return_value = master_inst
        MockMaster.list_lin_channels = MagicMock(return_value=[])

        from src.gui.main_window_qt import MainWindow
        win = MainWindow()

        # Load an LDF to populate the viewer and comm panel
        from src.ldf_parser import parse_ldf_string
        ldf_text = """
        LIN_description_file ;
        LIN_protocol_version = "2.1" ;
        LIN_language_version = "2.1" ;
        LIN_speed = 19.2 kbps ;
        Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S1 ; }
        Signals { S1: 8, 0, M, S1 ; }
        Frames { F1 : 0x10, M, 2 { S1, 0 ; } }
        Schedule_tables { Main { F1 delay 10 ms ; } }
        """
        ldf = parse_ldf_string(ldf_text)

        from src.gui.ldf_viewer import LDFViewer
        viewer = LDFViewer(ldf)
        win.setCentralWidget(viewer)
        win._comm_window.load_ldf(ldf)

        yield win


class TestEvaluateWithCommWindow:
    def test_report_with_loaded_ldf(self, main_window_with_ldf):
        report = evaluate_main_window_automatic_rgaa(main_window_with_ldf)
        assert report.total > 0
        assert report.passed > 0
        assert 0 <= report.percentage <= 100


class TestEvaluateWithLegacyFallback:
    def test_report_with_comm_panel_fallback(self, qapp):
        """When _comm_window is absent, fall back to _comm_panel."""
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.main_window_qt import MainWindow
            win = MainWindow()

            # Remove comm_window and add comm_panel directly.
            # Keep a reference to comm_window so that Qt's parent-child
            # mechanism does not destroy the comm_panel C++ object.
            comm_window_ref = win._comm_window
            comm_panel = comm_window_ref._comm_panel
            del win._comm_window
            win._comm_panel = comm_panel

            report = evaluate_main_window_automatic_rgaa(win)
            assert report.total > 0


class TestEvaluateWithMissingTree:
    def test_report_no_ldf_loaded(self, qapp):
        """When no LDF is loaded, tree checks should fail gracefully."""
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.main_window_qt import MainWindow
            win = MainWindow()
            report = evaluate_main_window_automatic_rgaa(win)
            assert report.total > 0
            # Tree checks should fail since no LDF is loaded
            # but the function should still return a valid report


class TestEvaluateWithMissingCommPanel:
    def test_report_no_comm_panel(self, qapp):
        """When neither comm_window nor comm_panel exists."""
        with patch("src.gui.communication_panel.LINMaster") as MockMaster:
            master_inst = MagicMock()
            master_inst.is_connected = False
            MockMaster.return_value = master_inst
            MockMaster.list_lin_channels = MagicMock(return_value=[])

            from src.gui.main_window_qt import MainWindow
            win = MainWindow()

            # Remove both comm_window and _comm_panel
            saved = win._comm_window
            del win._comm_window
            # Ensure _comm_panel is also absent
            if hasattr(win, "_comm_panel"):
                del win._comm_panel

            report = evaluate_main_window_automatic_rgaa(win)
            assert report.total > 0
            # comm label checks should fail but not crash

            # Restore to avoid issues in cleanup
            win._comm_window = saved
