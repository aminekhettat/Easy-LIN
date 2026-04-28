"""Unit tests for ``src.lin_timing``.

Cross-checks the implemented LIN timing equations against the reference
values in LIN Specification Package 2.2A, section 2.3.2.4 ("Frame transfer
time"). All numerical comparisons use a tight tolerance (1 micro-second).
"""

from __future__ import annotations

import math

import pytest

from src.lin_timing import (
    BITS_PER_BYTE,
    HEADER_BITS_NOMINAL,
    HEADER_SLACK_FACTOR,
    LIN_MAX_BAUDRATE,
    LIN_MAX_DATA_BYTES,
    LIN_MIN_BAUDRATE,
    RESPONSE_SLACK_FACTOR,
    bit_time_ms,
    compute_frame_timing,
    frame_time_ms,
    header_time_ms,
    response_time_ms,
    validate_baudrate,
    validate_data_length,
)

US = 1e-3  # 1 micro-second expressed in milliseconds.


class TestConstants:
    """Pin the LIN protocol constants so accidental drift fails loudly."""

    def test_bits_per_byte_is_ten(self):
        assert BITS_PER_BYTE == 10  # 8 data + start + stop.

    def test_header_bits_is_thirty_four(self):
        assert HEADER_BITS_NOMINAL == 34  # 13 break + 1 delim + 10 sync + 10 PID.

    def test_slack_factors_are_one_point_four(self):
        assert HEADER_SLACK_FACTOR == pytest.approx(1.4)
        assert RESPONSE_SLACK_FACTOR == pytest.approx(1.4)

    def test_lin_baud_range(self):
        assert LIN_MIN_BAUDRATE == 1_000
        assert LIN_MAX_BAUDRATE == 20_000

    def test_lin_max_data_bytes(self):
        assert LIN_MAX_DATA_BYTES == 8


class TestBitTime:
    def test_bit_time_at_19200_bps(self):
        # 1 / 19200 s = 52.0833... us = 0.052083... ms
        assert bit_time_ms(19_200) == pytest.approx(1000.0 / 19200.0, abs=US)

    def test_bit_time_at_20000_bps(self):
        assert bit_time_ms(20_000) == pytest.approx(0.05, abs=US)

    def test_bit_time_at_1000_bps(self):
        assert bit_time_ms(1_000) == pytest.approx(1.0, abs=US)


class TestHeaderTime:
    def test_header_nominal_at_19200(self):
        # 34 bits * (1/19200 s) ~= 1.7708 ms
        expected = 34 * (1000.0 / 19200.0)
        assert header_time_ms(19_200) == pytest.approx(expected, abs=US)

    def test_header_with_slack_is_1_4_times_nominal(self):
        nominal = header_time_ms(9_600)
        assert header_time_ms(9_600, with_slack=True) == pytest.approx(nominal * 1.4, abs=US)


class TestResponseTime:
    @pytest.mark.parametrize("data_length", list(range(1, 9)))
    def test_response_nominal_scales_linearly_with_data_length(self, data_length):
        # Response = 10 * (N + 1) * Tbit
        expected = 10 * (data_length + 1) * (1000.0 / 19200.0)
        assert response_time_ms(19_200, data_length) == pytest.approx(expected, abs=US)

    def test_response_with_slack_is_1_4_times_nominal(self):
        nominal = response_time_ms(19_200, 8)
        slack = response_time_ms(19_200, 8, with_slack=True)
        assert slack == pytest.approx(nominal * 1.4, abs=US)


class TestFrameTime:
    def test_frame_8_bytes_at_19200_matches_lin_spec(self):
        # LIN 2.2A, section 2.3.2.4: nominal 8-byte frame at 19.2 kbps is
        # (34 + 10 * 9) bits / 19200 bps = 124 / 19200 s = ~6.458 ms; with
        # the 40 % slack budget the worst-case slot is ~9.042 ms.
        nominal_expected = (34 + 10 * (8 + 1)) * (1000.0 / 19200.0)
        max_expected = 1.4 * nominal_expected
        assert frame_time_ms(19_200, 8) == pytest.approx(nominal_expected, abs=US)
        assert frame_time_ms(19_200, 8, with_slack=True) == pytest.approx(max_expected, abs=US)
        assert math.isclose(frame_time_ms(19_200, 8), 6.4583, rel_tol=1e-3)
        assert math.isclose(frame_time_ms(19_200, 8, with_slack=True), 9.0417, rel_tol=1e-3)

    def test_frame_nominal_one_byte_at_20000(self):
        # No slack: header (34 bits) + response (20 bits) = 54 bits, at
        # 20 kbps that is 54 * 0.05 ms = 2.7 ms.
        assert frame_time_ms(20_000, 1) == pytest.approx(2.7, abs=US)

    def test_frame_max_grows_with_data_length(self):
        previous = 0.0
        for length in range(1, 9):
            current = frame_time_ms(19_200, length, with_slack=True)
            assert current > previous
            previous = current


class TestComputeFrameTiming:
    def test_returns_consistent_aggregate(self):
        timing = compute_frame_timing(19_200, 8)
        assert timing.bit_time_ms == pytest.approx(bit_time_ms(19_200), abs=US)
        assert timing.header_nominal_ms == pytest.approx(header_time_ms(19_200), abs=US)
        assert timing.header_max_ms == pytest.approx(
            header_time_ms(19_200, with_slack=True), abs=US
        )
        assert timing.response_nominal_ms == pytest.approx(response_time_ms(19_200, 8), abs=US)
        assert timing.response_max_ms == pytest.approx(
            response_time_ms(19_200, 8, with_slack=True), abs=US
        )
        assert timing.frame_nominal_ms == pytest.approx(
            timing.header_nominal_ms + timing.response_nominal_ms, abs=US
        )
        assert timing.frame_max_ms == pytest.approx(
            timing.header_max_ms + timing.response_max_ms, abs=US
        )


class TestValidation:
    @pytest.mark.parametrize("invalid", [0, -1, 999, 20_001, 50_000])
    def test_baudrate_outside_lin_range_rejected(self, invalid):
        with pytest.raises(ValueError):
            validate_baudrate(invalid)

    def test_baudrate_must_be_numeric(self):
        with pytest.raises(TypeError):
            validate_baudrate("19200")

    @pytest.mark.parametrize("invalid", [0, -1, 9, 100])
    def test_data_length_outside_range_rejected(self, invalid):
        with pytest.raises(ValueError):
            validate_data_length(invalid)

    def test_data_length_must_be_int(self):
        with pytest.raises(TypeError):
            validate_data_length(1.0)

    @pytest.mark.parametrize("baudrate", [1_000, 9_600, 19_200, 20_000])
    def test_baudrate_inside_lin_range_accepted(self, baudrate):
        validate_baudrate(baudrate)  # must not raise

    @pytest.mark.parametrize("length", list(range(1, 9)))
    def test_data_length_inside_range_accepted(self, length):
        validate_data_length(length)  # must not raise
