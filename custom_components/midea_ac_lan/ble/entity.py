from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from ..const import DOMAIN


class ApplianceEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        device = coordinator.profile
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            manufacturer="COLMO",
            model=device.model,
            name=f"{device.name}（蓝牙）",
        )

    @property
    def value(self):
        return (self.coordinator.data or {}).get(self.key)
