"""
Atomic features covered:
- Simulation fallback and callback propagation for Vector transport
- Send/receive frame formatting and error behavior
- Vector channel enumeration behavior with and without python-can
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import src.communication.vector_lin as vector_lin
from src.communication.vector_lin import LINError, LINFrame, VectorLINBus


def test_linframe_helpers_and_string() -> None:
    frame = LINFrame(frame_id=0x12, data=bytes([0xAB, 0xCD]), direction="TX")

    assert frame.frame_id_hex == "0x12"
    assert frame.data_hex == "AB CD"
    assert "ID=0x12" in str(frame)


def test_send_without_start_raises() -> None:
    bus = VectorLINBus()
    with pytest.raises(LINError):
        bus.send_frame(LINFrame(frame_id=1, data=b"\x00"))


def test_simulation_mode_echoes_frames(monkeypatch) -> None:
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", False)

    bus = VectorLINBus()
    seen_rx = []
    seen_tx = []
    bus.add_rx_callback(seen_rx.append)
    bus.add_tx_callback(seen_tx.append)

    bus.start()
    sent = bus.send_frame_by_id(0x21, [0x01, 0x02])
    assert sent.frame_id == 0x21

    time.sleep(0.03)
    bus.stop()

    assert len(seen_tx) == 1
    assert seen_tx[0].direction == "TX"
    assert len(seen_rx) == 1
    assert seen_rx[0].direction == "RX"
    assert seen_rx[0].data == bytes([0x01, 0x02])


def test_list_vector_channels_no_can_available(monkeypatch) -> None:
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", False)
    assert VectorLINBus.list_vector_channels() == []


def test_list_vector_channels_returns_configs(monkeypatch) -> None:
    fake_can = SimpleNamespace(
        detect_available_configs=lambda interfaces: [
            {"interface": "vector", "channel": 0}
        ]
    )
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", True)
    monkeypatch.setattr(vector_lin, "can", fake_can)

    assert VectorLINBus.list_vector_channels() == [
        {"interface": "vector", "channel": 0}
    ]


def test_list_vector_channels_handles_detection_error(monkeypatch) -> None:
    fake_can = SimpleNamespace(
        detect_available_configs=lambda interfaces: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
    )
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", True)
    monkeypatch.setattr(vector_lin, "can", fake_can)

    assert VectorLINBus.list_vector_channels() == []


def test_start_vector_success_path(monkeypatch) -> None:
    class FakeBus:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def recv(self, timeout):
            return None

        def shutdown(self):
            pass

    fake_can = SimpleNamespace(
        interface=SimpleNamespace(Bus=lambda **kwargs: FakeBus(**kwargs))
    )
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", True)
    monkeypatch.setattr(vector_lin, "can", fake_can)

    bus = VectorLINBus(channel=2, bitrate=19200, app_name="Easy-LIN")
    bus.start()
    bus.start()
    assert bus.is_connected is True
    assert bus.is_simulation is False
    bus.stop()


def test_start_vector_failure_falls_back_to_sim(monkeypatch) -> None:
    def raising_bus(**kwargs):
        raise RuntimeError("driver unavailable")

    fake_can = SimpleNamespace(interface=SimpleNamespace(Bus=raising_bus))
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", True)
    monkeypatch.setattr(vector_lin, "can", fake_can)

    bus = VectorLINBus()
    bus.add_rx_callback(lambda _frame: None)
    bus.start()
    assert bus.is_simulation is True
    bus.stop()


def test_add_rx_callback_after_sim_start(monkeypatch) -> None:
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", False)
    bus = VectorLINBus()
    bus.start()

    hit = []
    bus.add_rx_callback(lambda frame: hit.append(frame.frame_id))
    bus.send_frame_by_id(2, [0xAA])

    time.sleep(0.03)
    bus.stop()
    assert hit == [2]


def test_notify_callbacks_handle_exceptions(monkeypatch) -> None:
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", False)

    bus = VectorLINBus()
    seen_rx = []

    def bad_rx(_frame):
        raise RuntimeError("rx callback failed")

    def bad_tx(_frame):
        raise RuntimeError("tx callback failed")

    bus.add_rx_callback(bad_rx)
    bus.add_rx_callback(seen_rx.append)
    bus.add_tx_callback(bad_tx)
    bus.start()
    bus.send_frame_by_id(1, [0x01])

    time.sleep(0.03)
    bus.stop()
    assert len(seen_rx) == 1


def test_send_via_can_without_bus_noop() -> None:
    bus = VectorLINBus()
    bus._send_via_can(LINFrame(frame_id=1, data=b"\x01"))


def test_send_via_can_error(monkeypatch) -> None:
    class FailingBus:
        def send(self, msg):
            raise RuntimeError("send failure")

        def shutdown(self):
            pass

    fake_can = SimpleNamespace(
        interface=SimpleNamespace(Bus=lambda **kwargs: FailingBus()),
        Message=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(vector_lin, "_CAN_AVAILABLE", True)
    monkeypatch.setattr(vector_lin, "can", fake_can)

    bus = VectorLINBus()
    bus.start()

    with pytest.raises(LINError):
        bus.send_frame(LINFrame(frame_id=1, data=b"\x01"))

    bus.stop()


def test_stop_handles_shutdown_exception() -> None:
    class BrokenBus:
        def shutdown(self):
            raise RuntimeError("cannot shutdown")

    bus = VectorLINBus()
    bus._bus = BrokenBus()
    bus.stop()


def test_rx_loop_dispatches_message_and_handles_callback_error() -> None:
    bus = VectorLINBus()

    class OneShotBus:
        def __init__(self):
            self.called = 0

        def recv(self, timeout):
            self.called += 1
            if self.called == 1:
                return SimpleNamespace(arbitration_id=0x25, data=[1, 2], timestamp=1.0)
            bus._running = False
            return None

    events = []

    def bad_cb(_frame):
        raise RuntimeError("cb failed")

    bus.add_rx_callback(bad_cb)
    bus.add_rx_callback(lambda frame: events.append(frame.frame_id))
    bus._bus = OneShotBus()
    bus._running = True
    bus._rx_loop()

    assert events == [0x25 & 0x3F]
