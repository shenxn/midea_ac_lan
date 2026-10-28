"""Independent water thermostat sharing the kitchen device's LAN transport."""

# ruff: file-ignore[docstring-missing-exception, any-type]
from typing import Any, ClassVar, cast

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .midea_entity import MideaEntity


class MideaHydronicClimate(MideaEntity, ClimateEntity):
    """Expose water settings without using the indoor AC thermostat methods."""

    _enable_turn_on_off_backwards_compatibility = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 25
    _attr_max_temp = 60
    _attr_target_temperature_step = 1
    _attr_hvac_modes: ClassVar = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes: ClassVar = ["手动", "自动"]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    @property
    def hvac_mode(self) -> HVACMode | None:
        """The module's own power state."""
        value = self._device.get_attribute("hydronic_power")
        return None if value is None else HVACMode.HEAT if value else HVACMode.OFF

    @property
    def target_temperature(self) -> float | None:
        """The reported water setpoint."""
        return cast(
            "float | None",
            self._device.get_attribute("hydronic_temperature_set"),
        )

    @property
    def current_temperature(self) -> float | None:
        """Measured outlet water temperature."""
        return cast(
            "float | None",
            self._device.get_attribute("hydronic_out_temperature"),
        )

    @property
    def preset_mode(self) -> str | None:
        """Automatic or manual water regulation."""
        value = self._device.get_attribute("hydronic_temperature_auto")
        return None if value is None else "自动" if value else "手动"

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set module power without changing indoor AC power."""
        if hvac_mode not in self.hvac_modes:
            raise ValueError("Hydronic module only supports off and heat")
        self._device.set_attribute("hydronic_power", hvac_mode == HVACMode.HEAT)

    def set_temperature(self, **kwargs: Any) -> None:
        """Set manual water temperature; power is changed only when explicit."""
        mode = kwargs.get(ATTR_HVAC_MODE)
        if mode is not None and mode not in self.hvac_modes:
            raise ValueError("Hydronic module only supports off and heat")
        if ATTR_TEMPERATURE in kwargs:
            self._device.set_attribute(
                "hydronic_temperature_set",
                kwargs[ATTR_TEMPERATURE],
            )
        if mode is not None:
            self.set_hvac_mode(mode)

    def set_preset_mode(self, preset_mode: str) -> None:
        """Change the water regulation mode."""
        if preset_mode not in self.preset_modes:
            raise ValueError("Unsupported hydronic preset")
        self._device.set_attribute("hydronic_temperature_auto", preset_mode == "自动")

    def turn_on(self) -> None:
        """Enable water heating."""
        self.set_hvac_mode(HVACMode.HEAT)

    def turn_off(self) -> None:
        """Disable water heating."""
        self.set_hvac_mode(HVACMode.OFF)
