"""
Atomic features covered:
- Display Protected ID (PID) under node-related and diagnostic frame sections
- Show periodicity derived from all schedule tables under related/diagnostic frames
- Show Publisher and TX/RX direction at frame level only (not at signal level)
- Expose signal attributes (subscribers, initial value, size, encoding) without
  Publisher/Direction duplication under Nodes -> Slaves -> Related frames
- Include diagnostic frames in slave "Related frames" when the slave is involved
- Keep diagnostic frames in their dedicated "Diagnostic frames" section only
- Signal encoding and logical/physical details reachable under related/diagnostic frames
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from src.ldf_parser import parse_ldf_string
from src.gui.ldf_viewer import LDFViewer


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Provide a reusable QApplication for Qt widget tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Comprehensive LDF sample: master + 2 slaves, both subscriber and publisher
# frames, diagnostic frames, and multi-table schedule.
# ---------------------------------------------------------------------------

FULL_LDF = """
LIN_description_file ;
LIN_protocol_version = "2.1" ;
LIN_language_version = "2.1" ;
LIN_speed = 19.2 kbps ;
Channel_name = "CABIN" ;
Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S1, S2 ; }
Signals {
  S1: 8, 0, M, S1 ;
  S2: 8, 1, M, S2 ;
  S3: 16, 0, S1, M ;
}
Frames {
  F1 : 0x10, M, 2 { S1, 0 ; S2, 8 ; }
  F2 : 0x11, S1, 4 { S3, 0 ; }
  MasterReq : 0x3C, M, 8 { S1, 0 ; }
  SlaveResp : 0x3D, S1, 8 { S1, 0 ; }
}
Schedule_tables {
  Main { F1 delay 10 ms ; F2 delay 15 ms ; MasterReq delay 5 ms ; }
  Fast { F1 delay 5 ms ; }
}
Signal_encoding_types {
  EncS1 {
    logical_value, 0, "Idle" ;
    physical_value, 0, 100, 0.5, -40.0, "deg C" ;
  }
}
Signal_representation { EncS1: S1 ; }
Node_attributes {
  S1 { LIN_protocol = "2.1" ; configured_NAD = 0x01 ; initial_NAD = 0x01 ; }
}
"""


def _find_child(item, startswith: str):
    """Return the first child whose text starts with *startswith*, or None."""
    for i in range(item.childCount()):
        if item.child(i).text(0).startswith(startswith):
            return item.child(i)
    return None


def _children_texts(item) -> set[str]:
    """Return the set of direct child row texts for one tree item."""
    return {item.child(i).text(0) for i in range(item.childCount())}


# ---------------------------------------------------------------------------
# Protected ID / PID calculation
# ---------------------------------------------------------------------------


def test_lin_protected_id_known_values() -> None:
    """Verify PID computation against known LIN 2.x reference values."""
    # Frame 0x10 = 16 → P0=1, P1=0 → PID = 0x50
    assert LDFViewer._lin_protected_id(0x10) == 0x50
    # Frame 0x00 → P0=0, P1=1 → PID = 0x80
    assert LDFViewer._lin_protected_id(0x00) == 0x80
    # Frame 0x01 → P0=1, P1=1 → PID = 0xC1
    assert LDFViewer._lin_protected_id(0x01) == 0xC1


def test_no_top_level_generic_frames_section(qapp: QApplication) -> None:
    """Verify there is no redundant top-level non-diagnostic Frames section."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    assert _find_child(root, "Frames (") is None


def test_lin_protected_id_shown_in_slave_related_frames(qapp: QApplication) -> None:
    """Verify Protected ID appears for every frame in Nodes → Slaves."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    assert f1 is not None

    props = _children_texts(f1)
    assert "Protected ID (PID): 0x50 (80 decimal)" in props
    assert "Frame ID: 0x10 (16 decimal)" in props


def test_lin_protected_id_shown_in_diagnostic_frames(qapp: QApplication) -> None:
    """Verify Protected ID appears in the Diagnostic frames section."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    diag = _find_child(root, "Diagnostic frames")
    assert diag is not None

    mr = _find_child(diag, "MasterReq:")
    assert mr is not None
    props = _children_texts(mr)
    assert "Protected ID (PID): 0x3C (60 decimal)" in props
    assert "Frame ID: 0x3C (60 decimal)" in props


# ---------------------------------------------------------------------------
# Periodicity
# ---------------------------------------------------------------------------


def test_periodicity_shown_for_multi_table_frame(qapp: QApplication) -> None:
    """Related frame in multiple schedule tables shows all delays with table names."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    props = _children_texts(f1)

    # F1 appears in Main (10 ms) and Fast (5 ms)
    assert any("Periodicity" in p and "Main" in p and "10.0 ms" in p for p in props)
    assert any("Periodicity" in p and "Fast" in p and "5.0 ms" in p for p in props)


def test_periodicity_shown_in_slave_related_frames(qapp: QApplication) -> None:
    """Periodicity is visible for frames in the Nodes → Slaves section."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f2 = _find_child(rel, "F2:")
    assert f2 is not None
    props = _children_texts(f2)

    assert any("Periodicity" in p and "15.0 ms" in p and "Main" in p for p in props)


def test_periodicity_not_scheduled_for_slaved_resp_frame(qapp: QApplication) -> None:
    """A frame absent from all schedule tables shows 'not scheduled'."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    sr = _find_child(rel, "SlaveResp:")
    assert sr is not None
    props = _children_texts(sr)

    assert "Periodicity: not scheduled" in props


# ---------------------------------------------------------------------------
# Direction — frame level
# ---------------------------------------------------------------------------


def test_direction_rx_for_slave_subscribing_to_frame(qapp: QApplication) -> None:
    """Slave → Related frames → master-published frame shows RX direction."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    # F1 is published by M, so S1 is a subscriber → RX
    f1 = _find_child(rel, "F1:")
    props = _children_texts(f1)
    assert any("Direction" in p and "RX" in p for p in props)


def test_direction_tx_for_slave_publishing_frame(qapp: QApplication) -> None:
    """Slave → Related frames → slave-published frame shows TX direction."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    # F2 is published by S1 → TX for S1
    f2 = _find_child(rel, "F2:")
    assert f2 is not None
    props = _children_texts(f2)
    assert any("Direction" in p and "TX" in p for p in props)


# ---------------------------------------------------------------------------
# Publisher and Direction — frame level (not signal level)
# ---------------------------------------------------------------------------


def test_signal_shows_attributes_without_publisher_direction(qapp: QApplication) -> None:
    """Signals under slave show bit offset, size, subscribers but not Publisher/Direction.

    Publisher and Direction info is shown at the frame level to avoid redundancy,
    since all signals in a frame have the same publisher as the frame.
    """
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    s1_sig = _find_child(f1, "S1")
    assert s1_sig is not None

    props = _children_texts(s1_sig)
    # Signal should have these properties
    assert "Size: 8 bit" in props
    assert "Subscribers: S1" in props
    assert "Bit offset: 0" in props
    # But NOT Publisher or Direction (those are at frame level)
    assert not any("Publisher" in p for p in props), "Publisher should not appear at signal level"
    assert not any("Direction" in p for p in props), "Direction should not appear at signal level"


def test_frame_shows_publisher_and_direction_under_slave(qapp: QApplication) -> None:
    """Frame under slave shows Publisher and Direction (not duplicated at signal level)."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    assert f1 is not None

    props = _children_texts(f1)
    # Frame should have Publisher and Direction
    assert any("Publisher" in p for p in props), f"Frame should show Publisher. Got: {props}"
    assert any("Direction" in p and "RX" in p for p in props), (
        f"Frame should show RX direction. Got: {props}"
    )


# ---------------------------------------------------------------------------
# Full signal details under Related frames
# ---------------------------------------------------------------------------


def test_related_frames_expose_full_signal_attributes(qapp: QApplication) -> None:
    """Related frames must show all signal attributes, not just bit offset."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    s1_sig = _find_child(f1, "S1")
    assert s1_sig is not None, "Signal S1 must be directly under F1 in Related frames"

    props = _children_texts(s1_sig)
    assert "Bit offset: 0" in props
    assert "Size: 8 bit" in props
    assert "Initial value: 0" in props
    assert "Subscribers: S1" in props
    # Publisher and Direction are shown at frame level, not signal level
    assert not any("Publisher" in p for p in props), "Publisher should not appear at signal level"


def test_related_frames_expose_signal_encoding(qapp: QApplication) -> None:
    """Signal in Related frames must include the encoding subtree."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f1 = _find_child(rel, "F1:")
    s1_sig = _find_child(f1, "S1")

    enc = _find_child(s1_sig, "Encoding: EncS1")
    assert enc is not None
    enc_props = _children_texts(enc)
    assert "BCD: no" in enc_props
    assert "ASCII: no" in enc_props
    assert "Logical values count: 1" in enc_props
    assert "Physical ranges count: 1" in enc_props


# ---------------------------------------------------------------------------
# Diagnostic frames in slave related frames
# ---------------------------------------------------------------------------


def test_diagnostic_frames_included_in_slave_related_frames(qapp: QApplication) -> None:
    """Slave's Related frames must include diagnostic frames when involved."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")

    frame_names = {rel.child(i).text(0).split(":", 1)[0] for i in range(rel.childCount())}
    # S1 subscribes to MasterReq signals and publishes SlaveResp
    assert "MasterReq" in frame_names, "MasterReq (0x3C) must appear in S1 related frames"
    assert "SlaveResp" in frame_names, "SlaveResp (0x3D) must appear in S1 related frames"


def test_diagnostic_frames_not_duplicated_in_top_level_frames_section(qapp: QApplication) -> None:
    """No top-level generic Frames section is rendered, so diagnostics are never duplicated there."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    assert _find_child(root, "Frames (") is None


def test_diagnostic_frames_section_has_full_properties(qapp: QApplication) -> None:
    """Diagnostic frames section must show Frame ID, Protected ID, Publisher, Periodicity."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    diag = _find_child(root, "Diagnostic frames")
    mr = _find_child(diag, "MasterReq:")
    assert mr is not None

    props = _children_texts(mr)
    assert "Frame ID: 0x3C (60 decimal)" in props
    assert "Protected ID (PID): 0x3C (60 decimal)" in props
    assert "Publisher: M" in props
    assert any("Periodicity" in p for p in props)
