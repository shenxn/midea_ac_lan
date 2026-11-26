"""Bluetooth appliance binary sensor entities."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type]
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity

from . import purifier
from .appliances import DISH, HOOD, PURIFIER
from .entity import ApplianceEntity

NAMES = {
    "door": "机门",
    "low_salt": "缺软水盐",
    "low_rinse": "缺亮碟剂",
    "water_lack": "缺水",
    "auto_door": "自动开门设置",
    "light": "灯带",
    "storage": "鲜存运行",
}


HEATER_BINARY = {
    "power": "电源状态",
    "burning": "燃烧反馈",
    "new_filter_problem": "全维恒净芯异常",
    "cruise_antifreeze": "巡航防冻",
    "cruise_antifreeze_error": "巡航防冻故障",
}


class ApplianceBinary(ApplianceEntity, BinarySensorEntity):
    """ApplianceBinary interface for exact-model Bluetooth appliances."""

    @property
    def is_on(self) -> Any:
        """The last reported switch state."""
        return self.value


async def async_setup_entry(_hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Create the model-specific Bluetooth entities."""
    profile = entry.runtime_data.profile
    fields = {"power": "电源状态"} if profile == HOOD else HEATER_BINARY
    if profile == DISH:
        fields = NAMES
    if profile == PURIFIER:
        fields = purifier.BINARY
    entities = []
    for key, name in fields.items():
        sensor = ApplianceBinary(entry.runtime_data, key, name)
        if key == "door":
            sensor._attr_device_class = "door"  # ruff: ignore[private-member-access] - Set HA metadata before adding the entity.
        elif key in {"new_filter_problem", "cruise_antifreeze_error"}:
            sensor._attr_device_class = "problem"  # ruff: ignore[private-member-access] - Set HA metadata before adding the entity.
        entities.append(sensor)
    async_add_entities(entities)
