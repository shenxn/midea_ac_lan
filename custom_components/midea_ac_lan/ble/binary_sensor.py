from homeassistant.components.binary_sensor import BinarySensorEntity
from .appliances import HOOD
from .entity import ApplianceEntity


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
    entities = []
    for key, name in fields.items():
        sensor = ApplianceBinary(entry.runtime_data, key, name)
        entities.append(sensor)
    async_add_entities(entities)
