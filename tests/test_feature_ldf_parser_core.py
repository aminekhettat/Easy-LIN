"""
Atomic features covered:
- Parse full LDF content including nodes, signals, frames and schedules
- Parse encoding definitions, node attributes and lookup helpers
- Parse from file and string with comment stripping and number formats
- Handle unsupported/optional sections and parse failures safely
"""

from __future__ import annotations

import pytest

from src.ldf_parser import LDFParseError, parse_ldf, parse_ldf_string


SAMPLE_LDF = """
LIN_description_file ;
LIN_protocol_version = "2.1" ;
LIN_language_version = "2.1" ;
LIN_speed = 19.2 kbps ;
Channel_name = "CABIN" ;

Nodes {
  Master: BodyControl, 5 ms, 0.1 ms ;
  Slaves: DoorLeft, DoorRight ;
}

Signals {
  DoorLeftCmd: 2, 0, BodyControl, DoorLeft ;
  DoorRightCmd: 2, 0, BodyControl, DoorRight ;
  DoorLeftPos: 8, 0, DoorLeft, BodyControl ;
  DoorRightPos: 8, 0, DoorRight, BodyControl ;
  Temp: 8, 0x0A, DoorLeft, BodyControl ;
}

Frames {
  DoorCmd : 0x10, BodyControl, 2 {
    DoorLeftCmd, 0 ;
    DoorRightCmd, 2 ;
  }
  DoorStatus : 0x11, DoorLeft, 2 {
    DoorLeftPos, 0 ;
    DoorRightPos, 8 ;
  }
  Climate : 18, DoorLeft, 1 {
    Temp, 0 ;
  }
}

Sporadic_frames {
  Ignored: 0x20 ;
}

Event_triggered_frames {
  Ignored: 0x21 ;
}

Schedule_tables {
  MainSchedule {
    DoorCmd delay 10 ms ;
    DoorStatus delay 10 ms ;
    Climate delay 20 ms ;
  }
}

Signal_groups {
  IgnoreMe { DoorLeftCmd, DoorRightCmd ; }
}

Signal_encoding_types {
  DoorCmdEncoding {
    logical_value, 0, "Idle" ;
    logical_value, 1, "Open" ;
    logical_value, 2, "Close" ;
  }
  TempEncoding {
    physical_value, 0, 255, 1.0, -40.0, "deg C" ;
  }
}

Signal_representation {
  DoorCmdEncoding: DoorLeftCmd, DoorRightCmd ;
  TempEncoding: Temp ;
}

Node_attributes {
  DoorLeft {
    LIN_protocol = "2.1" ;
    configured_NAD = 0x01 ;
    initial_NAD = 0x01 ;
    product_id = 0x1000, 0x0001, 0x01 ;
    response_error = DoorLeftPos ;
    P2_min = 50 ms ;
    ST_min = 0 ms ;
    N_As_timeout = 1000 ms ;
    N_Cr_timeout = 1000 ms ;
    configurable_frames {
      DoorCmd ;
      DoorStatus ;
    }
  }
}

Node_composition { Ignore { X ; } }
Composite { Ignore { X ; } }
"""


def test_parse_string_populates_all_sections() -> None:
    """Ensure parsing from a string populates all supported LDF sections."""
    ldf = parse_ldf_string(SAMPLE_LDF)

    assert ldf.protocol_version == "2.1"
    assert ldf.language_version == "2.1"
    assert ldf.speed == pytest.approx(19.2)
    assert ldf.channel_name == "CABIN"

    assert ldf.nodes is not None
    assert ldf.nodes.master.name == "BodyControl"
    assert ldf.nodes.slaves == ["DoorLeft", "DoorRight"]

    assert len(ldf.signals) == 5
    assert ldf.signal("DoorLeftCmd") is not None
    assert ldf.signal("Missing") is None

    assert len(ldf.frames) == 3
    assert ldf.frame_by_name("DoorCmd") is not None
    assert ldf.frame_by_id(0x10) is not None
    assert ldf.frame_by_id(18).name == "Climate"

    assert len(ldf.schedule_tables) == 1
    assert ldf.schedule_tables[0].entries[0].delay == pytest.approx(10.0)

    assert len(ldf.encoding_types) == 2
    assert ldf.encoding_types[0].logical_values[1].text == "Open"
    assert ldf.encoding_types[1].physical_ranges[0].offset == pytest.approx(-40.0)

    assert len(ldf.signal_representations) == 2
    assert "Temp" in ldf.signal_representations[1].signals

    assert len(ldf.node_attributes) == 1
    assert ldf.node_attributes[0].configured_nad == 0x01


def test_parse_file_roundtrip(tmp_path) -> None:
    """Ensure parsing from a file path preserves the expected frame data."""
    path = tmp_path / "network.ldf"
    path.write_text(SAMPLE_LDF, encoding="utf-8")

    ldf = parse_ldf(str(path))

    assert ldf.protocol_version == "2.1"
    assert ldf.frame_by_name("DoorStatus").frame_size == 2


