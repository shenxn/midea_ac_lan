"""Bluetooth appliance entity entities."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, ambiguous-unicode-character-string]
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import (  # ruff: ignore[relative-imports] - Resolve within the HA integration package.
    DOMAIN,
)


class ApplianceEntity(CoordinatorEntity):
    """ApplianceEntity interface for exact-model Bluetooth appliances."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, key: str, name: str) -> None:
        """Initialize the model-specific Bluetooth state."""
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
    def value(self) -> Any:
        """The last device-reported value or unknown."""
        return (self.coordinator.data or {}).get(self.key)
