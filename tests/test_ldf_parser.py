"""
Unit tests for the LDF parser.

All tests use the sample fixture located at tests/fixtures/sample.ldf
and cover every major section of the LDF format.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.ldf.parser import LDFParser, LDFFile

FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'sample.ldf'


@pytest.fixture(scope='module')
def ldf() -> LDFFile:
    return LDFParser().parse_file(FIXTURE_PATH)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

class TestHeader:
    def test_protocol_version(self, ldf: LDFFile) -> None:
        assert ldf.protocol_version == '2.1'

    def test_language_version(self, ldf: LDFFile) -> None:
        assert ldf.language_version == '2.1'

    def test_speed(self, ldf: LDFFile) -> None:
        assert ldf.speed_kbps == pytest.approx(19.2)

    def test_channel_name(self, ldf: LDFFile) -> None:
        assert ldf.channel_name == 'LIN_1'

    def test_source_path(self, ldf: LDFFile) -> None:
        assert 'sample.ldf' in ldf.source_path


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

class TestNodes:
    def test_master_present(self, ldf: LDFFile) -> None:
        assert ldf.master is not None

    def test_master_name(self, ldf: LDFFile) -> None:
        assert ldf.master.name == 'BCM'

    def test_master_flag(self, ldf: LDFFile) -> None:
        assert ldf.master.is_master is True

    def test_master_timebase(self, ldf: LDFFile) -> None:
        assert ldf.master.timebase_ms == pytest.approx(5.0)

    def test_master_jitter(self, ldf: LDFFile) -> None:
        assert ldf.master.jitter_ms == pytest.approx(0.1)

    def test_slave_count(self, ldf: LDFFile) -> None:
        assert len(ldf.slaves) == 4

    def test_slave_names(self, ldf: LDFFile) -> None:
        names = {s.name for s in ldf.slaves}
        assert names == {'BodyControl', 'WindowLeft', 'WindowRight', 'SeatLeft'}

    def test_slaves_not_master(self, ldf: LDFFile) -> None:
        for slave in ldf.slaves:
            assert slave.is_master is False


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class TestSignals:
    def test_signal_count(self, ldf: LDFFile) -> None:
        assert len(ldf.signals) == 15

    def test_signal_names_present(self, ldf: LDFFile) -> None:
        for name in ('WinLeftCmd', 'WinRightPos', 'InteriorTemp', 'SeatErr'):
            assert name in ldf.signals

    def test_win_left_cmd_bit_length(self, ldf: LDFFile) -> None:
        assert ldf.signals['WinLeftCmd'].bit_length == 2

    def test_win_left_pos_bit_length(self, ldf: LDFFile) -> None:
        assert ldf.signals['WinLeftPos'].bit_length == 8

    def test_win_left_cmd_publisher(self, ldf: LDFFile) -> None:
        assert ldf.signals['WinLeftCmd'].publisher == 'BCM'

    def test_win_left_pos_publisher(self, ldf: LDFFile) -> None:
        assert ldf.signals['WinLeftPos'].publisher == 'WindowLeft'

    def test_signal_subscribers(self, ldf: LDFFile) -> None:
        assert 'BCM' in ldf.signals['WinLeftPos'].subscribers

    def test_signal_init_value(self, ldf: LDFFile) -> None:
        assert ldf.signals['WinLeftCmd'].init_value == 0


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

class TestFrames:
    def test_frame_count(self, ldf: LDFFile) -> None:
        assert len(ldf.frames) == 6

    def test_frame_names_present(self, ldf: LDFFile) -> None:
        for name in ('WinCmd', 'SeatCmd', 'MirrorCmd', 'WinStatus', 'SeatStatus', 'BodyStatus'):
            assert name in ldf.frames

    def test_win_cmd_id(self, ldf: LDFFile) -> None:
        assert ldf.frames['WinCmd'].frame_id == 0x10

    def test_win_cmd_publisher(self, ldf: LDFFile) -> None:
        assert ldf.frames['WinCmd'].publisher == 'BCM'

    def test_win_cmd_length(self, ldf: LDFFile) -> None:
        assert ldf.frames['WinCmd'].length == 2

    def test_win_cmd_signals(self, ldf: LDFFile) -> None:
        signal_names = {s.signal_name for s in ldf.frames['WinCmd'].signals}
        assert signal_names == {'WinLeftCmd', 'WinRightCmd'}

    def test_win_left_cmd_offset(self, ldf: LDFFile) -> None:
        frame = ldf.frames['WinCmd']
        offsets = {s.signal_name: s.bit_offset for s in frame.signals}
        assert offsets['WinLeftCmd'] == 0
        assert offsets['WinRightCmd'] == 2

    def test_win_status_publisher(self, ldf: LDFFile) -> None:
        assert ldf.frames['WinStatus'].publisher == 'WindowLeft'

    def test_body_status_id(self, ldf: LDFFile) -> None:
        assert ldf.frames['BodyStatus'].frame_id == 0x22


# ---------------------------------------------------------------------------
# Schedule tables
# ---------------------------------------------------------------------------

class TestScheduleTables:
    def test_table_count(self, ldf: LDFFile) -> None:
        assert len(ldf.schedule_tables) == 2

    def test_table_names(self, ldf: LDFFile) -> None:
        assert 'Normal_Schedule' in ldf.schedule_tables
        assert 'Slow_Schedule' in ldf.schedule_tables

    def test_normal_entry_count(self, ldf: LDFFile) -> None:
        assert len(ldf.schedule_tables['Normal_Schedule'].entries) == 6

    def test_slow_entry_count(self, ldf: LDFFile) -> None:
        assert len(ldf.schedule_tables['Slow_Schedule'].entries) == 3

    def test_entry_delay(self, ldf: LDFFile) -> None:
        first = ldf.schedule_tables['Normal_Schedule'].entries[0]
        assert first.delay_ms == pytest.approx(10.0)

    def test_entry_frame_name(self, ldf: LDFFile) -> None:
        first = ldf.schedule_tables['Normal_Schedule'].entries[0]
        assert first.frame_name == 'WinCmd'


# ---------------------------------------------------------------------------
# Signal encoding types
# ---------------------------------------------------------------------------

class TestEncodingTypes:
    def test_encoding_count(self, ldf: LDFFile) -> None:
        assert len(ldf.encoding_types) == 5

    def test_encoding_names(self, ldf: LDFFile) -> None:
        for name in ('MotorCmd', 'Position', 'HeatLevel', 'ErrorFlag', 'Temperature'):
            assert name in ldf.encoding_types

    def test_motor_cmd_values(self, ldf: LDFFile) -> None:
        values = ldf.encoding_types['MotorCmd'].values
        assert len(values) == 4

    def test_motor_cmd_logical_labels(self, ldf: LDFFile) -> None:
        labels = {v.min_value: v.label for v in ldf.encoding_types['MotorCmd'].values}
        assert labels[0] == 'Idle'
        assert labels[1] == 'Up / Forward'
        assert labels[2] == 'Down / Backward'

    def test_position_physical(self, ldf: LDFFile) -> None:
        v = ldf.encoding_types['Position'].values[0]
        assert v.kind == 'physical'
        assert v.scale == pytest.approx(0.392)
        assert v.unit == '%'

    def test_temperature_offset(self, ldf: LDFFile) -> None:
        v = ldf.encoding_types['Temperature'].values[0]
        assert v.offset == pytest.approx(-40.0)
        assert v.unit == '°C'


# ---------------------------------------------------------------------------
# Signal representation
# ---------------------------------------------------------------------------

class TestSignalRepresentation:
    def test_win_left_cmd_encoding(self, ldf: LDFFile) -> None:
        assert ldf.signal_representations['WinLeftCmd'] == 'MotorCmd'

    def test_win_left_pos_encoding(self, ldf: LDFFile) -> None:
        assert ldf.signal_representations['WinLeftPos'] == 'Position'

    def test_interior_temp_encoding(self, ldf: LDFFile) -> None:
        assert ldf.signal_representations['InteriorTemp'] == 'Temperature'

    def test_seat_heat_encoding(self, ldf: LDFFile) -> None:
        assert ldf.signal_representations['SeatHeat'] == 'HeatLevel'


# ---------------------------------------------------------------------------
# Node attributes
# ---------------------------------------------------------------------------

class TestNodeAttributes:
    def test_attribute_count(self, ldf: LDFFile) -> None:
        assert len(ldf.node_attributes) == 4

    def test_body_control_nad(self, ldf: LDFFile) -> None:
        assert ldf.node_attributes['BodyControl'].configured_nad == 0x01

    def test_window_left_nad(self, ldf: LDFFile) -> None:
        assert ldf.node_attributes['WindowLeft'].configured_nad == 0x02

    def test_lin_protocol(self, ldf: LDFFile) -> None:
        assert ldf.node_attributes['BodyControl'].lin_protocol == '2.1'

    def test_p2_min(self, ldf: LDFFile) -> None:
        assert ldf.node_attributes['BodyControl'].p2_min_ms == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Parser robustness – parse_string interface
# ---------------------------------------------------------------------------

class TestParseString:
    def test_minimal_ldf(self) -> None:
        src = '''
        LIN_description_file ;
        LIN_protocol_version = "2.0" ;
        LIN_language_version = "2.0" ;
        LIN_speed = 9.6 kbps ;
        Nodes { Master: ECU, 10 ms, 0.5 ms ; Slaves: SensorA ; }
        Signals { Temp : 8, 0, SensorA, ECU ; }
        Frames { TempFrame : 0x01, SensorA, 1 { Temp, 0 ; } }
        '''
        ldf = LDFParser().parse_string(src)
        assert ldf.protocol_version == '2.0'
        assert ldf.master is not None
        assert ldf.master.name == 'ECU'
        assert 'SensorA' in {s.name for s in ldf.slaves}
        assert 'Temp' in ldf.signals
        assert 'TempFrame' in ldf.frames

    def test_empty_ldf(self) -> None:
        ldf = LDFParser().parse_string('LIN_description_file ;')
        assert ldf.protocol_version == ''
        assert ldf.master is None
        assert not ldf.signals
        assert not ldf.frames

    def test_comment_stripping(self) -> None:
        src = '''
        /* This is a block comment */
        LIN_description_file ;
        LIN_protocol_version = "2.1" ; // line comment
        LIN_language_version = "2.1" ;
        LIN_speed = 19.2 kbps ;
        '''
        ldf = LDFParser().parse_string(src)
        assert ldf.protocol_version == '2.1'

    def test_hex_frame_id(self) -> None:
        src = '''
        LIN_description_file ;
        LIN_protocol_version = "2.1" ;
        LIN_language_version = "2.1" ;
        LIN_speed = 19.2 kbps ;
        Nodes { Master: M, 5 ms, 0 ms ; Slaves: S ; }
        Signals { S1 : 8, 0, M, S ; }
        Frames { F1 : 0x3C, M, 1 { S1, 0 ; } }
        '''
        ldf = LDFParser().parse_string(src)
        assert ldf.frames['F1'].frame_id == 0x3C

    def test_decimal_frame_id(self) -> None:
        src = '''
        LIN_description_file ;
        LIN_protocol_version = "2.1" ;
        LIN_language_version = "2.1" ;
        LIN_speed = 19.2 kbps ;
        Nodes { Master: M, 5 ms, 0 ms ; Slaves: S ; }
        Signals { S1 : 8, 0, M, S ; }
        Frames { F1 : 16, M, 1 { S1, 0 ; } }
        '''
        ldf = LDFParser().parse_string(src)
        assert ldf.frames['F1'].frame_id == 16
