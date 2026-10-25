"""Model-specific settings checked against independent vendor wire vectors."""

# ruff: file-ignore[magic-value-comparison, any-type, pytest-raises-too-broad]

import hashlib
import json
from datetime import time
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from midea_ac_lan.local_models import Softener845
from midea_ac_lan.local_protocol import ModelCodec, frame
from midea_ac_lan.time import MideaTime
from midealan.const import ProtocolVersion

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/softener_extensions.json").read_text(),
)


@pytest.fixture
def device() -> Any:
    """Build an offline model with no household identifiers or credentials."""
    result = Softener845(
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model="6360000F",
        subtype=845,
        customize="",
    )
    result.build_send = Mock()
    return result


@pytest.mark.parametrize("case", VECTORS["encode"])
def test_vendor_control_vectors(case: dict[str, Any]) -> None:
    """Every protection choice and representative times match the vendor codec."""
    assert ModelCodec(237, 845).encode("control", case["control"]) == case["hex"]


def test_all_1440_time_settings_match_vendor_digest() -> None:
    """Both time bytes, including zero, must survive the complete clock range."""
    codec = ModelCodec(237, 845)
    packets = b"".join(
        bytes.fromhex(
            codec.encode(
                "control",
                {"timing_regeneration_hour": h, "timing_regeneration_min": m},
            ),
        )
        for h in range(24)
        for m in range(60)
    )
    assert hashlib.sha256(packets).hexdigest() == VECTORS["time_digest"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_vendor_telemetry_and_corruption(case: dict[str, Any]) -> None:
    """Extra telemetry matches the oracle and corrupt packets remain rejected."""
    codec = ModelCodec(237, 845)
    packet = bytes.fromhex(case["hex"])
    assert codec.decode(packet) == case["expected"]
    for length in range(len(packet)):
        assert codec.decode(packet[:length]) == {}
    for index in range(len(packet)):
        corrupt = bytearray(packet)
        corrupt[index] ^= 1
        assert codec.decode(bytes(corrupt)) == {}


def test_time_entity_sends_one_atomic_command(device: Any) -> None:
    """A time edit sends one packet, preventing the second field reverting first."""
    device._vendor_status = {
        "timing_regeneration_hour": 2,
        "timing_regeneration_min": 0,
    }
    item = object.__new__(MideaTime)
    item._config = {"combined_attribute": "f08_regeneration_time"}
    item._device = device
    item.set_value(time(23, 59))
    device.build_send.assert_called_once()
    packet = device.build_send.call_args.args[0].serialize()
    assert packet[10:-1] == bytes.fromhex("150101020900173b")
    assert device._vendor_status["timing_regeneration_hour"] == 2
    with pytest.raises(ValueError):
        item.set_value(time(23, 59, 1))
    assert device.build_send.call_count == 1


@pytest.mark.parametrize(
    ("attribute", "value", "body"),
    [
        ("f08_leak_protection_setting", 950, "1501010909015f00"),
        ("f08_leak_protection_setting", 0, "1501010909000000"),
        ("f08_micro_leak_setting", 90, "1501010a09015a00"),
        ("f08_micro_leak_setting", 0, "1501010a09000000"),
        ("f08_flushing_days", 30, "1501010109001e00"),
        ("f08_water_hardness", 30, "1501010009001e00"),
    ],
)
def test_setting_units_and_no_optimistic_update(
    device: Any,
    attribute: str,
    value: int,
    body: str,
) -> None:
    """UI units convert once and each setting occupies exactly one command."""
    device._vendor_status = {"ready": True}
    device.set_attribute(attribute, value)
    assert device.build_send.call_args.args[0].serialize()[10:-1].hex() == body
    assert device._vendor_status == {"ready": True}


def test_partial_protection_reports_and_missing_data(device: Any) -> None:
    """A threshold-only report retains the last actual protection flag."""
    device.process_message(frame(237, 3, bytes.fromhex("ff010909295f5a")))
    assert device.get_attribute("f08_leak_protection_setting") is None
    device.process_message(frame(237, 3, bytes.fromhex("ff0109111918")))
    assert device.get_attribute("f08_leak_protection_setting") == 950
    assert device.get_attribute("f08_micro_leak_setting") == 90
    device.process_message(frame(237, 3, bytes.fromhex("ff01090929140a")))
    assert device.get_attribute("f08_leak_protection_setting") == 200
    device.process_message(frame(237, 3, bytes.fromhex("ff0109111900")))
    assert device.get_attribute("f08_leak_protection_setting") == 0


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("regeneration_time", "24:00"),
        ("regeneration_time", "12:00:01"),
        ("regeneration_time", "12:00+08:00"),
        ("regeneration_time", 123),
        ("leak_protection_setting", True),
        ("leak_protection_setting", 201),
        ("micro_leak_setting", 95),
        ("flushing_days", 31),
        ("water_hardness", 29),
        ("regeneration", True),
        ("holiday_mode", True),
    ],
)
def test_unsupported_settings_send_nothing(
    device: Any,
    attribute: str,
    value: Any,
) -> None:
    """Invalid settings and unverified actions never reach LAN transport."""
    device._vendor_status = {"ready": True}
    with pytest.raises(ValueError):
        device.set_attribute(attribute, value)
    device.build_send.assert_not_called()


@pytest.mark.parametrize(
    "control",
    [
        {"timing_regeneration_hour": 2},
        {"timing_regeneration_hour": 2, "timing_regeneration_min": 60},
        {"timing_regeneration_hour": True, "timing_regeneration_min": 0},
        {"leak_water_protection": "on", "leak_water_protection_value": 19},
        {"micro_leak_protection": "off", "micro_leak_protection_value": 10},
        {"micro_leak_protection": "on", "micro_leak_protection_value": True},
    ],
)
def test_incomplete_or_invalid_coupled_commands(control: dict[str, Any]) -> None:
    """The codec rejects incomplete pairs even if called without the adapter."""
    with pytest.raises(ValueError):
        ModelCodec(237, 845).encode("control", control)


def test_protection_controls_exist_before_first_poll(device: Any) -> None:
    """HA platform setup must see derived attributes before status arrives."""
    for key in ("f08_leak_protection_setting", "f08_micro_leak_setting"):
        assert key in device.attributes
        assert device.get_attribute(key) is None


def test_time_entity_refreshes_from_reported_clock_fields(device: Any) -> None:
    """The combined setter key is not a wire field; watch the 090C clock report."""
    item = MideaTime(device, "f08_regeneration_time")
    item.hass = Mock()
    item.schedule_update_if_running = Mock()
    status = device.process_message(frame(237, 3, bytes.fromhex("ff01090c4900000201")))
    item.update_state(status)
    item.schedule_update_if_running.assert_called_once()
    assert item.native_value == time(2, 1)
    item.schedule_update_if_running.reset_mock()
    item.update_state({"f08_left_salt": 36})
    item.schedule_update_if_running.assert_not_called()
