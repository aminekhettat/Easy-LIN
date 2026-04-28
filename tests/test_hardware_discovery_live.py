"""Live integration test for Vector hardware discovery.

These tests talk to the real Vector XL Driver and the physical hardware
attached to the workstation. They are automatically **skipped** when:

  * the Vector XL DLL (``vxlapi64.dll`` / ``vxlapi.dll``) is not installed,
  * no Vector device is currently visible to the driver, or
  * the user has not opted in by setting the environment variable
    ``EASYLIN_RUN_LIVE_HW_TESTS=1``.

To run them locally with a VN1630A (or any other LIN-capable Vector device)
connected, execute::

    $env:EASYLIN_RUN_LIVE_HW_TESTS = "1"
    python -m pytest tests/test_hardware_discovery_live.py -v
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Opt-in / skip guard - applied to every test in this module.
# ---------------------------------------------------------------------------

if os.environ.get("EASYLIN_RUN_LIVE_HW_TESTS") != "1":
    pytest.skip(
        "Live Vector hardware tests are opt-in. Set EASYLIN_RUN_LIVE_HW_TESTS=1 to enable.",
        allow_module_level=True,
    )

try:
    from src.vector_xl_api import VectorXLApi, VectorXLDriverNotFoundError
except Exception as exc:  # noqa: BLE001
    pytest.skip(
        f"Cannot import VectorXLApi (driver bindings unavailable): {exc}",
        allow_module_level=True,
    )

from src.communication.hardware_discovery import HardwareDiscovery, VectorDevice


@pytest.fixture(scope="module")
def discovery() -> HardwareDiscovery:
    """Return a real HardwareDiscovery; skip the module if the DLL is missing."""
    try:
        api = VectorXLApi()
    except VectorXLDriverNotFoundError as exc:
        pytest.skip(f"Vector XL Driver not installed: {exc}")
    return HardwareDiscovery(api=api)


@pytest.fixture(scope="module")
def devices(discovery: HardwareDiscovery) -> list[VectorDevice]:
    """Run a real ``scan_devices()`` once for the whole module."""
    try:
        result = discovery.scan_devices()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"scan_devices() failed against the live driver: {exc}")
    if not result:
        pytest.skip("No Vector device detected. Connect a VN1xxx (with LIN piggyback) and re-run.")
    return result


class TestLiveHardwareDiscovery:
    """Sanity checks against the real Vector driver."""

    def test_at_least_one_device_detected(self, devices):
        """``scan_devices`` must return at least one real (non-virtual) device."""
        non_virtual = [d for d in devices if d.hw_type != 1]
        assert non_virtual, (
            "Driver only reports virtual channels. "
            "Make sure the physical device appears in Vector Hardware Manager."
        )

    def test_every_channel_has_consistent_identity(self, devices):
        """Each channel must report a stable serial / hwType / hwIndex."""
        for device in devices:
            for ch in device.channels:
                assert ch.hw_type == device.hw_type
                assert ch.hw_index == device.hw_index
                assert ch.device_serial == device.device_serial
                assert ch.channel_mask > 0
                assert ch.name, "Vector channel reported an empty name"

    def test_every_channel_has_lin_capability(self, devices):
        """``HardwareDiscovery.get_lin_channels`` only yields LIN-compatible
        channels - the silicon-level capability bit must always be set."""
        for ch in [c for d in devices for c in d.channels]:
            assert ch.bus_capabilities & 0x2, (
                f"Channel '{ch.name}' has bus_capabilities=0x{ch.bus_capabilities:X} "
                "without the LIN-compatible bit set."
            )

    def test_at_least_one_channel_is_lin_configurable(self, devices):
        """At least one detected channel should currently be activatable as
        LIN; otherwise the test environment is missing a LIN piggyback."""
        configurable = [c for d in devices for c in d.channels if c.lin_configurable]
        if not configurable:
            pytest.skip(
                "No LIN-configurable channel on this machine "
                "(missing LIN piggyback?). Discovery still worked correctly."
            )
        # Each configurable channel must also be LIN-compatible (sanity).
        for ch in configurable:
            assert ch.bus_capabilities & 0x20000, (
                f"Channel '{ch.name}' marked configurable but lacks "
                f"XL_BUS_ACTIVE_CAP_LIN (caps=0x{ch.bus_capabilities:X})."
            )


class TestLiveAutoAssign:
    """Round-trip ``auto_assign_application`` against the real driver."""

    def test_auto_assign_uses_only_configurable_channels(self, discovery, devices):
        """The auto-assign helper must register exactly the LIN-configurable
        channels under the application name and skip the others."""
        configurable = [c for d in devices for c in d.channels if c.lin_configurable]
        if not configurable:
            pytest.skip("No LIN-configurable channel to assign on this machine.")

        # Use a dedicated application name so we never overwrite the user's
        # production "EasyLIN" assignment when running the test.
        app_name = "EasyLIN-LiveTest"

        results = discovery.auto_assign_application(app_name=app_name)
        assigned = [r for r in results if r["action"] != "skipped-not-configurable"]
        skipped = [r for r in results if r["action"] == "skipped-not-configurable"]

        assert len(assigned) == len(configurable), (
            f"Expected {len(configurable)} assigned channels, got {len(assigned)}: {results}"
        )
        # All assigned entries must point at hardware that we know is configurable.
        configurable_keys = {(c.hw_type, c.hw_index, c.hw_channel) for c in configurable}
        for r in assigned:
            assert (r["hw_type"], r["hw_index"], r["hw_channel"]) in configurable_keys
            assert r["action"] in {"created", "updated", "kept"}
        # All skipped entries must correspond to channels that are NOT configurable.
        for r in skipped:
            assert r["app_channel"] is None
            key = (r["hw_type"], r["hw_index"], r["hw_channel"])
            assert key not in configurable_keys

    def test_auto_assign_is_idempotent(self, discovery, devices):
        """Running auto-assign twice in a row must report ``kept`` the second
        time for every previously assigned channel."""
        configurable = [c for d in devices for c in d.channels if c.lin_configurable]
        if not configurable:
            pytest.skip("No LIN-configurable channel to assign on this machine.")

        app_name = "EasyLIN-LiveTest"
        # First call: ensures the assignment exists.
        discovery.auto_assign_application(app_name=app_name)
        # Second call: must be a no-op for every configurable channel.
        results = discovery.auto_assign_application(app_name=app_name)
        for r in results:
            if r["action"] == "skipped-not-configurable":
                continue
            assert r["action"] == "kept", f"Second auto-assign was not idempotent for {r}"
