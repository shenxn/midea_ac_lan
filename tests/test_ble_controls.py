"""Regressions for exact-model BLE control payloads and state-dependent writes."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, pytest-raises-too-broad, import-outside-top-level]
from typing import Any

import pytest

from custom_components.midea_ac_lan.ble.appliances import DISH, HEATER, HOOD
from custom_components.midea_ac_lan.ble.controls import command, group, matches


def test_personal_mode_carries_latest_temperature() -> None:
    """Verify personal mode carries latest temperature."""
    assert command(HEATER, "person_mode_two", "on", {"person_tem_two": 43})[
        10:14
    ] == bytes.fromhex("140c012b")
    with pytest.raises(ValueError, match="companion"):
        command(HEATER, "bathtub", "on", {})
    with pytest.raises(ValueError, match="companion"):
        command(HEATER, "bathtub", "on", {"bathtub_water_level": 300})


def test_hood_setting_does_not_change_fan() -> None:
    """Verify hood setting does not change fan."""
    assert (
        command(HOOD, "lightness", "35", {}).hex()
        == "aa12b60000000000000211010202ff23ffff00"
    )
    with pytest.raises(ValueError):
        command(HOOD, "lightness", "37", {})


def test_dishwasher_does_not_offer_cycle_start() -> None:
    """Verify dishwasher does not offer cycle start."""
    for key, spec in group(DISH).items():
        for value in spec["commands"]:
            frame = command(DISH, key, value, {})
            assert frame[10:12] not in {b"\x08\x03", b"\x83\x01", b"\x08\x02"}
    assert matches("work_status", "pause", {"operator_paused": True})


@pytest.mark.parametrize("device", [DISH, HOOD, HEATER])
def test_all_catalog_packets_have_exact_size_and_checksum(device: Any) -> None:
    """Verify all catalog packets have exact size and checksum."""
    for key, spec in group(device).items():
        for opt in spec["commands"]:
            observed = {spec["include"][0]: 45} if spec.get("include") else {}
            frame = command(device, key, opt, observed)
            assert frame[9] == 2
            assert frame[2] == device.kind
            assert frame[1] + 1 == len(frame)
            assert sum(frame[1:]) % 256 == 0


def test_cycle_start_needs_explicit_opt_in_at_wire_boundary() -> None:
    """Verify cycle start needs explicit opt in at wire boundary."""
    with pytest.raises((ValueError, KeyError)):
        command(DISH, "wash_mode", "eco_wash", {})
    with pytest.raises(ValueError):
        command(DISH, "work_status", "resume", {})
    assert command(DISH, "wash_mode", "eco_wash", {}, allow_cycle=True)[
        10:13
    ] == bytes.fromhex("080304")
    assert command(DISH, "work_status", "resume", {}, allow_cycle=True)[
        10:12
    ] == bytes.fromhex("8301")


def test_readback_status_fields_and_matching() -> None:
    """Verify readback status fields and matching."""
    from custom_components.midea_ac_lan.ble.controls import status_fields
    from custom_components.midea_ac_lan.ble.protocol import signed

    def report(device: Any, body: Any) -> Any:
        """Apply report."""
        return b"\xaa" + signed(
            bytes([len(body) + 10, device.kind, 0, 0, 0, 0, 0, 2, 3]) + body,
        )

    for state in (0, 1, 3, 9):
        for flags in (0, 255, 32):
            body = bytearray(62)
            body[1] = state
            body[2] = 4
            body[4] = body[5] = body[61] = flags
            values = status_fields(DISH, report(DISH, body))
            assert values["operator_started"] == bool(flags & 8)
            assert values["waterswitch"] == ("on" if flags & 4 else "off")
    assert "knock_sensor_door_action" not in status_fields(
        DISH,
        report(DISH, bytes(39)),
    )
    for size in (22, 25, 30):
        body = bytearray(size)
        for offset in (2, 16):
            for flag in (0, 1, 2, 4, 8, 16, 32, 64, 128):
                body[offset] = flag
                values = status_fields(HEATER, report(HEATER, body))
                assert "water_heater" in values
        body[2] = 0
        for flag in (1, 2, 4, 8, 16, 32, 64):
            body[16] = flag
            assert "mode" in status_fields(HEATER, report(HEATER, body))
    for mode in range(6):
        for kind in (1, 2, 3):
            values = status_fields(
                HOOD,
                report(HOOD, b"\x11\x02\x03" + bytes([kind, mode, 0])),
            )
            assert values[
                ("left_stove_off", "right_stove_off", "middle_stove_off")[kind - 1]
            ] == ("off" if mode < 2 else "working" if mode < 5 else None)
    assert status_fields(HOOD, report(HOOD, b"\x11\x02\xff")) == {}
    for enabled in (0, 1, 2):
        values = status_fields(HOOD, report(HOOD, b"\x11\x09\x01" + bytes([enabled])))
        assert ("ai_butler" in values) == (enabled < 2)
    for length in (1, 3, 8, 14, 52):
        for fill in (0, 8, 13, 255):
            values = status_fields(
                HOOD,
                report(HOOD, b"\x11\x01" + bytes([length]) + bytes([fill]) * length),
            )
            assert isinstance(values, dict)
    assert matches("work_status", "resume", {"operator_started": True})
    assert matches("work_status", "power_on", {"work_status": "cancel"})
    assert matches("work_status", "cancel", {"work_status": "cancel"})
    assert matches("left_stove_off", "press", {"left_stove_off": "off"})
    assert not matches("power", "on", {})
