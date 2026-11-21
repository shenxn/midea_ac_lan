"""Malformed reports, selector fallback and repeated registration regressions."""

from collections.abc import Callable
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_DEVICE_ID, CONF_SWITCHES
from midealan.const import ProtocolVersion
from midealan.devices.ac import MideaACDevice
from midealan.devices.b6 import MideaB6Device

from custom_components.midea_ac_lan import local_protocol
from custom_components.midea_ac_lan.climate import async_setup_entry
from custom_components.midea_ac_lan.const import DEVICES, DOMAIN
from custom_components.midea_ac_lan.hood_model import Hood730007C9
from custom_components.midea_ac_lan.hood_protocol import hood_status
from custom_components.midea_ac_lan.hydronic_climate import MideaHydronicClimate
from custom_components.midea_ac_lan.hydronic_protocol import hydronic_status
from custom_components.midea_ac_lan.kitchen_protocol import kitchen_status
from custom_components.midea_ac_lan.local_entities import register_local_entities
from custom_components.midea_ac_lan.local_models import (
    SPEEDS,
    FreshAir24297131,
    Kitchen22397091,
    VendorMixin,
)
from custom_components.midea_ac_lan.local_protocol import (
    ModelCodec,
    ac_envelope,
    frame,
)
from custom_components.midea_ac_lan.midea_devices import MIDEA_DEVICES
from custom_components.midea_ac_lan.purifier_model import (
    Purifier632009CN,
    device_selector,
)
from custom_components.midea_ac_lan.purifier_protocol import purifier_status

from .test_local_models import FRESH_STATUS, make


def hood_report(body: bytes) -> bytes:
    """Build a checked B6 v2 status packet, distinct from a v0 control frame."""
    packet = bytearray(frame(182, 3, body))
    packet[8] = 2
    packet[-1] = -sum(packet[1:-1]) & 255
    return bytes(packet)


@pytest.mark.parametrize("record", [b"\x01", b"\x01\x14", b"\x01\x01\x00"])
def test_hood_short_records(record: bytes) -> None:
    """Reject incomplete TLVs even when their outer checksum is correct."""
    assert hood_status(hood_report(b"\x11" + record + b"\x00")) == {}


def test_hood_unknown_and_sentinel_records() -> None:
    """Unknown records and unsupported fields cannot fabricate settings."""
    payload = b"\x11\x02\x01\x00\x01\x1d" + b"\xff" * 29 + b"\x00"
    assert hood_status(hood_report(payload)) == {}
    hood = make(Hood730007C9, "730007C9", 0)
    assert hood.process_message(b"") == {}
    with patch.object(MideaB6Device, "set_attribute") as parent:
        hood.set_attribute("power", False)
    parent.assert_called_once_with("power", False)


@pytest.mark.parametrize(
    "record",
    [b"\x01", b"\x01\x00", b"\x01\x20\x00", b"\x10\x10\x00"],
)
def test_purifier_short_records(record: bytes) -> None:
    """Reject truncated headers, zero lengths and incomplete known fields."""
    assert purifier_status(frame(237, 3, b"\xff\x01\x01" + record)) == {}


def test_minimal_purifier_dispatch() -> None:
    """The minimal installation selector still accepts the exact model."""
    selected = device_selector(
        name="test",
        device_id=123,
        device_type=237,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        customize="",
        model="632009CN",
        subtype=845,
    )
    assert isinstance(selected, Purifier632009CN)


@pytest.mark.parametrize("decoder", [hydronic_status, kitchen_status])
def test_nested_invalid_checksum_and_unknown_command(
    decoder: Callable[[bytes], dict],
) -> None:
    """A correct outer checksum must not hide an invalid nested envelope."""
    body = bytearray(ac_envelope(0x99, b"\x00" * 10))
    body[-1] ^= 1
    assert decoder(frame(172, 3, bytes(body))) == {}
    assert decoder(frame(172, 3, ac_envelope(0x99, b"\x00" * 10))) == {}


def test_ed_and_ac_codec_boundaries() -> None:
    """Short supported envelopes preserve only the fields actually reported."""
    assert local_protocol._decode_ed(b"\xff\x00\x00") == {}
    with pytest.raises(ValueError, match="flag"):
        local_protocol._decode_ed(b"\xff\x01\x01\x14\x09")
    general = local_protocol._decode_ac(ac_envelope(0x11, bytes(17)))
    assert general == {"new_wind_machine": "off", "fresh_air_mode": 0}
    assert local_protocol._decode_ac(ac_envelope(0x10, bytes(9))) == {
        "indoor_temperature": 0,
    }
    assert local_protocol._decode_ac(ac_envelope(0x99, b"")) == {}
    with pytest.raises(ValueError, match="protocol"):
        ModelCodec(0, 0)
    ed = ModelCodec(237, 1046)
    with pytest.raises(ValueError, match="message kind"):
        ed.encode("invalid", {})
    with pytest.raises(ValueError, match="one ED setting"):
        ed.encode("control", {})
    with pytest.raises(ValueError, match="AC query"):
        ModelCodec(172, 1).encode("query", {"query_type": "invalid"})
    with pytest.raises(NotImplementedError):
        VendorMixin()._map_status({})


def test_fresh_air_presets_delegate_to_speed_control() -> None:
    """Both fan presets select the existing, independently tested speed path."""
    fresh = make(FreshAir24297131, "24297131", 1)
    fresh._vendor_status = dict(FRESH_STATUS)
    fresh.build_send = Mock()
    assert fresh.fresh_air_fan_speeds == list(SPEEDS.values())
    assert fresh.fresh_air_exhaust_fan_speeds == list(SPEEDS.values())
    for attr in ("fresh_air_mode", "fresh_air_exhaust_mode"):
        with pytest.raises(ValueError, match="speed preset"):
            fresh.set_attribute(attr, "invalid")
        fresh.set_attribute(attr, next(iter(SPEEDS.values())))
    assert fresh.build_send.call_count == 2


def test_kitchen_telemetry_and_upstream_control() -> None:
    """Water telemetry avoids room decoding while normal AC controls fall through."""
    device = make(Kitchen22397091, "22397091", 1)
    assert device.process_message(frame(172, 3, ac_envelope(0x12, bytes(10)))) == {
        "hydronic_in_temperature": 0,
        "hydronic_out_temperature": 0,
    }
    with patch.object(MideaACDevice, "set_attribute") as parent:
        device.set_attribute("power", False)
    parent.assert_called_once_with("power", False)


def test_registration_is_idempotent() -> None:
    """Repeated integration setup must not duplicate model exclusions."""
    devices = deepcopy(MIDEA_DEVICES)
    register_local_entities(devices)
    first = deepcopy(devices)
    register_local_entities(devices)
    assert devices == first


def test_hydronic_entity_properties_and_modes() -> None:
    """Unknown water status stays unknown; HVAC and preset writes remain isolated."""
    device = make(Kitchen22397091, "22397091", 1)
    entity = MideaHydronicClimate(device, "hydronic_power")
    assert entity.hvac_mode is None
    assert entity.preset_mode is None
    for enabled in (True, False):
        device._attributes.update(
            hydronic_power=enabled,
            hydronic_temperature_auto=enabled,
        )
        assert entity.hvac_mode == (HVACMode.HEAT if enabled else HVACMode.OFF)
        assert entity.preset_mode == ("自动" if enabled else "手动")
    device._attributes.update(hydronic_temperature_set=30, hydronic_out_temperature=29)
    assert entity.native_target_temperature == 30
    assert entity.native_current_temperature == 29
    device.set_attribute = Mock()
    with pytest.raises(ValueError, match="only supports"):
        entity.set_hvac_mode(HVACMode.COOL)
    with pytest.raises(ValueError, match="preset"):
        entity.set_preset_mode("invalid")
    entity.turn_on()
    device.set_attribute.assert_called_with("hydronic_power", True)
    entity.set_temperature(hvac_mode=HVACMode.OFF)
    device.set_attribute.assert_called_with("hydronic_power", False)


async def test_hydronic_entity_setup() -> None:
    """The kitchen entry creates the separate opted-in water thermostat."""
    device = make(Kitchen22397091, "22397091", 1)
    entry = SimpleNamespace(
        data={CONF_DEVICE_ID: 123},
        options={CONF_SWITCHES: ["hydronic_power"]},
    )
    hass = SimpleNamespace(data={DOMAIN: {DEVICES: {123: device}}})
    add = Mock()
    await async_setup_entry(hass, entry, add)
    assert any(isinstance(e, MideaHydronicClimate) for e in add.call_args.args[0])
