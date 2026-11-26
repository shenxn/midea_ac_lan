"""Exact-model HA registry isolation and entity mapping."""

from copy import deepcopy
from datetime import time
from unittest.mock import patch

from midealan.const import ProtocolVersion
from midealan.devices.ca import MideaCADevice

from custom_components.midea_ac_lan.const import supports_device
from custom_components.midea_ac_lan.fridge_entities import register_fridge_entities
from custom_components.midea_ac_lan.midea_devices import MIDEA_DEVICES
from custom_components.midea_ac_lan.number import MideaNumber
from custom_components.midea_ac_lan.select import MideaSelect
from custom_components.midea_ac_lan.time import MideaTime


def test_registry_isolation() -> None:
    """Preserve shared door metadata and scope all additions and exclusions."""
    original = {
        "freezer_door": {"type": "binary_sensor"},
        "refrigerator_door": {"type": "binary_sensor"},
        "humidity": {"type": "sensor"},
    }
    entities = deepcopy(original)
    register_fridge_entities(entities)
    assert entities["freezer_door"] == original["freezer_door"]
    assert entities["refrigerator_door"] == original["refrigerator_door"]
    assert not supports_device("00000003", 38, entities["humidity"])
    assert supports_device("other", 38, entities["humidity"])
    for key in entities.keys() - original.keys():
        assert supports_device("00000003", 38, entities[key])
        assert not supports_device("other", 38, entities[key])
        assert not supports_device("00000003", 37, entities[key])
    assert "estimated_power" not in entities
    assert "energy_last_24h" not in entities


def test_entities_use_reported_attributes() -> None:
    """Use actual device fields and atomic time writes through generic platforms."""
    d = MideaCADevice(
        name="AXFS",
        device_id=2,
        ip_address="192.0.2.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V1,
        model="00000003",
        subtype=38,
        customize="",
    )
    d._attributes.update(
        {
            "refrigerator_level": 3,
            "lighting": "standard",
            "night_start_hour": 22,
            "night_start_min": 0,
        },
    )
    number = MideaNumber(d, "refrigerator_level")
    assert number.native_value == 3
    assert number.native_unit_of_measurement is None
    select = MideaSelect(d, "lighting")
    assert select.current_option == "标准"
    timer = MideaTime(d, "night_start")
    assert timer.native_value == time(22, 0)
    with patch.object(d, "set_attribute") as setter:
        select.select_option("中")
        setter.assert_called_with("lighting", "medium")
        timer.set_value(time(21, 30))
        setter.assert_called_with("night_start", "21:30")
    assert MIDEA_DEVICES[202]["entities"]["ambient_temperature"]["unit"] == "°C"
