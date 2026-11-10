"""HA control surfaces sharing the verified BLE transport and readback."""

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

from .appliances import DISH
from .controls import group
from .entity import ApplianceEntity


class Control(ApplianceEntity):
    def __init__(self, coordinator, key, spec):
        super().__init__(coordinator, "control_" + key, spec["name"])
        self.field = key
        self.spec = spec

    @property
    def observed(self):
        return (self.coordinator.data or {}).get("controls", {})

    @property
    def available(self):
        if not super().available:
            return False
        if self.spec["platform"] == "button":
            return self.observed.get(self.field) in ("off", "working")
        return True

    async def apply(self, option):
        await self.coordinator.write(self.key, option)


class Toggle(Control, SwitchEntity):
    @property
    def is_on(self):
        value = self.observed.get(self.field)
        return value == "on" if value is not None else None

    async def async_turn_on(self, **kwargs):
        await self.apply("on")

    async def async_turn_off(self, **kwargs):
        await self.apply("off")


class Choice(Control, SelectEntity):
    @property
    def options(self):
        return list(self.spec["commands"])

    @property
    def current_option(self):
        v = self.observed.get(self.field)
        return v if v in self.options else None

    async def async_select_option(self, option):
        await self.apply(option)


class Brightness(Control, NumberEntity):
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"

    @property
    def value(self):
        return self.native_value

    @property
    def native_value(self):
        v = self.observed.get(self.field)
        return int(v) if v is not None else None

    async def async_set_native_value(self, value):
        if not float(value).is_integer():
            raise ValueError("Integer brightness required")
        await self.apply(str(int(value)))


class BurnerOff(Control, ButtonEntity):
    async def async_press(self):
        await self.apply("press")


class Thermostat(Control, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 20
    _attr_max_temp = 60
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def hvac_mode(self):
        v = self.observed.get("power")
        return (HVACMode.HEAT if v == "on" else HVACMode.OFF) if v is not None else None

    @property
    def target_temperature(self):
        return (self.coordinator.data or {}).get("temperature")

    @property
    def current_temperature(self):
        return (self.coordinator.data or {}).get("outlet")

    async def async_set_temperature(self, **kwargs):
        temp = float(kwargs["temperature"])
        if not temp.is_integer():
            raise ValueError("Device accepts whole degrees")
        await self.apply(str(int(temp)))

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise ValueError("Unsupported mode")
        await self.coordinator.write(
            "control_power", "off" if hvac_mode == HVACMode.OFF else "on"
        )


class ChildLock(ApplianceEntity, LockEntity):
    @property
    def is_locked(self):
        return (self.coordinator.data or {}).get("child_lock")

    async def async_lock(self, **kwargs):
        await self.coordinator.write("child_lock", True)

    async def async_unlock(self, **kwargs):
        await self.coordinator.write("child_lock", False)


def add_controls(entry, add, platform):
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
        ]
    )
