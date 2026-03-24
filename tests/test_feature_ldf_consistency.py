"""
Atomic features covered:
- Detect core LDF consistency errors for nodes/signals/frames/schedules
- Detect encoding, representation, and node-attribute integrity problems
- Parse-level validation and workspace-level report generation
"""

from __future__ import annotations

from src.ldf_consistency import (
    ConsistencyIssue,
    LDFConsistencyReport,
    format_report,
    validate_ldf,
    validate_ldf_file,
    validate_workspace_ldf_files,
)
from src.ldf_parser import (
    LDFEncodingType,
    LDFFile,
    LDFFrame,
    LDFFrameSignal,
    LDFMaster,
    LDFNodeAttributes,
    LDFNodes,
    LDFScheduleEntry,
    LDFScheduleTable,
    LDFSignal,
    parse_ldf_string,
)


def _codes(issues):
    """Return the issue codes from a consistency issue collection."""
    return {item.code for item in issues}


def test_validate_ldf_detects_structural_errors() -> None:
    """Ensure structural node, signal, frame, and schedule errors are detected."""
    content = """
    LIN_description_file ;
    LIN_speed = 25 kbps ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: M, S, S ; }
    Signals {
      A: 8, 300, M, UnknownNode ;
      A: 8, 0, M, S ;
    }
    Frames {
      F: 64, UnknownPub, 9 {
        UnknownSig, 0 ;
        A, 80 ;
      }
      F: 64, M, 1 { A, 0 ; A, 0 ; }
    }
    Schedule_tables {
      T { MissingFrame delay 7 ms ; }
    }
    """
    ldf = parse_ldf_string(content)
    issues = validate_ldf(ldf)
    codes = _codes(issues)

    assert "GLOBAL_SPEED_RANGE" in codes
    assert "NODE_DUP_MASTER" in codes
    assert "NODE_DUP_SLAVE" in codes
    assert "SIGNAL_DUP_NAME" in codes
    assert "SIGNAL_INIT_RANGE" in codes
    assert "SIGNAL_SUBSCRIBER_UNKNOWN" in codes
    assert "FRAME_ID_RANGE" in codes
    assert "FRAME_SIZE_RANGE" in codes
    assert "FRAME_PUBLISHER_UNKNOWN" in codes
    assert "FRAME_SIGNAL_UNKNOWN" in codes
    assert "FRAME_SIGNAL_FIT" in codes
    assert "FRAME_DUP_NAME" in codes
    assert "FRAME_ID_DUP" in codes
    assert "SCHEDULE_FRAME_UNKNOWN" in codes
    assert "SCHEDULE_DELAY_MULTIPLE" in codes


def test_validate_ldf_detects_encoding_representation_node_attr_issues() -> None:
    """Ensure encoding, representation, and node-attribute errors are detected."""
    content = """
    LIN_description_file ;
    LIN_protocol_version = "2.1" ;
    LIN_language_version = "2.1" ;
    LIN_speed = 19.2 kbps ;
    Nodes { Master: M, 10 ms, 0.1 ms ; Slaves: S1 ; }
    Signals {
      Sig1: 8, 0, M, S1 ;
      Unused: 4, 0, M, S1 ;
    }
    Frames {
      MasterReq: 60, M, 6 { Sig1, 0 ; }
      SlaveResp: 61, M, 8 { Sig1, 0 ; }
    }
    Schedule_tables {
      Main { FreeFormat { X ; } delay 10 ms ; }
    }
    Signal_encoding_types {
      EncA {
        logical_value, 1, "One" ;
        logical_value, 1, "Again" ;
        physical_value, 5, 4, 0, 0, "u" ;
      }
      EncA {
        logical_value, 2, "Two" ;
      }
    }
    Signal_representation {
      MissingEnc: Sig1 ;
      EncA: Sig1 ;
      EncA: MissingSig ;
    }
    Node_attributes {
      M {
        configured_NAD = 200 ;
        initial_NAD = -1 ;
        response_error = MissingSignal ;
        configurable_frames {
          MissingFrame ;
        }
      }
      Unknown {
        LIN_protocol = "2.1" ;
      }
    }
    """
    ldf = parse_ldf_string(content)
    issues = validate_ldf(ldf)
    codes = _codes(issues)

    assert "FRAME_DIAG_SIZE" in codes
    assert "SIGNAL_UNUSED" in codes
    assert "ENCODING_DUP_NAME" in codes
    assert "ENCODING_LOGICAL_DUP" in codes
    assert "ENCODING_RANGE_ORDER" in codes
    assert "ENCODING_SCALE_ZERO" in codes
    assert "REPRESENTATION_ENCODING_UNKNOWN" in codes
    assert "REPRESENTATION_SIGNAL_UNKNOWN" in codes
    assert "REPRESENTATION_SIGNAL_DUP" in codes
    assert "NODE_ATTR_NOT_SLAVE" in codes
    assert "NODE_ATTR_NAD_RANGE" in codes
    assert "NODE_ATTR_RESPONSE_ERROR_UNKNOWN" in codes
    assert "NODE_ATTR_CONFIG_FRAME_UNKNOWN" in codes
    assert "NODE_ATTR_UNKNOWN_NODE" in codes


