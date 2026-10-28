"""Independent control vectors and isolation of the shared water module."""

# ruff: file-ignore[magic-value-comparison, any-type]

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from homeassistant.components.climate import HVACMode
from midea_ac_lan.hydronic_climate import MideaHydronicClimate
from midea_ac_lan.hydronic_protocol import (
    hydronic_control,
    hydronic_query,
    hydronic_status,
)
from midea_ac_lan.local_models import Kitchen22397091
from midea_ac_lan.local_protocol import ac_envelope, frame
from midealan.const import ProtocolVersion

VECTORS = json.loads((Path(__file__).parent / "fixtures/hydronic.json").read_text())


@pytest.mark.parametrize("case", VECTORS)
def test_control_vector(case: dict[str, Any]) -> None:
    """Commands match independent exact-model vectors."""
    command = dict(case["command"])
    command.pop("single_control")
    if "water_model_temperature_set" in command:
        name, value = "temperature_set", command["water_model_temperature_set"]
    else:
        key, value = next(iter(command.items()))
        name, value = key.removeprefix("water_model_"), value == "on"
    assert hydronic_control(name, value).hex() == case["frame"]


@pytest.mark.parametrize(
    "value",
    [True, 24, 61, 25.5, float("nan"), float("inf"), "26", None],
)
def test_invalid_temperature(value: Any) -> None:
    """Reject malformed inputs before transmitting."""
    with pytest.raises(ValueError, match=r"Water temperature|Unsupported"):
        hydronic_control("temperature_set", value)


def test_query() -> None:
    """Read-only request matches the verified wire frame."""
    assert hydronic_query().hex() == "aa12ac00000000000203aa0800ffff12df5f3d"


def test_water_telemetry_and_corruption() -> None:
    """Signed telemetry decodes and damaged frames are rejected."""
    payload = bytearray(88)
    payload[6:8] = (-125).to_bytes(2, "little", signed=True)
    payload[8:10] = (2250).to_bytes(2, "little", signed=True)
    packet = frame(172, 3, ac_envelope(0x12, bytes(payload)))
    assert hydronic_status(packet) == {
        "hydronic_in_temperature": -1.25,
        "hydronic_out_temperature": 22.5,
    }
    for i in range(len(packet)):
        assert hydronic_status(packet[:i]) == {}
        corrupt = bytearray(packet)
        corrupt[i] ^= 1
        assert hydronic_status(bytes(corrupt)) == {}


def test_c002_states_and_masks() -> None:
    """Each water flag stays independent of other functions."""
    for flags in range(64):
        p = bytearray(79)
        p[1:4] = b"\x01\xc0\x02"
        p[34] = flags
        p[35] = 64
        p[36] = 102
        r = hydronic_status(frame(172, 3, ac_envelope(0xC0, bytes(p))))
        assert r["hydronic_has_temperature_set"] is True
        assert r["hydronic_temperature_set"] == 26
        for name, bit in [
            ("power", 0),
            ("power_save", 1),
            ("temperature_auto", 3),
            ("ptc", 4),
            ("go_out", 5),
        ]:
            assert r["hydronic_" + name] == bool(flags & (1 << bit))


def test_adapter_guard_and_readback() -> None:
    """Capabilities gate commands and only readback changes state."""
    d: Any = Kitchen22397091(
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model="22397091",
        subtype=1,
        customize="",
    )
    d.build_send = Mock()
    with pytest.raises(ValueError, match="not confirmed"):
        d.set_attribute("hydronic_power", True)
    p = bytearray(80)
    p[20] = 64
    p[19] = 100
    d.process_message(frame(172, 3, ac_envelope(0x11, bytes(p))))
    assert d.get_attribute("hydronic_power") is False
    with pytest.raises(ValueError, match="not confirmed"):
        d.set_attribute("hydronic_temperature_set", 26)
    p = bytearray(79)
    p[1:4] = b"\x01\xc0\x02"
    p[35] = 64
    p[36] = 100
    d.process_message(frame(172, 3, ac_envelope(0xC0, bytes(p))))
    d.set_attribute("hydronic_temperature_set", 26)
    assert d.get_attribute("hydronic_temperature_set") == 25
    d.build_send.assert_called_once()


def test_climate_uses_only_water_controls() -> None:
    """HA services never call the parent indoor-unit power or setpoint methods."""
    device: Any = Mock()
    device.device_type = 172
    device.device_id = 123
    device.name = "Kitchen"
    entity = MideaHydronicClimate(device, "hydronic_power")
    entity.set_temperature(temperature=26)
    device.set_attribute.assert_called_once_with("hydronic_temperature_set", 26)
    device.set_attribute.reset_mock()
    entity.turn_off()
    device.set_attribute.assert_called_once_with("hydronic_power", False)
    device.set_attribute.reset_mock()
    with pytest.raises(ValueError, match="only supports"):
        entity.set_temperature(temperature=26, hvac_mode=HVACMode.COOL)
    device.set_attribute.assert_not_called()
    entity.set_preset_mode("自动")
    device.set_attribute.assert_called_once_with("hydronic_temperature_auto", True)
    assert entity.device_info["via_device"] == ("midea_ac_lan", "123")
