"""HA control surfaces sharing the verified BLE transport and readback."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-exception]
from typing import Any, ClassVar

from homeassistant.components.button import ButtonEntity
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.lock import LockEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import UnitOfTemperature

from ..native_temperature import (  # ruff: ignore[relative-imports] - Resolve within the HA integration package.
    NativeTemperatureCompat,
)
from .appliances import DISH
from .controls import group
from .entity import ApplianceEntity


class Control(ApplianceEntity):
    """Control interface for exact-model Bluetooth appliances."""

    def __init__(self, coordinator: Any, key: str, spec: Any) -> None:
        """Initialize the model-specific Bluetooth state."""
        super().__init__(coordinator, "control_" + key, spec["name"])
        self.field = key
        self.spec = spec

    @property
    def observed(self) -> Any:
        """Controls present in the latest device report."""
        return (self.coordinator.data or {}).get("controls", {})

    @property
    def available(self) -> bool:
        """Require a successful update and known state for stateful buttons."""
        if not super().available:
            return False
        if self.spec["platform"] == "button":
            if self.field == "new_filter_reset":
                return self.observed.get(self.field) in {"normal", "abnormal"}
            return self.observed.get(self.field) in {"off", "working"}
        return True

    async def apply(self, option: str) -> None:
        """Write a catalog option through the coordinator."""
        await self.coordinator.write(self.key, option)


class Toggle(Control, SwitchEntity):
    """Toggle interface for exact-model Bluetooth appliances."""

    @property
    def is_on(self) -> Any:
        """The last reported switch state."""
        value = self.observed.get(self.field)
        return value == "on" if value is not None else None

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Apply async turn on."""
        await self.apply("on")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Apply async turn off."""
        await self.apply("off")


class Choice(Control, SelectEntity):
    """Choice interface for exact-model Bluetooth appliances."""

    @property
    def options(self) -> Any:
        """Options supported by the exact-model catalog."""
        return list(self.spec["commands"])

    @property
    def current_option(self) -> Any:
        """The reported option only when supported."""
        v = self.observed.get(self.field)
        return v if v in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Apply async select option."""
        await self.apply(option)


class Brightness(Control, NumberEntity):
    """Numeric control interface for exact-model Bluetooth appliances."""

    def __init__(self, coordinator: Any, key: str, spec: Any) -> None:
        """Initialize range, step, unit, and optional fixed-point scale."""
        super().__init__(coordinator, key, spec)
        self._scale = spec.get("scale", 1)
        self._attr_native_min_value = spec.get("min", 10)
        self._attr_native_max_value = spec.get("max", 100)
        self._attr_native_step = spec.get("step", 5)
        self._attr_native_unit_of_measurement = spec.get("unit", "%")

    @property
    def value(self) -> Any:
        """The last device-reported value or unknown."""
        return self.native_value

    @property
    def native_value(self) -> Any:
        """The reported native numeric value."""
        v = self.observed.get(self.field)
        if v is None:
            return None
        raw = int(v)
        return round(raw / self._scale, 1) if self._scale != 1 else raw

    async def async_set_native_value(self, value: Any) -> None:
        """Apply async set native value."""
        scaled = round(float(value) * self._scale, 6)
        if not scaled.is_integer():
            raise ValueError("Integer step value required")
        await self.apply(str(int(scaled)))


class BurnerOff(Control, ButtonEntity):
    """BurnerOff interface for exact-model Bluetooth appliances."""

    async def async_press(self) -> None:
        """Apply async press."""
        await self.apply("press")


class Thermostat(NativeTemperatureCompat, Control, ClimateEntity):
    """Thermostat interface for exact-model Bluetooth appliances."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 32
    _attr_max_temp = 65
    _attr_target_temperature_step = 1
    _attr_hvac_modes: ClassVar = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_mode(self) -> Any:
        """The reported heater power as an HVAC mode."""
        v = self.observed.get("power")
        return (HVACMode.HEAT if v == "on" else HVACMode.OFF) if v is not None else None

    @property
    def native_target_temperature(self) -> Any:
        """The reported temperature setpoint."""
        return (self.coordinator.data or {}).get("temperature")

    @property
    def native_current_temperature(self) -> Any:
        """The measured outlet temperature."""
        return (self.coordinator.data or {}).get("outlet")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Apply async set temperature."""
        temp = float(kwargs["temperature"])
        if not temp.is_integer():
            raise ValueError("Device accepts whole degrees")
        await self.apply(str(int(temp)))

    async def async_set_hvac_mode(self, hvac_mode: Any) -> None:
        """Apply async set hvac mode."""
        if hvac_mode not in self.hvac_modes:
            raise ValueError("Unsupported mode")
        await self.coordinator.write(
            "control_power",
            "off" if hvac_mode == HVACMode.OFF else "on",
        )


class ChildLock(ApplianceEntity, LockEntity):
    """ChildLock interface for exact-model Bluetooth appliances."""

    @property
    def is_locked(self) -> Any:
        """The last reported child-lock state."""
        return (self.coordinator.data or {}).get("child_lock")

    async def async_lock(self, **_kwargs: Any) -> None:
        """Apply async lock."""
        await self.coordinator.write("child_lock", True)

    async def async_unlock(self, **_kwargs: Any) -> None:
        """Apply async unlock."""
        await self.coordinator.write("child_lock", False)


def add_controls(entry: Any, add: Any, platform: str) -> None:
    """Create only controls offered by this model and its options."""
    coordinator = entry.runtime_data
    if platform == "lock":
        if coordinator.profile == DISH:
            add([ChildLock(coordinator, "cloud_lock", "童锁")])
        return
    cls = {
        "switch": Toggle,
        "select": Choice,
        "number": Brightness,
        "button": BurnerOff,
        "climate": Thermostat,
    }[platform]
    add(
        [
            cls(coordinator, key, spec)
            for key, spec in group(coordinator.profile, coordinator.allow_cycle).items()
            if spec["platform"] == platform
        ],
    )
