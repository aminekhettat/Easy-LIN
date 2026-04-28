"""Tests for the LIN-configurability detection logic.

Covers the channel-capability helpers added to :mod:`src.vector_xl_api`,
the ``lin_configurable`` plumbing through
:class:`src.communication.hardware_discovery.HardwareDiscovery`, the
``auto_assign_application`` skip logic, the corresponding ``LINMaster``
helpers, and the GUI surface (combobox filtering + device-info dialog).

The tests use a real LIN-configurable bitmap (lower bits 0x2 +
upper-bit XL_BUS_ACTIVE_CAP_LIN = 0x20000) and a CAN-only bitmap
(0x10001) modelled after the live VN1630A driver dump:

    LINpiggy 7269mag channel : busCaps = 0x8020903 -> LIN ready
    On board CAN 1051cap     : busCaps = 0x10001   -> NOT LIN ready
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Capability bitmaps modelled on the real VN1630A driver dump.
# ---------------------------------------------------------------------------

LIN_READY_CAPS = 0x08020903  # LINpiggy 7269mag channel on the real device
CAN_ONLY_CAPS = 0x00010001  # On-board CAN 1051cap channel (LIN-compatible
# at the silicon level but no active LIN cap)


def _channel(
    name: str,
    hw_type: int,
    hw_index: int,
    hw_channel: int,
    channel_index: int,
    mask: int,
    caps: int = LIN_READY_CAPS,
    serial: int = 9540,
    article: int = 7113,
    transceiver: bytes = b"LINpiggy 7269mag",
) -> MagicMock:
    """Return a MagicMock that mimics one ``XL_CHANNEL_CONFIG`` entry."""
    ch = MagicMock()
    ch.name = name.encode("ascii") + b"\x00"
    ch.hwType = hw_type
    ch.hwIndex = hw_index
    ch.hwChannel = hw_channel
    ch.channelIndex = channel_index
    ch.channelMask = mask
    ch.channelBusCapabilities = caps
    ch.serialNumber = serial
    ch.articleNumber = article
    ch.transceiverName = transceiver
    return ch


# ---------------------------------------------------------------------------
# VectorXLApi.is_lin_compatible / is_lin_configurable
# ---------------------------------------------------------------------------


class TestVectorXLApiCapabilityHelpers:
    """Validate the static capability helpers on :class:`VectorXLApi`."""

    def test_lin_ready_caps_are_compatible_and_configurable(self):
        from src.vector_xl_api import VectorXLApi

        ch = _channel("LIN", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)
        assert VectorXLApi.is_lin_compatible(ch) is True
        assert VectorXLApi.is_lin_configurable(ch) is True

    def test_can_only_caps_are_neither_compatible_nor_configurable(self):
        from src.vector_xl_api import VectorXLApi

        ch = _channel("CAN", 57, 0, 2, 2, 0x4, caps=CAN_ONLY_CAPS)
        assert VectorXLApi.is_lin_compatible(ch) is False
        assert VectorXLApi.is_lin_configurable(ch) is False

    def test_compat_only_without_active_cap_is_not_configurable(self):
        from src.vector_xl_api import VectorXLApi, XL_BUS_COMPATIBLE_LIN

        ch = _channel("LINcompat", 57, 0, 0, 0, 0x1, caps=XL_BUS_COMPATIBLE_LIN)
        assert VectorXLApi.is_lin_compatible(ch) is True
        assert VectorXLApi.is_lin_configurable(ch) is False

    def test_active_cap_alone_marks_channel_configurable(self):
        from src.vector_xl_api import VectorXLApi, XL_BUS_ACTIVE_CAP_LIN

        ch = _channel("LINactive", 57, 0, 0, 0, 0x1, caps=XL_BUS_ACTIVE_CAP_LIN)
        assert VectorXLApi.is_lin_configurable(ch) is True

    def test_helpers_tolerate_missing_attribute(self):
        from src.vector_xl_api import VectorXLApi

        bare = MagicMock(spec=[])  # no channelBusCapabilities at all
        assert VectorXLApi.is_lin_compatible(bare) is False
        assert VectorXLApi.is_lin_configurable(bare) is False

    def test_helpers_tolerate_garbage_attribute(self):
        from src.vector_xl_api import VectorXLApi

        ch = MagicMock()
        ch.channelBusCapabilities = "not-an-int"
        assert VectorXLApi.is_lin_compatible(ch) is False
        assert VectorXLApi.is_lin_configurable(ch) is False

    def test_lin_configurable_channels_filters_correctly(self):
        from src.vector_xl_api import VectorXLApi

        cfg = MagicMock()
        cfg.channelCount = 3
        ch_lin = _channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)
        ch_can = _channel("CAN1", 57, 0, 2, 2, 0x4, caps=CAN_ONLY_CAPS)
        ch_lin2 = _channel("LIN2", 57, 0, 1, 1, 0x2, caps=LIN_READY_CAPS)
        cfg.channel = [ch_lin, ch_can, ch_lin2]

        api = VectorXLApi.__new__(VectorXLApi)
        result = api.lin_configurable_channels(cfg)
        assert [c.channelMask for c in result] == [0x1, 0x2]


# ---------------------------------------------------------------------------
# HardwareDiscovery.scan_devices populates lin_configurable
# ---------------------------------------------------------------------------


class TestHardwareDiscoveryConfigurability:
    def test_scan_devices_marks_lin_ready_channel(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = MagicMock()
        cfg = MagicMock()
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = [
            _channel("VN1630A Channel 1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS),
        ]

        d = HardwareDiscovery(api=api)
        devices = d.scan_devices()

        assert len(devices) == 1
        ch = devices[0].channels[0]
        assert ch.lin_configurable is True
        assert ch.bus_capabilities == LIN_READY_CAPS
        assert ch.transceiver_name == "LINpiggy 7269mag"
        assert ch.article_number == 7113
        assert ch.device_serial == "9540"

    def test_scan_devices_marks_can_only_channel_as_not_configurable(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = MagicMock()
        cfg = MagicMock()
        api.get_driver_config.return_value = cfg
        # The driver still lists the CAN channel because we feed it through
        # api.lin_channels() (real api filters the silicon-level LIN-cap
        # bit, but we keep the test independent of that filter).
        api.lin_channels.return_value = [
            _channel(
                "VN1630A Channel 3",
                57,
                0,
                2,
                2,
                0x4,
                caps=CAN_ONLY_CAPS,
                transceiver=b"On board CAN 1051cap(Highspeed)",
            ),
        ]

        d = HardwareDiscovery(api=api)
        ch = d.scan_devices()[0].channels[0]
        assert ch.lin_configurable is False
        assert ch.bus_capabilities == CAN_ONLY_CAPS


# ---------------------------------------------------------------------------
# HardwareDiscovery.auto_assign_application
# ---------------------------------------------------------------------------


class TestAutoAssignApplication:
    def _build_api(self, channels):
        api = MagicMock()
        cfg = MagicMock()
        api.get_driver_config.return_value = cfg
        api.lin_channels.return_value = channels
        # By default, no application channel is registered yet.
        api.get_appl_config.return_value = (0, 0, 0)
        api.set_appl_config.return_value = None
        return api

    def test_assigns_only_lin_configurable_channels(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = self._build_api(
            [
                _channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS),
                _channel(
                    "CAN3",
                    57,
                    0,
                    2,
                    2,
                    0x4,
                    caps=CAN_ONLY_CAPS,
                    transceiver=b"On board CAN 1051cap",
                ),
                _channel("LIN2", 57, 0, 1, 1, 0x2, caps=LIN_READY_CAPS),
            ]
        )
        d = HardwareDiscovery(api=api)
        results = d.auto_assign_application(app_name="EasyLIN")

        actions = [r["action"] for r in results]
        # scan_devices() sorts channels per device by (hw_channel, channel_index),
        # so the iteration order is LIN1 (hw_channel=0), LIN2 (hw_channel=1),
        # then the non-configurable CAN3 (hw_channel=2).
        assert actions == ["created", "created", "skipped-not-configurable"]

        # Only two real assignments should have hit set_appl_config, with
        # contiguous app_channel indices 0 and 1.
        assert api.set_appl_config.call_count == 2
        first_call, second_call = api.set_appl_config.call_args_list
        assert first_call.args[0] == "EasyLIN"
        assert first_call.args[1] == 0  # app_channel 0
        assert first_call.args[2:5] == (57, 0, 0)
        assert second_call.args[1] == 1  # app_channel 1
        assert second_call.args[2:5] == (57, 0, 1)

        # The skipped entry must not consume an app_channel slot.
        assigned = [r for r in results if r["action"] != "skipped-not-configurable"]
        assert [r["app_channel"] for r in assigned] == [0, 1]
        skipped = [r for r in results if r["action"] == "skipped-not-configurable"]
        assert skipped[0]["app_channel"] is None

    def test_keeps_existing_assignment_when_already_correct(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = self._build_api([_channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)])
        api.get_appl_config.return_value = (57, 0, 0)
        d = HardwareDiscovery(api=api)
        results = d.auto_assign_application()
        assert results[0]["action"] == "kept"
        api.set_appl_config.assert_not_called()

    def test_updates_existing_assignment_when_pointing_elsewhere(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = self._build_api([_channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)])
        api.get_appl_config.return_value = (57, 1, 0)  # different hw_index
        d = HardwareDiscovery(api=api)
        results = d.auto_assign_application()
        assert results[0]["action"] == "updated"
        api.set_appl_config.assert_called_once()

    def test_empty_when_no_channels(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = self._build_api([])
        d = HardwareDiscovery(api=api)
        assert d.auto_assign_application() == []
        api.set_appl_config.assert_not_called()

    def test_set_appl_config_failure_is_marked_skipped(self):
        from src.communication.hardware_discovery import HardwareDiscovery

        api = self._build_api([_channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)])
        api.set_appl_config.side_effect = RuntimeError("driver missing export")
        d = HardwareDiscovery(api=api)
        results = d.auto_assign_application()
        assert results[0]["action"] == "skipped"


# ---------------------------------------------------------------------------
# LINMaster.list_lin_channels exposes lin_configurable; auto_assign helper
# ---------------------------------------------------------------------------


class TestLINMasterAutoAssign:
    @patch("src.lin_master.VectorXLApi")
    def test_list_lin_channels_includes_configurability(self, MockApi):
        from src.lin_master import LINMaster
        from src.vector_xl_api import VectorXLApi as RealVectorXLApi

        api = MockApi.return_value
        # The real static helper must still run when the class is mocked;
        # reuse the real implementation explicitly.
        MockApi.is_lin_configurable.side_effect = RealVectorXLApi.is_lin_configurable
        ch = _channel("LIN1", 57, 0, 0, 0, 0x1, caps=LIN_READY_CAPS)
        api.get_driver_config.return_value = MagicMock()
        api.lin_channels.return_value = [ch]

        result = LINMaster.list_lin_channels()
        assert result[0]["lin_configurable"] is True
        assert result[0]["bus_capabilities"] == LIN_READY_CAPS
        assert result[0]["device_serial"] == "9540"
        assert result[0]["transceiver_name"] == "LINpiggy 7269mag"

    @patch("src.communication.hardware_discovery.HardwareDiscovery.auto_assign_application")
    def test_auto_assign_lin_channels_delegates(self, mock_auto):
        from src.lin_master import LINMaster

        mock_auto.return_value = [{"action": "created", "app_channel": 0}]
        result = LINMaster.auto_assign_lin_channels(app_name="MyApp")
        mock_auto.assert_called_once_with(app_name="MyApp")
        assert result == [{"action": "created", "app_channel": 0}]

    @patch(
        "src.communication.hardware_discovery.HardwareDiscovery.auto_assign_application",
        side_effect=RuntimeError("boom"),
    )
    def test_auto_assign_lin_channels_swallows_runtime_error(self, _mock_auto):
        from src.lin_master import LINMaster

        assert LINMaster.auto_assign_lin_channels() == []


# ---------------------------------------------------------------------------
# GUI: combobox filters and device-info dialog respect lin_configurable
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def panel(qapp):
    from src.gui.communication_panel import CommunicationPanel

    backend = MagicMock()
    backend.list_lin_channels.return_value = []
    backend.is_connected = False
    return CommunicationPanel(backend=backend)


class TestCommunicationPanelChannelFiltering:
    def test_combobox_hides_non_configurable_channels(self, panel):
        from src.gui import communication_panel as mod

        with patch.object(mod.LINMaster, "auto_assign_lin_channels", return_value=[]):
            panel._backend.list_lin_channels.return_value = [
                {
                    "name": "LIN1",
                    "channel_index": 0,
                    "channel_mask": 1,
                    "lin_configurable": True,
                    "device_serial": "9540",
                },
                {
                    "name": "CAN3",
                    "channel_index": 2,
                    "channel_mask": 4,
                    "lin_configurable": False,
                    "device_serial": "9540",
                },
                {
                    "name": "LIN2",
                    "channel_index": 1,
                    "channel_mask": 2,
                    "lin_configurable": True,
                    "device_serial": "9540",
                },
            ]
            panel._refresh_channels()

        labels = [panel._channel_combo.itemText(i) for i in range(panel._channel_combo.count())]
        assert len(labels) == 2
        assert all("CAN3" not in lbl for lbl in labels)
        assert any("LIN1" in lbl for lbl in labels)
        assert any("LIN2" in lbl for lbl in labels)

    def test_combobox_warns_when_only_non_configurable_channels(self, panel):
        from src.gui import communication_panel as mod

        with patch.object(mod.LINMaster, "auto_assign_lin_channels", return_value=[]):
            panel._backend.list_lin_channels.return_value = [
                {
                    "name": "CAN3",
                    "channel_index": 2,
                    "channel_mask": 4,
                    "lin_configurable": False,
                    "device_serial": "9540",
                },
            ]
            panel._refresh_channels()

        assert panel._channel_combo.count() == 1
        assert "LIN-configurable" in panel._channel_combo.itemText(0)
        assert panel._channel_combo.itemData(0) is None

    def test_combobox_keeps_legacy_entries_without_lin_configurable_key(self, panel):
        """Older backends that don't supply the key should still show entries."""
        from src.gui import communication_panel as mod

        with patch.object(mod.LINMaster, "auto_assign_lin_channels", return_value=[]):
            panel._backend.list_lin_channels.return_value = [
                {"name": "LegacyLIN", "channel_index": 0, "channel_mask": 1},
            ]
            panel._refresh_channels()

        assert panel._channel_combo.count() == 1
        assert "LegacyLIN" in panel._channel_combo.itemText(0)
        assert panel._channel_combo.itemData(0) == 1


