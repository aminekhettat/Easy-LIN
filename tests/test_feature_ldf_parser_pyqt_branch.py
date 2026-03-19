"""
Atomic features covered:
- Parse LDF from file and from inline strings
- Validate protocol metadata, nodes, signals, frames, schedules
- Validate encoding types and node attributes
- Verify parser error handling and lookup initialization

Unit tests for src.ldf_parser.

These tests exercise the LDF parser against the sample LDF file located at
tests/data/sample.ldf and against inline string fixtures so that they run
without any external dependencies.
"""

import os
import pytest

from src.ldf_parser import (
    parse_ldf,
    parse_ldf_string,
    LDFFile,
    LDFParseError,
)

# ---------------------------------------------------------------------------
# Fixture: path to the sample LDF file
# ---------------------------------------------------------------------------

SAMPLE_LDF = os.path.join(os.path.dirname(__file__), "data", "sample.ldf")


# ---------------------------------------------------------------------------
# Tests: load from file
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_file_loads_without_error(self):
        ldf = parse_ldf(SAMPLE_LDF)
        assert isinstance(ldf, LDFFile)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_ldf("/nonexistent/path/to/file.ldf")


# ---------------------------------------------------------------------------
# Tests: protocol metadata
# ---------------------------------------------------------------------------

class TestProtocolMetadata:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_protocol_version(self):
        assert self.ldf.protocol_version == "2.1"

    def test_language_version(self):
        assert self.ldf.language_version == "2.1"

    def test_speed(self):
        assert self.ldf.speed == pytest.approx(19.2)

    def test_channel_name(self):
        assert self.ldf.channel_name == "DB"


# ---------------------------------------------------------------------------
# Tests: Nodes section
# ---------------------------------------------------------------------------

class TestNodes:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_master_name(self):
        assert self.ldf.nodes is not None
        assert self.ldf.nodes.master.name == "VehicleMaster"

    def test_master_time_base(self):
        assert self.ldf.nodes.master.time_base == pytest.approx(5.0)

    def test_master_jitter(self):
        assert self.ldf.nodes.master.jitter == pytest.approx(0.1)

    def test_slave_count(self):
        assert len(self.ldf.nodes.slaves) == 3

    def test_slave_names(self):
        assert "MotorController" in self.ldf.nodes.slaves
        assert "LightController" in self.ldf.nodes.slaves
        assert "SensorNode" in self.ldf.nodes.slaves


# ---------------------------------------------------------------------------
# Tests: Signals section
# ---------------------------------------------------------------------------

class TestSignals:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_signal_count(self):
        assert len(self.ldf.signals) == 11

    def test_motor_speed_signal(self):
        sig = self.ldf.signal("MotorSpeed")
        assert sig is not None
        assert sig.size == 8
        assert sig.init_value == 0
        assert sig.publisher == "VehicleMaster"
        assert "MotorController" in sig.subscribers

    def test_temperature_signal(self):
        sig = self.ldf.signal("Temperature")
        assert sig is not None
        assert sig.size == 10
        assert sig.publisher == "SensorNode"

    def test_lookup_by_name(self):
        assert self.ldf.signal("NonExistent") is None


# ---------------------------------------------------------------------------
# Tests: Frames section
# ---------------------------------------------------------------------------

class TestFrames:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_frame_count(self):
        assert len(self.ldf.frames) == 5

    def test_motor_command_frame(self):
        frame = self.ldf.frame_by_name("MotorCommand")
        assert frame is not None
        assert frame.frame_id == 0x10
        assert frame.publisher == "VehicleMaster"
        assert frame.frame_size == 2
        signal_names = [s.signal_name for s in frame.signals]
        assert "MotorSpeed" in signal_names
        assert "MotorDirection" in signal_names
        assert "MotorEnable" in signal_names

    def test_sensor_data_frame(self):
        frame = self.ldf.frame_by_name("SensorData")
        assert frame is not None
        assert frame.frame_id == 0x30
        assert frame.publisher == "SensorNode"

    def test_frame_by_id_lookup(self):
        frame = self.ldf.frame_by_id(0x10)
        assert frame is not None
        assert frame.name == "MotorCommand"

    def test_frame_by_id_unknown(self):
        assert self.ldf.frame_by_id(0xFF) is None

    def test_motor_speed_bit_offset(self):
        frame = self.ldf.frame_by_name("MotorCommand")
        motor_speed_ref = next(
            (s for s in frame.signals if s.signal_name == "MotorSpeed"), None
        )
        assert motor_speed_ref is not None
        assert motor_speed_ref.bit_offset == 0


# ---------------------------------------------------------------------------
# Tests: Schedule tables
# ---------------------------------------------------------------------------

