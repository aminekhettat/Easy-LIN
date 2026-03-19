"""
Atomic features covered:
- Build stable tree nodes for accessible navigation
- Generate plain-language descriptions for screen-reader output
- Provide signal, frame, schedule and encoding explanations
"""

from __future__ import annotations

from src.ldf_parser import parse_ldf_string
from src.ldf_presenter import build_tree_nodes, describe_encoding, describe_key


LDF_TEXT = """
LIN_description_file ;
LIN_protocol_version = "2.1" ;
LIN_language_version = "2.1" ;
LIN_speed = 19.2 kbps ;
Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
Signals {
  S1: 8, 0, M, S ;
}
Frames {
  F1 : 0x10, M, 1 { S1, 0 ; }
}
Schedule_tables {
  Main { F1 delay 10 ms ; }
}
Signal_encoding_types {
  Enc {
    logical_value, 0, "Idle" ;
  }
}
Signal_representation {
  Enc: S1 ;
}
"""


def test_build_tree_nodes_contains_expected_sections() -> None:
    ldf = parse_ldf_string(LDF_TEXT)
    nodes = build_tree_nodes(ldf)

    keys = {node.key for node in nodes}
    assert "header" in keys
    assert "signals" in keys
    assert "signal.S1" in keys
    assert "frame.F1" in keys
    assert "schedule.Main" in keys
    assert "encoding.Enc" in keys


def test_describe_key_signal_and_frame() -> None:
    ldf = parse_ldf_string(LDF_TEXT)

    signal_text = describe_key(ldf, "signal.S1")
    frame_text = describe_key(ldf, "frame.F1")

    assert "Signal S1" in signal_text
    assert "Publisher M" in signal_text
    assert "Frame F1" in frame_text
    assert "Identifier 0x10" in frame_text


def test_describe_key_schedule_and_header() -> None:
    ldf = parse_ldf_string(LDF_TEXT)

    schedule_text = describe_key(ldf, "schedule.Main")
    header_text = describe_key(ldf, "header")

    assert "Schedule table Main" in schedule_text
    assert "F1 after 10.0 milliseconds" in schedule_text
    assert "Protocol version 2.1" in header_text


def test_describe_key_missing_and_default_message() -> None:
    ldf = parse_ldf_string(LDF_TEXT)

    missing_signal = describe_key(ldf, "signal.Unknown")
    default_text = describe_key(ldf, "root")

    assert "was not found" in missing_signal
    assert "Select a frame" in default_text


def test_describe_key_missing_frame_and_encoding() -> None:
    ldf = parse_ldf_string(LDF_TEXT)

    missing_frame = describe_key(ldf, "frame.Unknown")
    missing_encoding = describe_key(ldf, "encoding.Unknown")
    missing_schedule = describe_key(ldf, "schedule.Unknown")

    assert "Frame Unknown was not found" in missing_frame
    assert "Encoding type Unknown was not found" in missing_encoding
    assert "Schedule table Unknown was not found" in missing_schedule


def test_describe_encoding_includes_flags() -> None:
    ldf = parse_ldf_string(
        """
        LIN_description_file ;
        Signal_encoding_types {
          E {
            logical_value, 1, "One" ;
            bcd_value ;
            ascii_value ;
          }
        }
        """
    )

    text = describe_encoding(ldf.encoding_types[0])
    assert "Encoding type E" in text
    assert "Logical value 1 means One" in text
    assert "BCD format is enabled" in text
    assert "ASCII format is enabled" in text


def test_build_tree_nodes_encoding_summary_includes_formats() -> None:
    ldf = parse_ldf_string(
        """
        LIN_description_file ;
        Signal_encoding_types {
          E {
            logical_value, 1, "One" ;
            physical_value, 0, 10, 1.0, 0.0, "u" ;
            bcd_value ;
            ascii_value ;
          }
        }
        """
    )

    nodes = build_tree_nodes(ldf)
    encoding_node = next(node for node in nodes if node.key == "encoding.E")
    assert "formats: BCD, ASCII" in encoding_node.value


def test_describe_key_encoding_with_physical_range() -> None:
    ldf = parse_ldf_string(
        """
        LIN_description_file ;
        Signal_encoding_types {
          TempEnc {
            physical_value, 0, 100, 0.5, -40.0, "deg C" ;
          }
        }
        """
    )

    text = describe_key(ldf, "encoding.TempEnc")
    assert "Encoding type TempEnc" in text
    assert "Physical range 0 to 100" in text


def test_describe_frame_without_mapped_signals() -> None:
    ldf = parse_ldf_string(
        """
        LIN_description_file ;
        Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
        Frames { F0 : 0x01, M, 1 { } }
        """
    )

    text = describe_key(ldf, "frame.F0")
    assert "No signals are mapped" in text
