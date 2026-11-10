"""Regressions for exact-model BLE control payloads and state-dependent writes."""

import pytest
from midea_ac_lan.ble.appliances import DISH, HEATER, HOOD
from midea_ac_lan.ble.controls import command, group, matches


def test_personal_mode_carries_latest_temperature():
    assert command(HEATER, "person_mode_two", "on", {"person_tem_two": 43})[
        10:14
    ] == bytes.fromhex("140c012b")
    with pytest.raises(ValueError, match="companion"):
        command(HEATER, "bathtub", "on", {})
    with pytest.raises(ValueError, match="companion"):
        command(HEATER, "bathtub", "on", {"bathtub_water_level": 300})


def test_hood_setting_does_not_change_fan():
    assert (
        command(HOOD, "lightness", "35", {}).hex()
        == "aa12b60000000000000211010202ff23ffff00"
    )
    with pytest.raises(ValueError):
        command(HOOD, "lightness", "37", {})


def test_dishwasher_does_not_offer_cycle_start():
    for key, spec in group(DISH).items():
        for value in spec["commands"]:
            frame = command(DISH, key, value, {})
            assert frame[10:12] not in (b"\x08\x03", b"\x83\x01", b"\x08\x02")
    assert matches("work_status", "pause", {"operator_paused": True})


@pytest.mark.parametrize("device", [DISH, HOOD, HEATER])
def test_all_catalog_packets_have_exact_size_and_checksum(device):
    for key, spec in group(device).items():
        for opt in spec["commands"]:
            observed = {spec["include"][0]: 45} if spec.get("include") else {}
            frame = command(device, key, opt, observed)
            assert frame[9] == 2 and frame[2] == device.kind
            assert frame[1] + 1 == len(frame) and sum(frame[1:]) % 256 == 0


def test_cycle_start_needs_explicit_opt_in_at_wire_boundary():
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