class TestScheduleTables:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_schedule_count(self):
        assert len(self.ldf.schedule_tables) == 2

    def test_normal_schedule_entries(self):
        sched = next((s for s in self.ldf.schedule_tables if s.name == "NormalSchedule"), None)
        assert sched is not None
        assert len(sched.entries) == 5

    def test_fast_schedule_entries(self):
        sched = next((s for s in self.ldf.schedule_tables if s.name == "FastSchedule"), None)
        assert sched is not None
        assert len(sched.entries) == 3

    def test_schedule_entry_delay(self):
        sched = next((s for s in self.ldf.schedule_tables if s.name == "NormalSchedule"), None)
        motor_cmd = next((e for e in sched.entries if e.frame_name == "MotorCommand"), None)
        assert motor_cmd is not None
        assert motor_cmd.delay == pytest.approx(10.0)

    def test_sensor_data_delay_in_fast_schedule(self):
        sched = next((s for s in self.ldf.schedule_tables if s.name == "FastSchedule"), None)
        sensor = next((e for e in sched.entries if e.frame_name == "SensorData"), None)
        assert sensor is not None
        assert sensor.delay == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Tests: Signal encoding types
# ---------------------------------------------------------------------------

class TestEncodingTypes:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_encoding_count(self):
        assert len(self.ldf.encoding_types) == 3

    def test_motor_direction_encoding(self):
        enc = next((e for e in self.ldf.encoding_types if e.name == "MotorDirectionEncoding"), None)
        assert enc is not None
        assert len(enc.logical_values) == 4
        texts = [lv.text for lv in enc.logical_values]
        assert "Forward" in texts
        assert "Reverse" in texts

    def test_temperature_encoding(self):
        enc = next((e for e in self.ldf.encoding_types if e.name == "TemperatureEncoding"), None)
        assert enc is not None
        assert len(enc.physical_ranges) == 1
        pr = enc.physical_ranges[0]
        assert pr.min_value == 0
        assert pr.max_value == 1023
        assert pr.scale == pytest.approx(0.25)
        assert pr.offset == pytest.approx(-40.0)
        assert pr.unit == "deg C"

    def test_signal_representations(self):
        assert len(self.ldf.signal_representations) == 3
        rep = next(
            (r for r in self.ldf.signal_representations if r.encoding_type == "TemperatureEncoding"),
            None,
        )
        assert rep is not None
        assert "Temperature" in rep.signals


# ---------------------------------------------------------------------------
# Tests: Node attributes
# ---------------------------------------------------------------------------

class TestNodeAttributes:
    @pytest.fixture(autouse=True)
    def _ldf(self):
        self.ldf = parse_ldf(SAMPLE_LDF)

    def test_node_attribute_count(self):
        assert len(self.ldf.node_attributes) == 3

    def test_motor_controller_nad(self):
        na = next((n for n in self.ldf.node_attributes if n.node_name == "MotorController"), None)
        assert na is not None
        assert na.configured_nad == 0x01
        assert na.initial_nad == 0x01

    def test_motor_controller_product_id(self):
        na = next((n for n in self.ldf.node_attributes if n.node_name == "MotorController"), None)
        assert na.product_id_supplier == 0x1234
        assert na.product_id_function == 0x0001
        assert na.product_id_variant == 0x00

    def test_sensor_node_lin_protocol(self):
        na = next((n for n in self.ldf.node_attributes if n.node_name == "SensorNode"), None)
        assert na is not None
        assert na.lin_protocol == "2.0"

    def test_motor_controller_configurable_frames(self):
        na = next((n for n in self.ldf.node_attributes if n.node_name == "MotorController"), None)
        assert "MotorCommand" in na.configurable_frames
        assert "MotorResponse" in na.configurable_frames


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_empty_string_produces_default_ldf(self):
        ldf = parse_ldf_string("")
        assert isinstance(ldf, LDFFile)
        assert ldf.signals == []
        assert ldf.frames == []

    def test_minimal_ldf(self):
        content = """
        LIN_description_file ;
        LIN_protocol_version = "2.0" ;
        LIN_language_version = "2.0" ;
        LIN_speed = 9.6 kbps ;
        """
        ldf = parse_ldf_string(content)
        assert ldf.protocol_version == "2.0"
        assert ldf.speed == pytest.approx(9.6)

    def test_comment_removal(self):
        content = """
        LIN_description_file ; // top-level comment
        /* block comment */
        LIN_protocol_version = "1.3" ;
        LIN_language_version = "1.3" ;
        LIN_speed = 19.2 kbps ;
        """
        ldf = parse_ldf_string(content)
        assert ldf.protocol_version == "1.3"

    def test_hex_frame_id(self):
        content = """
        LIN_description_file ;
        LIN_protocol_version = "2.0" ;
        LIN_language_version = "2.0" ;
        LIN_speed = 19.2 kbps ;
        Nodes {
          Master: M, 5 ms, 0.1 ms ;
          Slaves: S1 ;
        }
        Signals {
          Sig1: 8, 0x00, M, S1 ;
        }
        Frames {
          F1 : 0x3A, M, 1 {
            Sig1, 0 ;
          }
        }
        """
        ldf = parse_ldf_string(content)
        assert ldf.frame_by_id(0x3A) is not None
        assert ldf.frame_by_id(0x3A).name == "F1"

    def test_build_lookups_called(self):
        ldf = parse_ldf(SAMPLE_LDF)
        # Lookups should be populated
        assert len(ldf._signals_by_name) == len(ldf.signals)
        assert len(ldf._frames_by_name) == len(ldf.frames)
        assert len(ldf._frames_by_id) == len(ldf.frames)
