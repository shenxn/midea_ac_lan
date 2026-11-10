from homeassistant.components.sensor import SensorEntity
from .appliances import HOOD
from .entity import ApplianceEntity


class ApplianceSensor(ApplianceEntity, SensorEntity):
    @property
    def native_value(self):
        if self.value is None:
            return None
        return self.value


async def async_setup_entry(hass, entry, async_add_entities):
    profile = entry.runtime_data.profile
    fields = (
        {"gear": ("风机档位", None)}
        if profile == HOOD
        else {"temperature": ("设定温度", "°C"), "outlet": ("出水温度", "°C")}
    )
    entities = []
    for key, (name, unit) in fields.items():
        sensor = ApplianceSensor(entry.runtime_data, key, name)
        sensor._attr_native_unit_of_measurement = unit
        entities.append(sensor)
    async_add_entities(entities)
