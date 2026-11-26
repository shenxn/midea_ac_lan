"""Read-only 0x10 engineering telemetry tests for fresh-air model 24297131."""

# Byte offsets and captured frames are explicit wire-level evidence.
# ruff: file-ignore[any-type, pytest-raises-too-broad]

from typing import Any

import pytest
from homeassistant.helpers.entity import EntityCategory
from midealan.const import ProtocolVersion

from custom_components.midea_ac_lan.fresh_air_protocol import (
    FRESH_AIR_ENGINEERING_KEYS,
    fresh_air_engineering_status,
)
from custom_components.midea_ac_lan.local_models import FreshAir24297131
from custom_components.midea_ac_lan.local_protocol import ac_envelope, frame
from custom_components.midea_ac_lan.midea_devices import MIDEA_DEVICES
from custom_components.midea_ac_lan.sensor import MideaSensor

# Live 0x10 frames captured from CAX250GC1M (SN8 24297131, subtype 1).
CAPTURED_FRAMES: list[tuple[str, dict[str, Any]]] = [
    (
        "aa82ac00000000000803bb7800ffff10d4f7d4f70000009a060000000000000000000000008000"
        "000000000000000000000200cd0000000000000000000200000000000028a128b10000110d0072"
        "061500000000000000000000000000000040363030303030022830300000000000000000000000"
        "00000050000200000000001f8ac7",
        {
            "fresh_air_exhaust_actual_level": 40,
            "fresh_air_exhaust_fan_rpm_raw": 161,
            "fresh_air_intake_actual_level": 40,
            "fresh_air_intake_fan_rpm_raw": 177,
            "fresh_air_operating_mode": 1,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000803bb7800ffff10d4f7d4f7000000a4060000000000000000000000008000"
        "000000000000000000000200cd00000000000000000002000000000000199950c80000110b00a4"
        "061500000000000000000000000000000040363030303030012430300000000000000000000000"
        "0000004800020000000000a5afc7",
        {
            "fresh_air_exhaust_actual_level": 25,
            "fresh_air_exhaust_fan_rpm_raw": 153,
            "fresh_air_intake_actual_level": 80,
            "fresh_air_intake_fan_rpm_raw": 200,
            "fresh_air_operating_mode": 1,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000805bb7800ffff10d4f7d4f70000009a060000000000000000000000008000"
        "000000000000000000000200cd00000000000000000002000000000000019a019f0000110a0072"
        "061500000000000000000000000000000040363030303030022830300000000000000000000000"
        "000000550002000000000010fec5",
        {
            "fresh_air_exhaust_actual_level": 1,
            "fresh_air_exhaust_fan_rpm_raw": 154,
            "fresh_air_intake_actual_level": 1,
            "fresh_air_intake_fan_rpm_raw": 159,
            "fresh_air_operating_mode": 1,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000805bb7800ffff10d4f7d4f70000009a060000000000000000000000008000"
        "000000000000000000000200cd0000000000000000000200000000000000003cbf0000110b0072"
        "061500000000000000000000000000000040363030303030022830300000000000000000000000"
        "000000570002000000000093b8c5",
        {
            "fresh_air_exhaust_actual_level": 0,
            "fresh_air_exhaust_fan_rpm_raw": 0,
            "fresh_air_intake_actual_level": 60,
            "fresh_air_intake_fan_rpm_raw": 191,
            "fresh_air_operating_mode": 1,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000803bb7800ffff10d4f7d4f7000000a4060000000000000000000000008000"
        "000000000000000000000200cd000000000000000000020000000000006ec76eda0000170e00a4"
        "061500000000000000000000000000000040363030303030012430300000000000000000000000"
        "0000004b00020000000000b8ddc7",
        {
            "fresh_air_exhaust_actual_level": 110,
            "fresh_air_exhaust_fan_rpm_raw": 199,
            "fresh_air_intake_actual_level": 110,
            "fresh_air_intake_fan_rpm_raw": 218,
            "fresh_air_operating_mode": 7,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000803bb7800ffff10d4f7d4f700000090060000000000000000000000008000"
        "000000000000000000000200cd0000000000000000000200000000000064be64d20000140a0072"
        "061500000000000000000000000000000040363030303030022830300000000000000000000000"
        "000000510002000000000003f9c7",
        {
            "fresh_air_exhaust_actual_level": 100,
            "fresh_air_exhaust_fan_rpm_raw": 190,
            "fresh_air_intake_actual_level": 100,
            "fresh_air_intake_fan_rpm_raw": 210,
            "fresh_air_operating_mode": 4,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
    (
        "aa82ac00000000000805bb7800ffff10d4f7d4f700000090060000000000000000000000008000"
        "000000000000000000000200cd0000000000000000000200000000000064be64d20000180d0072"
        "061500000000000000000000000000000040363030303030022830300000000000000000000000"
        "00000052000200000000004fa5c5",
        {
            "fresh_air_exhaust_actual_level": 100,
            "fresh_air_exhaust_fan_rpm_raw": 190,
            "fresh_air_intake_actual_level": 100,
            "fresh_air_intake_fan_rpm_raw": 210,
            "fresh_air_operating_mode": 8,
            "fresh_air_fault": "正常",
            "fresh_air_protection": "正常",
        },
    ),
]


def _make_fresh_air() -> FreshAir24297131:
    """Create an offline CAX250GC1M adapter."""
    return FreshAir24297131(
        name="新风",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model="24297131",
        subtype=1,
        customize="",
    )


def _build_run_frame(payload: bytearray) -> bytes:
    """Wrap a 0x10 running-status payload with valid nested CRC and checksum."""
    return frame(0xAC, 3, ac_envelope(0x10, bytes(payload)))


@pytest.mark.parametrize(("hex_frame", "expected"), CAPTURED_FRAMES)
def test_captured_fresh_air_engineering_frames(
    hex_frame: str,
    expected: dict[str, Any],
) -> None:
    """Captured CAX250GC1M 0x10 frames decode exact levels, RPMs, mode and health."""
    raw = bytes.fromhex(hex_frame)
    assert fresh_air_engineering_status(raw) == expected
    device = _make_fresh_air()
    parsed = device.process_message(raw)
    for key, value in expected.items():
        assert parsed[key] == value
        assert device.get_attribute(key) == value


@pytest.mark.parametrize(
    ("mutations", "expected_fault"),
    [
        ({16: 0x10}, "风机失速"),
        ({94: 0x01}, "风机故障"),
        ({16: 0x02}, "温度传感器故障"),
        ({21: 0x10}, "温度传感器故障"),
        ({94: 0x20}, "温度传感器故障"),
        ({16: 0x40}, "主板参数故障"),
        ({94: 0x80}, "主板参数故障"),
        ({15: 0x01}, "通信故障"),
        ({22: 0x02}, "通信故障"),
        ({16: 0x12, 94: 0x01}, "风机失速、风机故障、温度传感器故障"),
    ],
)
def test_fresh_air_fault_bits(
    mutations: dict[int, int],
    expected_fault: str,
) -> None:
    """Each hardware-relevant fault bit maps to its Chinese label."""
    payload = bytearray(112)
    for offset, value in mutations.items():
        payload[offset] = value
    parsed = fresh_air_engineering_status(_build_run_frame(payload))
    assert parsed["fresh_air_fault"] == expected_fault
    assert parsed["fresh_air_protection"] == "正常"


@pytest.mark.parametrize(
    ("mutations", "expected_protection"),
    [
        ({18: 0x20}, "室外低温保护"),
        ({94: 0x04}, "室外低温保护"),
        ({18: 0x10}, "防凝露保护"),
        ({94: 0x02}, "防凝露保护"),
        ({21: 0x02}, "低温防凝露保护"),
        ({18: 0x40}, "室外高温保护"),
        ({94: 0x08}, "室外高温保护"),
        ({106: 2, 108: 0x04}, "除霜"),
        ({106: 1, 108: 0x04}, "正常"),
        ({18: 0x30, 106: 2, 108: 0x04}, "室外低温保护、防凝露保护、除霜"),
    ],
)
def test_fresh_air_protection_bits(
    mutations: dict[int, int],
    expected_protection: str,
) -> None:
    """Protection and target-gated defrost flags map cleanly without false positives."""
    payload = bytearray(112)
    for offset, value in mutations.items():
        payload[offset] = value
    parsed = fresh_air_engineering_status(_build_run_frame(payload))
    assert parsed["fresh_air_protection"] == expected_protection
    assert parsed["fresh_air_fault"] == "正常"


def test_fresh_air_engineering_boundaries_and_readonly() -> None:
    """Unknown before first 0x10, atomic on corruption, and strictly read-only."""
    device = _make_fresh_air()
    for key in FRESH_AIR_ENGINEERING_KEYS:
        assert device.get_attribute(key) is None
        with pytest.raises(ValueError, match="Unsupported"):
            device.set_attribute(key, 1)

    # Short 0x10 payloads and non-0x10 commands must not invent fields.
    assert fresh_air_engineering_status(_build_run_frame(bytearray(9))) == {}
    assert fresh_air_engineering_status(_build_run_frame(bytearray(22))) == {
        "fresh_air_protection": "正常",
    }
    assert fresh_air_engineering_status(_build_run_frame(bytearray(56))) == {
        "fresh_air_protection": "正常",
        "fresh_air_fault": "正常",
        "fresh_air_exhaust_actual_level": 0,
        "fresh_air_exhaust_fan_rpm_raw": 0,
        "fresh_air_intake_actual_level": 0,
        "fresh_air_intake_fan_rpm_raw": 0,
    }
    assert fresh_air_engineering_status(frame(0xAC, 3, ac_envelope(0x11, bytes(64)))) == {}

    # Truncated, outer-corrupt, or inner-envelope-corrupt frames are rejected atomically.
    good = bytes.fromhex(CAPTURED_FRAMES[0][0])
    assert fresh_air_engineering_status(good[:-1]) == {}
    bad = bytearray(good)
    bad[20] ^= 1
    assert fresh_air_engineering_status(bytes(bad)) == {}
    bad_inner = bytearray(ac_envelope(0x10, bytes(64)))
    bad_inner[-2] ^= 1
    assert fresh_air_engineering_status(frame(0xAC, 3, bytes(bad_inner))) == {}


def test_fresh_air_engineering_entities_are_diagnostic_and_model_scoped() -> None:
    """All 7 engineering entities default on for 24297131/1 as diagnostic sensors."""
    device = _make_fresh_air()
    entities = MIDEA_DEVICES[172]["entities"]
    for key in FRESH_AIR_ENGINEERING_KEYS:
        config = entities[key]
        assert config["models"] == ["24297131"]
        assert config["subtypes"] == [1]
        assert config["default"] is True
        sensor = MideaSensor(device, key)
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC
