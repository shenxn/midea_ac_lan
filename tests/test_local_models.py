"""Offline model, safety, state mapping and optional packet regressions."""

# Byte offsets and literals are the protocol evidence these tests assert.
# ruff: file-ignore[magic-value-comparison, any-type, pytest-raises-too-broad, import-outside-top-level, too-many-arguments, too-many-positional-arguments]

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from midea_ac_lan import local_models as models
from midealan.const import ProtocolVersion

ROOT = Path(__file__).resolve().parents[1]
Softener845 = models.Softener845
FreshAir24297131 = models.FreshAir24297131
PipeDispenser1046 = models.PipeDispenser1046
VendorFrame = models.VendorFrame

SOFT_STATUS = {"soften": "on", "water_hardness": 180, "flushing_days": 0}
FRESH_STATUS = {
    "special_machine_type": 1,
    "new_wind_machine": 1,
    "new_wind_machine_intake_switch": 1,
    "new_wind_machine_exhaust_switch": 1,
    "fresh_air_intake_fan_speed": 40,
    "fresh_air_exhaust_fan_speed": 40,
    "fresh_air_mode": 7,
}
PIPE_STATUS = {
    "custom_temperature_1": 45,
    "custom_temperature_2": 99,
    "custom_temperature_3": 99,
    "quantify_1": 15,
    "quantify_2": 30,
    "quantify_3": 50,
    "human_sensing_switch": "on",
    "input_temperature_Sensing": 22,
    "standby_status": 1,
    "water_consumption": 409,
}


def make(cls: Any, model: str, subtype: int) -> Any:
    """Make."""
    return cls(
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model=model,
        subtype=subtype,
        customize="",
    )


def test_queries() -> None:
    """Queries."""
    for cls, model, subtype in [
        (Softener845, "6360000F", 845),
        (FreshAir24297131, "24297131", 1),
    ]:
        d = make(cls, model, subtype)
        assert all(q.serialize()[9] == 3 for q in d.build_query())
        assert not d.build_init_query()


def test_soft_ff_vendor_fixture() -> None:
    """Soft ff vendor fixture."""
    d = make(Softener845, "6360000F", 845)
    # Actual vendor record identifiers, little endian; 0x902, 0x903, 0x906, 0x911.
    body = bytes.fromhex("ff01090249b40500000349af00000006192411192d")
    frame = bytearray([170, 0, 237, 0, 0, 0, 0, 0, 0, 3]) + body
    frame.append((-sum(frame[1:]) - len(frame)) % 256)
    frame[1] = len(frame) - 1
    parsed = d.process_message(bytes(frame))
    assert parsed["f08_soft_available_big"] == 1460
    assert parsed["f08_water_consumption_big"] == 175
    assert parsed["f08_left_salt"] == 36
    assert parsed["f08_holiday_mode"] is True
    assert parsed["f08_cl_sterilization"] is True
    assert parsed["f08_regeneration"] is False


def test_soft_controls() -> None:
    """Soft controls."""
    d = make(Softener845, "6360000F", 845)
    d._vendor_status = dict(SOFT_STATUS)
    d.build_send = Mock()
    d.set_attribute("f08_soften", True)
    frame = d.build_send.call_args.args[0].serialize()
    assert frame[9] == 2
    assert frame[10:13] == bytes.fromhex("150101")
    assert d.get_attribute("f08_soften") is None  # no optimistic state
    with pytest.raises(ValueError):
        d.set_attribute("regeneration", True)
    with pytest.raises(ValueError):
        d.set_attribute("f08_soften", "off")


def test_fresh_control_mask() -> None:
    """Fresh control mask."""
    d = make(FreshAir24297131, "24297131", 1)
    d._vendor_status = dict(FRESH_STATUS)
    d.build_send = Mock()
    d.set_attribute("fresh_air_fan_speed", 40)
    frame = d.build_send.call_args.args[0].serialize()
    # Embedded C003 command identifies dedicated ventilation, not AC thermostat.
    assert bytes.fromhex("01c00313") in frame
    start = frame.index(bytes.fromhex("01c00313")) + 4
    assert frame[start + 2] == 4  # intake switch only, no exhaust or master bit
    assert frame[start + 3] == 4
    assert frame[start + 5] == 168  # speed 40 with enable bit
    assert frame[start + 6] == 0  # exhaust untouched
    with pytest.raises(ValueError):
        d.set_attribute("fresh_air_fan_speed", 101)
    with pytest.raises(ValueError):
        d.set_attribute("power", True)


def test_fresh_mapping() -> None:
    """Fresh mapping."""
    d = make(FreshAir24297131, "24297131", 1)
    status = dict(FRESH_STATUS)
    parsed = d._map_status(status)
    assert parsed["ventilation_power"] is True
    assert parsed["fresh_air_power"] is True
    assert parsed["fresh_air_exhaust_power"] is True
    assert parsed["fresh_air_fan_speed"] == 40
    assert parsed["fresh_air_exhaust_speed"] == 40
    assert parsed["ventilation_mode"] == 7


def test_soft_units_and_ranges() -> None:
    """Soft units and ranges."""
    d = make(Softener845, "6360000F", 845)
    assert (
        d._map_status({"leak_water_protection_value": 95})[
            "f08_leak_water_protection_value"
        ]
        == 950
    )
    d._vendor_status = dict(SOFT_STATUS)
    d.build_send = Mock()
    for attr, value in [
        ("water_hardness", 0),
        ("water_hardness", 1000),
        ("flushing_days", 31),
    ]:
        with pytest.raises(ValueError):
            d.set_attribute(attr, value)


def test_fresh_dedicated_modes_and_mask() -> None:
    """Fresh dedicated modes and mask."""
    d = make(FreshAir24297131, "24297131", 1)
    d._vendor_status = dict(FRESH_STATUS)
    d.build_send = Mock()
    for mode in (1, 4, 7, 8):
        d.set_attribute("ventilation_preset", mode)
        frame = d.build_send.call_args.args[0].serialize()
        start = frame.index(bytes.fromhex("01c00313")) + 4
        assert frame[start + 4] == 128 + mode
        assert frame[start + 2 : start + 4] == bytes(2)  # no switch writes
        assert frame[start + 5 : start + 7] == bytes(2)  # no speed writes
    assert d.get_attribute("ventilation_preset") is None
    for invalid_mode in (2, 3, 5, 6, 0, True, "auto"):
        with pytest.raises(ValueError):
            d.set_attribute("ventilation_preset", invalid_mode)
    d._vendor_status["special_machine_type"] = 0
    with pytest.raises(ValueError):
        d.set_attribute("ventilation_preset", 1)


def test_fresh_filter_life_and_mode_readback() -> None:
    """Fresh filter life and mode readback."""
    d = make(FreshAir24297131, "24297131", 1)
    parsed = d._map_status({"fresh_air_mode": 7, "fresh_filter_time": 2})
    assert parsed["ventilation_preset"] == 7
    assert parsed["fresh_filter_remaining"] == 98
    assert d._map_status({"fresh_filter_time": -1})["fresh_filter_remaining"] is None


def test_pipeline_mapping_and_query() -> None:
    """Pipeline mapping and query."""
    d = make(PipeDispenser1046, "6320088A", 1046)
    assert d.build_query()[0].serialize()[9] == 3
    data = dict(PIPE_STATUS)
    p = d._map_status(data)
    assert p["a1_custom_temperature_1"] == 45
    assert p["a1_custom_temperature_2"] == 99
    assert p["a1_quantify_1"] == 150
    assert p["a1_quantify_2"] == 300
    assert p["a1_quantify_3"] == 500
    assert p["a1_human_sensing_switch"] is True
    assert p["input_temperature_sensing"] == 22
    assert p["standby_status"] is True
    assert p["water_consumption"] == pytest.approx(0.409)


def test_pipeline_single_setting_packets() -> None:
    """Pipeline single setting packets."""
    d = make(PipeDispenser1046, "6320088A", 1046)
    d._vendor_status = dict(PIPE_STATUS)
    d.build_send = Mock()
    for attr, value, tag in [
        ("a1_screenout_time", 60, bytes.fromhex("0801")),
        ("a1_quantify_1", 100, bytes.fromhex("0202")),
        ("a1_custom_temperature_1", 44, bytes.fromhex("0104")),
        ("a1_cur_quantify", 2, bytes.fromhex("0d02")),
    ]:
        d.set_attribute(attr, value)
        b = d.build_send.call_args.args[0].serialize()[10:-1]
        assert b[:3] == bytes.fromhex("150101")  # exactly one TLV command
        assert b[3:5] == tag
    assert d.get_attribute("a1_custom_temperature_1") is None
    for attr, value in [
        ("a1_quantify_1", 200),
        ("a1_custom_temperature_1", 46),
        ("a1_custom_temperature_2", 100),
        ("a1_screenout_time", 0),
        ("a1_cur_quantify", 21),
        ("out_hot_water", True),
        ("drainage", True),
        ("germicidal", True),
        ("cool", True),
    ]:
        with pytest.raises(ValueError):
            d.set_attribute(attr, value)


def test_model_exclusions_do_not_mutate_shared_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model exclusions do not mutate shared lists."""
    import enum
    import types

    class Platform(enum.StrEnum):
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        SWITCH = "switch"
        NUMBER = "number"
        SELECT = "select"
        TIME = "time"

    fake = types.ModuleType("homeassistant.const")
    fake.Platform = Platform  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant", types.ModuleType("homeassistant"))
    monkeypatch.setitem(sys.modules, "homeassistant.const", fake)
    spec = importlib.util.spec_from_file_location(
        "local_entities_test",
        ROOT / "custom_components/midea_ac_lan/local_entities.py",
    )
    assert spec is not None
    assert spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    shared: list[tuple[str, int]] = []
    ds = {
        172: {"entities": {"climate": {"excluded_devices": shared}}},
        237: {
            "entities": {
                key: {"excluded_devices": shared}
                for key in [
                    "power",
                    "child_lock",
                    "cur_quantify",
                    "water_consumption",
                    "water_kind",
                    "no_obsolete_water_mode",
                    "heat_start",
                ]
            },
        },
    }
    m.register_local_entities(ds)
    assert shared == []
    assert ds[237]["entities"]["power"]["excluded_devices"] == []
    assert ds[237]["entities"]["child_lock"]["excluded_devices"] == []
    assert ds[237]["entities"]["cur_quantify"]["excluded_devices"] == [
        ("6320088A", 1046),
    ]


@pytest.mark.parametrize(
    ("cls", "model", "subtype", "attribute", "value", "expected"),
    [
        (Softener845, "6360000F", 845, "f08_soften", False, {"soften": "off"}),
        (Softener845, "6360000F", 845, "water_hardness", 999, {"water_hardness": 999}),
        (Softener845, "6360000F", 845, "flushing_days", 0, {"flushing_days": 0}),
        (PipeDispenser1046, "6320088A", 1046, "a1_quantify_3", 700, {"quantify_3": 70}),
        (
            PipeDispenser1046,
            "6320088A",
            1046,
            "a1_cur_quantify",
            0,
            {"cur_quantify": 0},
        ),
        (PipeDispenser1046, "6320088A", 1046, "child_lock", True, {"lock": "on"}),
        (
            PipeDispenser1046,
            "6320088A",
            1046,
            "a1_human_sensing_switch",
            False,
            {"human_sensing_switch": "off"},
        ),
    ],
)
def test_control_mapping(
    cls: Any,
    model: str,
    subtype: int,
    attribute: str,
    value: Any,
    expected: Any,
) -> None:
    """Control mapping."""
    device = make(cls, model, subtype)
    device._send_control = Mock()
    device.set_attribute(attribute, value)
    device._send_control.assert_called_once_with(expected)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("out_water", True),
        ("out_hot_water", True),
        ("heat_start", 1),
        ("drainage", True),
        ("cool", True),
        ("germicidal", True),
        ("a1_cur_quantify", 21),
        ("a1_quantify_1", 200),
        ("a1_custom_temperature_1", 46),
        ("a1_custom_temperature_2", 100),
        ("a1_screenout_time", 0),
        ("a1_screenout_time", True),
        ("a1_quantify_2", 150.5),
    ],
)
def test_pipe_rejects_unverified_commands(attribute: str, value: Any) -> None:
    """Pipe rejects unverified commands."""
    device = make(PipeDispenser1046, "6320088A", 1046)
    device._send_control = Mock()
    with pytest.raises(ValueError):
        device.set_attribute(attribute, value)
    device._send_control.assert_not_called()


@pytest.mark.parametrize(
    ("attribute", "value"),
    [("regeneration", True), ("soften", "off"), ("water_hardness", True)],
)
def test_softener_rejects_unsafe_or_invalid_controls(
    attribute: str,
    value: Any,
) -> None:
    """Softener rejects unsafe or invalid controls."""
    device = make(Softener845, "6360000F", 845)
    device._send_control = Mock()
    with pytest.raises(ValueError):
        device.set_attribute(attribute, value)
    device._send_control.assert_not_called()


@pytest.mark.parametrize(
    ("model", "subtype", "expected"),
    [
        ("6360000F", 845, Softener845),
        ("6320088A", 1046, PipeDispenser1046),
        ("6360000F", 1046, None),
        ("OTHER", 845, None),
    ],
)
def test_selector_requires_exact_model_and_subtype(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    subtype: int,
    expected: Any,
) -> None:
    """Selector requires exact model and subtype."""
    import inspect

    signature = inspect.signature(models.upstream_selector)
    upstream = Mock()
    upstream.__signature__ = signature
    monkeypatch.setattr(models, "upstream_selector", upstream)
    result = models.device_selector(
        name="test",
        device_id=123,
        device_type=237,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model=model,
        subtype=subtype,
        customize="",
    )
    if expected:
        assert isinstance(result, expected)
        upstream.assert_not_called()
    else:
        assert result is upstream.return_value
        upstream.assert_called_once()


def test_waits_for_first_status_before_sending() -> None:
    """Waits for first status before sending."""
    device = make(Softener845, "6360000F", 845)
    device.build_send = Mock()
    with pytest.raises(ValueError, match="Wait for device status"):
        device.set_attribute("soften", True)
    device.build_send.assert_not_called()


def test_vendor_frame_rejects_corruption() -> None:
    """Vendor frame rejects corruption."""
    frame = bytearray([170, 11, 237, 0, 0, 0, 0, 0, 0, 3, 0, 0])
    frame[-1] = -sum(frame[1:]) % 256
    assert VendorFrame(frame.hex(), 237, 3).serialize() == bytes(frame)
    for index in (0, 1, 2, 9, 10, 11):
        corrupt = frame.copy()
        corrupt[index] ^= 1
        with pytest.raises(ValueError):
            VendorFrame(corrupt.hex(), 237, 3)
