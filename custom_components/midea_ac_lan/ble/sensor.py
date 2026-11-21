"""Bluetooth appliance sensor entities."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type]
from typing import Any

from homeassistant.components.sensor import SensorEntity

from . import purifier
from .appliances import DISH, HOOD, PURIFIER
from .entity import ApplianceEntity

SENSORS = {
    "status": ("运行状态", None),
    "program": ("程序代码", None),
    "stage": ("洗涤阶段代码", None),
    "temperature": ("温度", "°C"),
    "remaining": ("剩余时间", "min"),
    "error": ("故障代码", None),
    "storage_remaining": ("鲜存剩余时间", "h"),
    "salt_level": ("软水盐档位", None),
    "rinse_level": ("亮碟剂档位", None),
    "humidity": ("湿度", "%"),
}
STATUS = {0: "待机", 1: "取消", 2: "预约", 3: "洗涤中", 4: "故障", 6: "管路检查"}


class ApplianceSensor(ApplianceEntity, SensorEntity):
    """ApplianceSensor interface for exact-model Bluetooth appliances."""

    @property
    def native_value(self) -> Any:
        """The reported native sensor value."""
        if self.value is None:
            return None
        if self.key == "status":
            return STATUS.get(self.value, str(self.value))
        return self.value


async def async_setup_entry(_hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Create the model-specific Bluetooth entities."""
    profile = entry.runtime_data.profile
    fields: dict[str, tuple[str, str | None]] = (
        {"gear": ("风机档位", None)}
        if profile == HOOD
        else {"temperature": ("设定温度", "°C"), "outlet": ("出水温度", "°C")}
    )
    if profile == DISH:
        fields = SENSORS
    if profile == PURIFIER:
        fields = purifier.SENSORS
    entities = []
    for key, (name, unit) in fields.items():
        sensor = ApplianceSensor(entry.runtime_data, key, name)
        sensor._attr_native_unit_of_measurement = unit  # ruff: ignore[private-member-access] - Set HA metadata before adding the entity.
        entities.append(sensor)
    async_add_entities(entities)
