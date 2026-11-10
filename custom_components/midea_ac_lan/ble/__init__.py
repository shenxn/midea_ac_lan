"""Midea appliances via the Home Assistant Bluetooth proxy."""

import asyncio
from datetime import timedelta
import logging
from time import monotonic
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import connect
from .appliances import DEVICES


PLATFORMS = ["sensor", "binary_sensor", "switch"]


class Appliance(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=90),
            always_update=False,
        )
        self.lock = asyncio.Lock()
        self.profile = DEVICES[entry.data["sn8"]]
        self.address = entry.data["address"]

    async def _async_update_data(self):
        async with self.lock:
            try:
                async with (
                    asyncio.timeout(55),
                    connect(self.hass, self.profile, self.address) as link,
                ):
                    return await link.query()
            except Exception as err:
                raise UpdateFailed(f"{type(err).__name__}: {err}") from err

    async def write(self, key, value):
        async with self.lock:
            try:
                async with (
                    asyncio.timeout(60),
                    connect(self.hass, self.profile, self.address) as link,
                ):
                    state = await link.set_option(key, value)
                self.async_set_updated_data(state)
            except Exception as err:
                raise HomeAssistantError(f"Setting {key} unconfirmed: {err}") from err


async def setup_entry(hass: HomeAssistant, entry):
    coordinator = Appliance(hass, entry)
    # A sleeping appliance should still have a device page after HA restarts.
    await coordinator.async_refresh()
    next_wake_attempt = 0.0
    wake_task = None

    @callback
    def on_advertisement(info, change):
        nonlocal next_wake_attempt, wake_task
        now = monotonic()
        if (
            coordinator.last_update_success
            or now < next_wake_attempt
            or now - info.time > 10
            or (wake_task and not wake_task.done())
        ):
            return
        next_wake_attempt = now + 30
        wake_task = entry.async_create_background_task(
            hass,
            coordinator.async_request_refresh(),
            "Refresh COLMO after BLE advertisement",
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            on_advertisement,
            {"address": coordinator.address},
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
