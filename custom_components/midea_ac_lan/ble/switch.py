"""Bluetooth appliance switch entities."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type]
from typing import Any

from homeassistant.components.switch import SwitchEntity

from .appliances import DISH, HOOD, PURIFIER
from .control_entities import add_controls
from .entity import ApplianceEntity


class ApplianceSwitch(ApplianceEntity, SwitchEntity):
    """ApplianceSwitch interface for exact-model Bluetooth appliances."""

    @property
    def is_on(self) -> Any:
        """The last reported switch state."""
        return self.value

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Apply async turn on."""
        await self.coordinator.write(self.key, True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Apply async turn off."""
        await self.coordinator.write(self.key, False)


async def async_setup_entry(_hass: Any, entry: Any, async_add_entities: Any) -> None:
    """Create the model-specific Bluetooth entities."""
    add_controls(entry, async_add_entities, "switch")
    profile = entry.runtime_data.profile
    fields = {"light": "照明"} if profile == HOOD else {"beep": "主机提示音"}
    if profile == DISH:
        fields = {"beep": "提示音", "child_lock": "童锁"}
    if profile == PURIFIER:
        fields = {}
    async_add_entities(
        [ApplianceSwitch(entry.runtime_data, k, v) for k, v in fields.items()],
    )
