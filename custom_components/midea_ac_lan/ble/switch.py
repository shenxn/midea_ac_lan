from homeassistant.components.switch import SwitchEntity
from .appliances import HOOD
from .entity import ApplianceEntity


class ApplianceSwitch(ApplianceEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.value

    async def async_turn_on(self, **kwargs):
        await self.coordinator.write(self.key, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.write(self.key, False)


async def async_setup_entry(hass, entry, async_add_entities):
    profile = entry.runtime_data.profile
    fields = {"light": "照明"} if profile == HOOD else {"beep": "主机提示音"}
    async_add_entities(
        [ApplianceSwitch(entry.runtime_data, k, v) for k, v in fields.items()]
    )
