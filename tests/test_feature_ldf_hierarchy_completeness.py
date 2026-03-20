"""
Atomic features covered:
- Display Protected ID (PID) with parity bits for every frame section
- Show periodicity derived from all schedule tables under each frame
- Show TX/RX direction at frame level relative to the viewing node
- Show TX/RX direction at signal level relative to the viewing node
- Expose full signal attributes (publisher, subscribers, initial value, encoding)
  in EVERY frame section, not only in the Nodes section
- Include diagnostic frames in slave "Related frames" when the slave is involved
- Exclude diagnostic frames from the generic "Frames (N)" section
  (they have their own dedicated "Diagnostic frames" section)
- Master "Published frames" exposes Frame ID, Protected ID, direction, periodicity
- Signal encoding and logical/physical details reachable under every frame section
"""

from __future__ import annotations

import os

import pytest
from PyQt5.QtWidgets import QApplication

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


def test_lin_protected_id_shown_in_frames_section(qapp: QApplication) -> None:
    """Verify Protected ID appears in the non-diagnostic Frames section."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)

    frames_section = _find_child(root, "Frames (")
    assert frames_section is not None

    f1 = _find_child(frames_section, "F1")
    assert f1 is not None
    props = _children_texts(f1)

    assert "Frame ID: 0x10 (16 decimal)" in props
    assert "Protected ID (PID): 0x50 (80 decimal)" in props


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


def test_lin_protected_id_shown_in_master_published_frames(qapp: QApplication) -> None:
    """Verify Protected ID appears under Master → Published frames."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    master = _find_child(nodes, "Master:")
    pub = _find_child(master, "Published frames")
    f1 = _find_child(pub, "F1:")
    assert f1 is not None

    props = _children_texts(f1)
    assert "Protected ID (PID): 0x50 (80 decimal)" in props


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
    """Frame in multiple schedule tables shows all delays with table names."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    frames_section = _find_child(root, "Frames (")
    f1 = _find_child(frames_section, "F1")
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


def test_direction_tx_for_master_published_frame(qapp: QApplication) -> None:
    """Master → Published frames → frame shows Master TX direction."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    master = _find_child(nodes, "Master:")
    pub = _find_child(master, "Published frames")
    f1 = _find_child(pub, "F1:")
    props = _children_texts(f1)
    assert any("Direction" in p and "TX" in p and "Master" in p for p in props)


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
# Direction — signal level
# ---------------------------------------------------------------------------


def test_signal_direction_rx_when_slave_is_subscriber(qapp: QApplication) -> None:
    """Signal under slave shows RX when the slave is a subscriber."""
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
    assert any("Direction" in p and "RX" in p for p in props)
    assert "Publisher: M" in props
    assert "Subscribers: S1" in props
    assert "Size: 8 bit" in props


def test_signal_direction_tx_when_slave_is_publisher(qapp: QApplication) -> None:
    """Signal under slave shows TX when the slave is the publisher."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    slaves = _find_child(nodes, "Slaves")
    s1 = _find_child(slaves, "S1")
    rel = _find_child(s1, "Related frames")
    f2 = _find_child(rel, "F2:")
    s3_sig = _find_child(f2, "S3")
    assert s3_sig is not None

    props = _children_texts(s3_sig)
    assert any("Direction" in p and "TX" in p for p in props)
    assert "Publisher: S1" in props
    assert "Size: 16 bit" in props


# ---------------------------------------------------------------------------
# Full signal details in the generic Frames section
# ---------------------------------------------------------------------------


def test_frames_section_exposes_full_signal_attributes(qapp: QApplication) -> None:
    """Non-diagnostic Frames section must show all signal attributes, not just bit offset."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    frames_section = _find_child(root, "Frames (")
    f1 = _find_child(frames_section, "F1")
    s1_sig = _find_child(f1, "S1")
    assert s1_sig is not None, "Signal S1 must be directly under F1 in the Frames section"

    props = _children_texts(s1_sig)
    assert "Bit offset: 0" in props
    assert "Size: 8 bit" in props
    assert "Initial value: 0" in props
    assert "Publisher: M" in props
    assert "Subscribers: S1" in props


def test_frames_section_exposes_signal_encoding(qapp: QApplication) -> None:
    """Signal in Frames section must include the encoding subtree."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    frames_section = _find_child(root, "Frames (")
    f1 = _find_child(frames_section, "F1")
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


def test_diagnostic_frames_excluded_from_generic_frames_section(qapp: QApplication) -> None:
    """The generic Frames section must NOT list diagnostic frames (they have their own section)."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    frames_section = _find_child(root, "Frames (")
    assert frames_section is not None

    frame_names = {
        frames_section.child(i).text(0).split(":", 1)[0] for i in range(frames_section.childCount())
    }
    assert "MasterReq" not in frame_names
    assert "SlaveResp" not in frame_names


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


# ---------------------------------------------------------------------------
# Master Published frames — full properties
# ---------------------------------------------------------------------------


def test_master_published_frames_have_full_frame_properties(qapp: QApplication) -> None:
    """Master → Published frames must show Frame ID, Protected ID, Publisher, Periodicity."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    master = _find_child(nodes, "Master:")
    assert master is not None
    pub = _find_child(master, "Published frames")
    assert pub is not None

    f1 = _find_child(pub, "F1:")
    assert f1 is not None
    props = _children_texts(f1)

    assert "Frame ID: 0x10 (16 decimal)" in props
    assert "Protected ID (PID): 0x50 (80 decimal)" in props
    assert "Publisher: M" in props
    assert any("Periodicity" in p for p in props)
    assert any("Direction" in p for p in props)


def test_master_published_frames_have_full_signal_details(qapp: QApplication) -> None:
    """Signals under Master → Published frames show all attributes including encoding."""
    ldf = parse_ldf_string(FULL_LDF)
    viewer = LDFViewer(ldf)
    root = viewer._tree.topLevelItem(0)
    nodes = _find_child(root, "Nodes")
    master = _find_child(nodes, "Master:")
    pub = _find_child(master, "Published frames")
    f1 = _find_child(pub, "F1:")
    s1_sig = _find_child(f1, "S1")
    assert s1_sig is not None

    props = _children_texts(s1_sig)
    assert "Bit offset: 0" in props
    assert "Size: 8 bit" in props
    assert "Initial value: 0" in props
    assert "Publisher: M" in props
    # Direction: S1 subscriber, context=master "M" → master is the publisher
    assert any("Direction" in p and "TX" in p for p in props)
