"""LIN bit/frame timing calculations.

Pure-math helpers that compute LIN protocol frame durations from a baud rate
and a frame data length, following LIN Specification Package 2.2A
(clause 2.3.2.4 "Frame transfer time"). No hardware, no I/O.

Constants
---------
* 13 dominant bits for the **break field** (minimum)
* 1 break delimiter bit
* 10 bits for the **sync byte** (8 data + start + stop)
* 10 bits for the **PID byte** (8 data + start + stop)
* 10 bits per data / checksum byte (8 data + start + stop)
* The LIN spec allows up to 40% inter-byte space, hence the
  ``THEADER_MAX = 1.4 * THEADER_NOMINAL`` and
  ``TRESPONSE_MAX = 1.4 * TRESPONSE_NOMINAL`` upper bounds.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.10.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bits per LIN UART byte (8 data + 1 start + 1 stop, no parity).
BITS_PER_BYTE = 10

# Header field bit count: break (13) + break delimiter (1) +
# sync byte (10) + PID byte (10) = 34.
HEADER_BITS_NOMINAL = 13 + 1 + BITS_PER_BYTE + BITS_PER_BYTE  # 34

# LIN allows up to 40 % inter-byte space (LIN 2.2A, 2.3.2.4).
HEADER_SLACK_FACTOR = 1.4
RESPONSE_SLACK_FACTOR = 1.4

# Permitted baud rate range for LIN (LIN 2.2A, 2.4 "Bit rate"): 1 - 20 kbps.
LIN_MIN_BAUDRATE = 1_000
LIN_MAX_BAUDRATE = 20_000

# Maximum data bytes per LIN frame (LIN 2.2A, 2.3.2 "Frame structure").
LIN_MAX_DATA_BYTES = 8


@dataclass(frozen=True)
class FrameTiming:
    """Computed time budget for one LIN frame, in milliseconds.

    All fields are derived from the baud rate and the data length only,
    independently of the actual checksum bytes content.

    Attributes:
        bit_time_ms: Single-bit duration ``1 / baudrate`` in milliseconds.
        header_nominal_ms: Header time without inter-byte slack.
        header_max_ms: Header time including the 40 % LIN slack budget.
        response_nominal_ms: Data + checksum time without inter-byte slack.
        response_max_ms: Data + checksum time including the 40 % slack.
        frame_nominal_ms: ``header_nominal_ms + response_nominal_ms``.
        frame_max_ms: ``header_max_ms + response_max_ms`` (LIN slot bound).
    """

    bit_time_ms: float
    header_nominal_ms: float
    header_max_ms: float
    response_nominal_ms: float
    response_max_ms: float
    frame_nominal_ms: float
    frame_max_ms: float


def validate_baudrate(baudrate: int) -> None:
    """Raise :class:`ValueError` if ``baudrate`` is outside the LIN range.

    LIN 2.2A restricts the bit rate to 1 - 20 kbps. Anything outside that
    interval is rejected so that callers do not silently configure a
    non-conformant channel.
    """
    if not isinstance(baudrate, (int, float)):
        raise TypeError(f"baudrate must be a number, got {type(baudrate).__name__}")
    if baudrate < LIN_MIN_BAUDRATE or baudrate > LIN_MAX_BAUDRATE:
        raise ValueError(
            f"baudrate {baudrate} bps outside the LIN range "
            f"[{LIN_MIN_BAUDRATE}, {LIN_MAX_BAUDRATE}] bps"
        )


def validate_data_length(data_length: int) -> None:
    """Raise :class:`ValueError` if the LIN data length is out of range.

    LIN 2.2A allows 1 to 8 data bytes per classical frame.
    """
    if not isinstance(data_length, int):
        raise TypeError(f"data_length must be int, got {type(data_length).__name__}")
    if data_length < 1 or data_length > LIN_MAX_DATA_BYTES:
        raise ValueError(
            f"data_length {data_length} outside the LIN range [1, {LIN_MAX_DATA_BYTES}]"
        )


def bit_time_ms(baudrate: int) -> float:
    """Return the single-bit time in milliseconds for ``baudrate``."""
    validate_baudrate(baudrate)
    return 1000.0 / float(baudrate)


def header_time_ms(baudrate: int, *, with_slack: bool = False) -> float:
    """Return the LIN header field duration in milliseconds.

    Args:
        baudrate: LIN baud rate, in bits per second.
        with_slack: When True, return the LIN-specified upper bound
            (40 % inter-byte slack). When False, return the nominal header
            time.
    """
    nominal = HEADER_BITS_NOMINAL * bit_time_ms(baudrate)
    return nominal * HEADER_SLACK_FACTOR if with_slack else nominal


def response_time_ms(baudrate: int, data_length: int, *, with_slack: bool = False) -> float:
    """Return the LIN response (data + checksum) duration in milliseconds.

    The response carries ``data_length`` data bytes followed by 1 checksum
    byte, so the nominal response covers ``10 * (data_length + 1)`` bit times.

    Args:
        baudrate: LIN baud rate, in bits per second.
        data_length: Number of payload bytes (1 - 8).
        with_slack: When True, return the LIN-specified upper bound.
    """
    validate_data_length(data_length)
    nominal = BITS_PER_BYTE * (data_length + 1) * bit_time_ms(baudrate)
    return nominal * RESPONSE_SLACK_FACTOR if with_slack else nominal


def frame_time_ms(baudrate: int, data_length: int, *, with_slack: bool = False) -> float:
    """Return the total LIN frame duration in milliseconds.

    A LIN frame is ``header + response``. With ``with_slack=True`` this
    returns the worst-case "slot time" used to validate schedule entries.
    """
    return header_time_ms(baudrate, with_slack=with_slack) + response_time_ms(
        baudrate, data_length, with_slack=with_slack
    )


def compute_frame_timing(baudrate: int, data_length: int) -> FrameTiming:
    """Build a :class:`FrameTiming` summary for one frame definition."""
    bt = bit_time_ms(baudrate)
    h_nom = header_time_ms(baudrate, with_slack=False)
    h_max = header_time_ms(baudrate, with_slack=True)
    r_nom = response_time_ms(baudrate, data_length, with_slack=False)
    r_max = response_time_ms(baudrate, data_length, with_slack=True)
    return FrameTiming(
        bit_time_ms=bt,
        header_nominal_ms=h_nom,
        header_max_ms=h_max,
        response_nominal_ms=r_nom,
        response_max_ms=r_max,
        frame_nominal_ms=h_nom + r_nom,
        frame_max_ms=h_max + r_max,
    )