def test_parser_handles_comments_and_negative_values() -> None:
    """Ensure comments and signed numeric encoding fields are accepted."""
    content = """
    LIN_description_file ; // top level
    /* block comment */
    LIN_protocol_version = "2.0" ;
    LIN_language_version = "2.0" ;
    LIN_speed = 9.6 kbps ;
    Signal_encoding_types {
      T {
        physical_value, 0, 100, 0.5, -1.5, "u" ;
        bcd_value ;
        ascii_value ;
      }
    }
    """
    ldf = parse_ldf_string(content)

    assert ldf.protocol_version == "2.0"
    assert ldf.encoding_types[0].physical_ranges[0].offset == pytest.approx(-1.5)
    assert ldf.encoding_types[0].bcd is True
    assert ldf.encoding_types[0].ascii is True


def test_parser_handles_unknown_tokens_without_crash() -> None:
    """Ensure unknown sections do not crash the tolerant parser."""
    content = """
    LIN_description_file ;
    LIN_protocol_version = "2.0" ;
    UnknownSection { A B C ; }
    """
    ldf = parse_ldf_string(content)
    assert ldf.protocol_version == "2.0"


def test_parser_raises_ldf_parse_error_for_invalid_syntax() -> None:
    """Ensure invalid syntax is wrapped in an explicit parse error."""
    broken = "LIN_protocol_version = 2.0 ; Nodes { Master: A, 5 ms ; }"
    with pytest.raises(LDFParseError):
        parse_ldf_string(broken)


def test_parser_supports_negative_and_float_numbers() -> None:
    """Ensure tolerant numeric parsing handles signed and float-like tokens."""
    content = """
    LIN_description_file ;
    Signals {
      S1: 8, 1, M, S ;
      S2: 8, 16.0, M, S ;
      S3: 8, { 0x00, 0x00 }, M, S ;
    }
    Frames {
      F1: -1, M, 1 { S1, 0 ; }
    }
    Schedule_tables {
      Main { AssignNAD { X ; } delay 5 ms ; }
    }
    Signal_encoding_types {
      E {
        unsupported, field ;
      }
    }
    Node_attributes {
      N {
        unknown_field = 1 ;
        configurable_frames { ; F1 ; }
      }
    }
    """
    ldf = parse_ldf_string(content)

    assert ldf.signals[0].init_value == 1
    assert ldf.signals[1].init_value == 16
    assert ldf.signals[2].init_value == 0
    assert ldf.frames[0].frame_id == -1
    assert ldf.schedule_tables[0].entries[0].frame_name == "AssignNAD"


def test_parser_wraps_unexpected_errors() -> None:
    """Ensure unexpected parser failures are surfaced as parse errors."""
    with pytest.raises(LDFParseError):
        parse_ldf_string(None)  # type: ignore[arg-type]


def test_parser_invalid_identifier_raises() -> None:
    """Ensure invalid identifiers are rejected."""
    content = """
    LIN_description_file ;
    Signals {
      1Sig: 8, 0, M, S ;
    }
    """
    with pytest.raises(LDFParseError):
        parse_ldf_string(content)


def test_parser_accepts_physical_value_without_unit() -> None:
    """Ensure physical value entries remain valid when the unit is omitted."""
    content = """
    LIN_description_file ;
    Signal_encoding_types {
      E {
        physical_value, 0, 14, 1, 0 ;
        logical_value, 15, "Invalid" ;
      }
    }
    """
    ldf = parse_ldf_string(content)

    assert len(ldf.encoding_types) == 1
    assert ldf.encoding_types[0].physical_ranges[0].unit == ""


def test_parser_skips_diagnostic_frames_sections() -> None:
    """Ensure diagnostic frame sections are ignored by the main frame parser."""
    content = """
    LIN_description_file ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
    Signals { A: 8, 0, M, S ; }
    Frames {
      F1: 0x10, M, 1 { A, 0 ; }
      Diagnostic_frames {
        MasterReq: 0x3C { A, 0 ; }
      }
    }
    Diagnostic_frames {
      MasterReq: 0x3C { A, 0 ; }
    }
    """
    ldf = parse_ldf_string(content)

    assert len(ldf.frames) == 1
    assert ldf.frames[0].name == "F1"


def test_parser_accepts_redundant_nested_frame_header() -> None:
    """Ensure nested repeated frame headers are tolerated."""
    content = """
    LIN_description_file ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
    Signals {
      S1: 8, 0, M, S ;
      S2: 8, 0, M, S ;
    }
    Frames {
      Outer: 0x20, M, 2 {
        Outer: 0x20, M, 2 {
          S1, 0 ;
          S2, 8 ;
        }
      }
    }
    """
    ldf = parse_ldf_string(content)

    frame = ldf.frame_by_name("Outer")
    assert frame is not None
    assert len(frame.signals) == 2


def test_parser_accepts_frames_followed_by_section_without_closing_brace() -> None:
    """Ensure the parser tolerates a missing closing brace before the next section."""
    content = """
    LIN_description_file ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
    Signals { A: 8, 0, M, S ; }
    Frames {
      F1: 0x10, M, 1 { A, 0 ; }
      Node_attributes {
        S {
          LIN_protocol = "2.1" ;
        }
      }
    """
    ldf = parse_ldf_string(content)

    assert ldf.frame_by_name("F1") is not None
    assert len(ldf.node_attributes) == 1
    assert ldf.node_attributes[0].node_name == "S"