def test_validate_ldf_file_parse_error_and_file_missing(tmp_path) -> None:
    """Ensure file-level validation reports parse failures and missing files."""
    broken = tmp_path / "broken.ldf"
    broken.write_text("LIN_description_file ; Frames { F :", encoding="utf-8")

    parse_report = validate_ldf_file(str(broken))
    assert parse_report.parsed is False
    assert parse_report.error_count == 1
    assert parse_report.issues[0].code == "PARSE_ERROR"

    missing_report = validate_ldf_file(str(tmp_path / "missing.ldf"))
    assert missing_report.parsed is False
    assert missing_report.error_count == 1
    assert missing_report.issues[0].code == "FILE_NOT_FOUND"


def test_format_report_text_variants() -> None:
    """Ensure a clean report is rendered as consistent text."""
    content = """
    LIN_description_file ;
    LIN_protocol_version = "2.1" ;
    LIN_language_version = "2.1" ;
    LIN_speed = 19.2 kbps ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
    Signals { A: 8, 0, M, S ; }
    Frames { F: 10, M, 1 { A, 0 ; } }
    Schedule_tables { T { F delay 5 ms ; } }
    """
    report_clean = validate_ldf_file(_write_temp(content))
    text_clean = format_report(report_clean)
    assert "CONSISTENT" in text_clean


def _write_temp(content: str) -> str:
    """Write temporary LDF content and return its file path."""
    import os
    import tempfile
    from pathlib import Path

    fd, name = tempfile.mkstemp(suffix=".ldf")
    os.close(fd)
    Path(name).write_text(content, encoding="utf-8")
    return name


def test_validate_workspace_ldf_files_collects_all(tmp_path) -> None:
    """Ensure workspace validation returns reports for every discovered file."""
    good = tmp_path / "a.ldf"
    bad = tmp_path / "nested" / "b.ldf"
    bad.parent.mkdir(parents=True, exist_ok=True)

    good.write_text(
        """
        LIN_description_file ;
        LIN_speed = 19.2 kbps ;
        Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
        Signals { A: 8, 0, M, S ; }
        Frames { F: 10, M, 1 { A, 0 ; } }
        """,
        encoding="utf-8",
    )
    bad.write_text("LIN_description_file ; Frames {", encoding="utf-8")

    reports = validate_workspace_ldf_files(str(tmp_path))
    assert [r.path for r in reports] == ["a.ldf", "nested/b.ldf"]
    assert reports[0].parsed is True
    assert reports[1].parsed is True
    assert reports[1].error_count > 0


