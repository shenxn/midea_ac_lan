"""Golden vectors from a private Lua oracle, exercised with no Lua dependency."""

# Wire values are explicit evidence; tests access state to assert atomic rejection.
# ruff: file-ignore[magic-value-comparison, any-type, pytest-raises-too-broad]

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from midea_ac_lan.local_models import (
    FreshAir24297131,
    PipeDispenser1046,
    Softener845,
)
from midea_ac_lan.local_protocol import ModelCodec, ac_envelope, frame
from midealan.const import ProtocolVersion

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/local_protocol.json").read_text(),
)
CLASSES = {
    "6360000F": Softener845,
    "6320088A": PipeDispenser1046,
    "24297131": FreshAir24297131,
}


def make_device(case: dict[str, Any]) -> Any:
    """Construct an offline device with a deliberately non-routable test identity."""
    return CLASSES[case["model"]](
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model=case["model"],
        subtype=case["subtype"],
        customize="",
    )


@pytest.mark.parametrize("case", VECTORS["encode"])
def test_encoding_matches_lua_golden(case: dict[str, Any]) -> None:
    """Queries and allowed controls match independently captured Lua outputs."""
    device = make_device(case)
    if "queries" in case:
        assert [q.serialize().hex() for q in device.build_query()] == case["queries"]
        return
    device._vendor_status = dict(case["status"])
    device.build_send = Mock()
    device.set_attribute(case["attribute"], case["value"])
    assert device.build_send.call_args.args[0].serialize().hex() == case["hex"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_decoding_matches_lua_golden(case: dict[str, Any]) -> None:
    """Exposed fields match the oracle for zero, high-bit and random data."""
    device = make_device(case)
    assert device._vendor_codec.decode(bytes.fromhex(case["hex"])) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_truncated_or_corrupt_frames_never_update_state(case: dict[str, Any]) -> None:
    """Reject every truncated prefix and every single-byte corruption atomically."""
    device = make_device(case)
    original = bytes.fromhex(case["hex"])
    device.process_message(original)
    status, attributes = dict(device._vendor_status), dict(device._attributes)
    for length in range(len(original)):
        assert device._vendor_codec.decode(original[:length]) == {}
        device.process_message(original[:length])
        assert device._vendor_status == status
        assert device._attributes == attributes
    for index in range(len(original)):
        bad = bytearray(original)
        bad[index] ^= 1
        assert device._vendor_codec.decode(bytes(bad)) == {}


def test_unknown_ed_records_are_skipped_without_losing_known_fields() -> None:
    """Length-delimited extensions can precede a known status record."""
    codec = ModelCodec(237, 845)
    message = frame(237, 4, bytes.fromhex("ff0109fe3f112233061924"))
    assert codec.decode(message) == {"left_salt": 36}


@pytest.mark.parametrize(
    "body",
    [
        "ff0109061924ff",  # incomplete header after a valid salt record
        "ff01090619240a2901",  # declared value truncated
        "ff01090619240a1901",  # known record shorter than required
    ],
)
def test_malformed_ed_record_discards_the_entire_update(body: str) -> None:
    """Do not apply an earlier valid record when a later record is malformed."""
    assert ModelCodec(237, 845).decode(frame(237, 3, bytes.fromhex(body))) == {}


def test_inner_ac_integrity_is_checked_even_with_a_valid_outer_checksum() -> None:
    """UART integrity does not substitute for the nested JZ length and CRC."""
    codec = ModelCodec(172, 1)
    good = ac_envelope(0x10, bytes(130))
    for index in (0, 1, 6, len(good) - 2, len(good) - 1):
        bad = bytearray(good)
        bad[index] ^= 1
        if index == 6:
            # Also repair the inner additive checksum; its CRC is still wrong.
            bad[-1] = -sum(bad[:-1]) & 0xFF
        assert codec.decode(frame(172, 3, bytes(bad))) == {}


def test_status_types_and_unknown_commands() -> None:
    """Only ED status responses and known AC payload formats can update state."""
    ed = ModelCodec(237, 845)
    for message_type in (2, 5, 6):
        assert ed.decode(frame(237, message_type, bytes.fromhex("ff0109061924"))) == {}
    ac = ModelCodec(172, 1)
    for command in (0, 0x12, 0x30, 0xAB):
        assert ac.decode(frame(172, 3, ac_envelope(command, bytes(130)))) == {}
    for command, payload in (
        (0x10, bytes(8)),
        (0x11, bytes(16)),
        (0xC0, b"\x00\x01\xc0\x03"),
    ):
        assert ac.decode(frame(172, 3, ac_envelope(command, payload))) == {}


def test_partial_ventilation_updates_preserve_other_measurements() -> None:
    """C003 control acknowledgements cannot reset run telemetry or model identity."""
    device = make_device({"model": "24297131", "subtype": 1})
    run = bytearray(130)
    run[7:9] = (2150).to_bytes(2, "little")
    run[58] = 0x10
    run[61:63] = (-125).to_bytes(2, "little", signed=True)
    run[63] = 12
    device.process_message(frame(172, 3, ac_envelope(0x10, bytes(run))))
    status = bytearray(20)
    status[1:5] = b"\x01\xc0\x03\x13"
    status[9:13] = bytes((15, 0x87, 0xA8, 0xBC))
    for message_type in (2, 3, 4, 5):
        device.process_message(
            frame(172, message_type, ac_envelope(0xC0, bytes(status))),
        )
        assert device._vendor_status["special_machine_type"] == 1
        assert device.get_attribute("indoor_temperature") == pytest.approx(21.5)
        assert device.get_attribute("outdoor_temperature") == pytest.approx(-1.25)
        assert device.get_attribute("fresh_filter_remaining") == 88
        assert device.get_attribute("ventilation_preset") == 7
        assert device.get_attribute("fresh_air_fan_speed") == 40
        assert device.get_attribute("fresh_air_exhaust_speed") == 60


@pytest.mark.parametrize(
    ("device_type", "subtype", "control"),
    [
        (237, 845, {"regeneration": "on"}),
        (237, 1046, {"out_water": "on"}),
        (237, 1046, {"heat_start": 1}),
        (237, 1046, {"custom_temperature_other3": 45}),
        (172, 1, {"power": "on"}),
        (172, 1, {"new_wind_single_control": 1, "power": "on"}),
    ],
)
def test_codec_does_not_expose_generic_dangerous_commands(
    device_type: int,
    subtype: int,
    control: dict[str, Any],
) -> None:
    """The low-level encoder also rejects commands outside the native subset."""
    with pytest.raises(ValueError):
        ModelCodec(device_type, subtype).encode("control", control)
