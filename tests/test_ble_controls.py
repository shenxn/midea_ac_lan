"""Regressions for exact-model BLE control payloads and state-dependent writes."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, pytest-raises-too-broad, import-outside-top-level]
from typing import Any

import pytest

from custom_components.midea_ac_lan.ble.appliances import DISH, HEATER, HOOD
from custom_components.midea_ac_lan.ble.controls import command, group, matches


def test_heater_catalog_matches_exact_model_and_companion_duration() -> None:
    """Verify 5111102Z heater controls match the App and carry hold duration."""
    heater = group(HEATER)
    for removed in (
        "cold_water_ai",
        "cold_water",
        "bubble",
        "bathtub",
        "safe",
        "change_litre_switch",
        "person_mode_one",
        "person_mode_two",
        "person_mode_three",
        "high_temp_lock",
    ):
        assert removed not in heater
    assert heater["cold_water_master"]["name"] == "单次零冷水"
    assert heater["cold_water_pressure"]["name"] == "瀑布畅洗"
    assert list(heater["mode"]["commands"]) == ["标准洗", "婴儿浴", "ECO"]
    assert command(HEATER, "mode", "标准洗", {})[10:13] == bytes.fromhex("140202")
    assert command(HEATER, "mode", "婴儿浴", {})[10:14] == bytes.fromhex("14020020")
    assert command(HEATER, "mode", "ECO", {})[10:14] == bytes.fromhex("14020002")
    assert command(HEATER, "water_heater", "32", {})[10:13] == bytes.fromhex("140820")
    assert command(HEATER, "water_heater", "65", {})[10:13] == bytes.fromhex("140841")
    for invalid_temp in ("20", "31", "66"):
        with pytest.raises(ValueError, match="Unsupported"):
            command(HEATER, "water_heater", invalid_temp, {})
    assert command(HEATER, "cold_water_conservation", "节能零冷水", {})[
        10:14
    ] == bytes.fromhex("14160100")
    assert command(
        HEATER,
        "cold_water_conservation",
        "保温零冷水",
        {"cold_hold_duration": "30"},
    )[10:14] == bytes.fromhex("1416001e")
    for bad_obs in ({}, {"cold_hold_duration": "4"}, {"cold_hold_duration": "251"}):
        with pytest.raises(ValueError, match="companion"):
            command(HEATER, "cold_water_conservation", "保温零冷水", bad_obs)
    assert command(HEATER, "cold_hold_duration", "5", {})[10:14] == bytes.fromhex(
        "14160005",
    )
    assert command(HEATER, "cold_hold_duration", "250", {})[10:14] == bytes.fromhex(
        "141600fa",
    )
    for bad_dur in ("4", "251"):
        with pytest.raises(ValueError, match="Unsupported"):
            command(HEATER, "cold_hold_duration", bad_dur, {})
    assert command(HEATER, "new_filter_reset", "press", {})[10:13] == bytes.fromhex(
        "142901",
    )
    assert matches(
        "cold_hold_duration",
        "30",
        {"cold_hold_duration": "30", "cold_water_conservation": "保温零冷水"},
    )
    assert not matches(
        "cold_hold_duration",
        "30",
        {"cold_hold_duration": "30", "cold_water_conservation": "节能零冷水"},
    )
    assert matches("new_filter_reset", "press", {"new_filter_reset": "normal"})
    assert not matches("new_filter_reset", "press", {"new_filter_reset": "abnormal"})


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
            dep = spec.get("include") or spec.get("include_for", {}).get(opt)
            observed = {dep[0]: 45} if dep else {}
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
    for size in (22, 30, 42):
        body = bytearray(size)
        body[6] = 42
        body[2] = 8
        values = status_fields(HEATER, report(HEATER, body))
        assert values["water_heater"] == "42"
        assert values["mode"] == "标准洗"
        body[2] = 0
        for flag, expected in ((1, "ECO"), (16, "婴儿浴")):
            body[16] = flag
            assert status_fields(HEATER, report(HEATER, body))["mode"] == expected
        if size >= 42:
            body[28] = 64
            body[30] = 30
            body[40] = 8
            values = status_fields(HEATER, report(HEATER, body))
            assert values["cold_water_conservation"] == "节能零冷水"
            assert values["cold_hold_duration"] == "30"
            assert values["new_filter_reset"] == "abnormal"
            body[28] = 0
            body[40] = 0
            values = status_fields(HEATER, report(HEATER, body))
            assert values["cold_water_conservation"] == "保温零冷水"
            assert values["new_filter_reset"] == "normal"
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