def test_validate_ldf_manual_object_branches() -> None:
    """Exercise validation branches using a manually constructed LDF object."""
    ldf = LDFFile(
        protocol_version="",
        language_version="",
        speed=19.2,
        nodes=LDFNodes(master=LDFMaster(name="", time_base=5.0, jitter=0.1), slaves=["S"]),
        signals=[
            LDFSignal(name="S0", size=0, init_value=-1, publisher="Unknown", subscribers=["S"]),
            LDFSignal(name="S1", size=8, init_value=0, publisher="S", subscribers=[]),
        ],
        frames=[
            LDFFrame(
                name="F",
                frame_id=63,
                publisher="Unknown",
                frame_size=1,
                signals=[LDFFrameSignal("S0", -1), LDFFrameSignal("S1", 0)],
            )
        ],
        schedule_tables=[
            LDFScheduleTable(name="T", entries=[LDFScheduleEntry(frame_name="F", delay=0)])
        ],
        encoding_types=[LDFEncodingType(name="E")],
        signal_representations=[],
        node_attributes=[
            LDFNodeAttributes(node_name="S"),
            LDFNodeAttributes(node_name="S"),
            LDFNodeAttributes(
                node_name="S",
                configurable_frames=["=", "0x12", "12", "MissingFrame"],
            ),
        ],
    )

    issues = validate_ldf(ldf)
    codes = _codes(issues)
    assert "GLOBAL_PROTOCOL_MISSING" in codes
    assert "GLOBAL_LANGUAGE_MISSING" in codes
    assert "MASTER_MISSING" in codes
    assert "SIGNAL_SIZE_RANGE" in codes
    assert "SIGNAL_INIT_NEGATIVE" in codes
    assert "SIGNAL_PUBLISHER_UNKNOWN" in codes
    assert "FRAME_ID_RESERVED" in codes
    assert "FRAME_PUBLISHER_UNKNOWN" in codes
    assert "FRAME_SIGNAL_OFFSET_NEGATIVE" in codes
    assert "SCHEDULE_DELAY_POSITIVE" in codes
    assert "NODE_ATTR_DUP" in codes
    assert "NODE_ATTR_CONFIG_FRAME_UNKNOWN" in codes


def test_format_report_parse_failed_and_inconsistent_variants() -> None:
    """Ensure parse-failed and inconsistent report variants are rendered."""
    report_parse_failed = validate_ldf_file("this/path/does/not/exist.ldf")
    text_parse_failed = format_report(report_parse_failed)
    assert "PARSE FAILED" in text_parse_failed

    inconsistent = parse_ldf_string("LIN_description_file ;")
    issues = validate_ldf(inconsistent)
    fake_report = type(report_parse_failed)(path="in-memory", parsed=True, issues=issues)
    text_inconsistent = format_report(fake_report)
    assert "INCONSISTENT" in text_inconsistent


def test_format_report_warning_variant_and_is_consistent_property() -> None:
    """Ensure warning-only reports stay consistent while errors do not."""
    report_warning = LDFConsistencyReport(
        path="warn.ldf",
        parsed=True,
        issues=[ConsistencyIssue("warning", "W1", "warning only")],
    )
    assert report_warning.is_consistent is True
    assert "CONSISTENT WITH WARNINGS" in format_report(report_warning)

    report_error = LDFConsistencyReport(
        path="err.ldf",
        parsed=True,
        issues=[ConsistencyIssue("error", "E1", "error")],
    )
    assert report_error.is_consistent is False


def test_validate_ldf_duplicate_schedule_tables() -> None:
    """Ensure duplicate schedule table names are reported."""
    content = """
    LIN_description_file ;
    LIN_speed = 19.2 kbps ;
    Nodes { Master: M, 5 ms, 0.1 ms ; Slaves: S ; }
    Signals { A: 8, 0, M, S ; }
    Frames { F: 10, M, 1 { A, 0 ; } }
    Schedule_tables {
      T { F delay 5 ms ; }
      T { F delay 5 ms ; }
    }
    """
    issues = validate_ldf(parse_ldf_string(content))
    assert "SCHEDULE_DUP_NAME" in _codes(issues)
