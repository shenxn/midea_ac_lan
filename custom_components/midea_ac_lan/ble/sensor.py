from homeassistant.components.sensor import SensorEntity
from .appliances import DISH, HOOD
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
    @property
    def native_value(self):
        if self.value is None:
            return None
        if self.key == "status":
            return STATUS.get(self.value, str(self.value))
        return self.value


async def async_setup_entry(hass, entry, async_add_entities):
    profile = entry.runtime_data.profile
    fields = (
        {"gear": ("风机档位", None)}
        if profile == HOOD
        else {"temperature": ("设定温度", "°C"), "outlet": ("出水温度", "°C")}
    )
    if profile == DISH:
        fields = SENSORS
    entities = []
    for key, (name, unit) in fields.items():
        sensor = ApplianceSensor(entry.runtime_data, key, name)
        sensor._attr_native_unit_of_measurement = unit
        entities.append(sensor)
    async_add_entities(entities)