class TestDeviceInfoDialog:
    def test_dialog_renders_lin_ready_column(self, qapp):
        from src.gui.communication_panel import _DeviceInfoDialog

        channels = [
            {
                "name": "VN1630A Channel 1",
                "channel_index": 0,
                "channel_mask": 0x1,
                "hw_type": 57,
                "hw_index": 0,
                "hw_channel": 0,
                "device_serial": "9540",
                "article_number": 7113,
                "transceiver_name": "LINpiggy 7269mag",
                "lin_configurable": True,
            },
            {
                "name": "VN1630A Channel 3",
                "channel_index": 2,
                "channel_mask": 0x4,
                "hw_type": 57,
                "hw_index": 0,
                "hw_channel": 2,
                "device_serial": "9540",
                "article_number": 7113,
                "transceiver_name": "On board CAN 1051cap",
                "lin_configurable": False,
            },
        ]
        dlg = _DeviceInfoDialog(channels)

        from PySide6.QtWidgets import QTableWidget

        table = dlg.findChild(QTableWidget)
        assert table is not None
        # Header includes the LIN-ready column.
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        assert "LIN ready" in headers
        ready_col = headers.index("LIN ready")
        assert table.rowCount() == 2
        assert table.item(0, ready_col).text() == "Yes"
        assert table.item(1, ready_col).text() == "No"
        # The "No" row should expose an explanatory tooltip for screen readers.
        assert "piggyback" in table.item(1, ready_col).toolTip().lower()
        dlg.deleteLater()

    def test_dialog_shows_empty_message_when_no_channels(self, qapp):
        from src.gui.communication_panel import _DeviceInfoDialog
        from PySide6.QtWidgets import QLabel

        dlg = _DeviceInfoDialog([])
        labels = [w.text() for w in dlg.findChildren(QLabel)]
        assert any("No Vector LIN-capable hardware" in t for t in labels)
        dlg.deleteLater()
