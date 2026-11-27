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
    "program": ("洗涤程序", None),
    "stage": ("洗涤阶段代码", None),
    "temperature": ("温度", "°C"),
    "remaining": ("剩余时间", "min"),
    "error": ("故障代码", None),
    "storage_remaining": ("鲜存剩余时间", "h"),
    "salt_level": ("软水盐档位", None),
    "rinse_level": ("亮碟剂档位", None),
    "humidity": ("湿度", "%"),
}
HEATER_SENSORS: dict[str, tuple[str, str | None]] = {
    "temperature": ("设定温度", "°C"),
    "outlet": ("出水温度", "°C"),
    "work_status": ("运行状态", None),
    "inlet": ("进水温度", "°C"),
    "return_water": ("回水温度", "°C"),
    "water_flow": ("实时水流量", "L/min"),
    "gas_lift_percent": ("实时火力", "%"),
    "change_litre": ("当前升数", "L"),
    "cold_conservation_duration": ("零冷水节能时长", "min"),
    "error_code": ("故障代码", None),
}
STATUS = {0: "待机", 1: "取消", 2: "预约", 3: "洗涤中", 4: "故障", 6: "管路检查"}
PROGRAMS = {
    0: "无",
    1: "智能洗",
    2: "强力洗",
    3: "标准洗",
    4: "节能洗",
    5: "玻璃洗",
    6: "1小时洗",
    7: "超快洗",
    8: "预冲洗",
    9: "90分钟洗",
    10: "自清洁",
    11: "果蔬洗",
    13: "除菌洗",
    19: "夜间洗",
}


class ApplianceSensor(ApplianceEntity, SensorEntity):
    """ApplianceSensor interface for exact-model Bluetooth appliances."""

    @property
    def native_value(self) -> Any:
        """The reported native sensor value."""
        if self.value is None:
            return None
        if self.key == "status":
            return STATUS.get(self.value, str(self.value))
        if self.key == "program":
            return PROGRAMS.get(self.value, str(self.value))
        return self.value


async def async_setup_entry(_hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Create the model-specific Bluetooth entities."""
    profile = entry.runtime_data.profile
    fields: dict[str, tuple[str, str | None]] = (
        {} if profile == HOOD else HEATER_SENSORS
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
