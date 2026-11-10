from homeassistant.components.binary_sensor import BinarySensorEntity
from .appliances import DISH, HOOD
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


class ApplianceBinary(ApplianceEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.value


async def async_setup_entry(hass, entry, async_add_entities):
    profile = entry.runtime_data.profile
    fields = (
        {"power": "电源状态"}
        if profile == HOOD
        else {"power": "电源状态", "burning": "燃烧反馈"}
    )
    if profile == DISH:
        fields = NAMES
    entities = []
    for key, name in fields.items():
        sensor = ApplianceBinary(entry.runtime_data, key, name)
        if key == "door":
            sensor._attr_device_class = "door"
        entities.append(sensor)
    async_add_entities(entities)
