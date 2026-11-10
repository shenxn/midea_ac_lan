"""Adopt entities from the standalone dishwasher without changing their IDs."""

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from ..const import DOMAIN

LEGACY_DOMAIN = "colmo_dishwasher_ble"


def adopt_legacy_dishwasher(hass, entry, address):
    """Only transfer records owned by the disabled, address-matched entry."""
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    for previous in hass.config_entries.async_entries(LEGACY_DOMAIN):
        if previous.unique_id != address:
            continue
        if previous.disabled_by is None:
            raise ConfigEntryNotReady(
                "Disable the standalone COLMO BLE dishwasher entry before migration"
            )
        for legacy in dr.async_entries_for_config_entry(devices, previous.entry_id):
            if (LEGACY_DOMAIN, address) not in legacy.identifiers:
                continue
            target = devices.async_get_or_create(
                config_entry_id=entry.entry_id, identifiers={(DOMAIN, address)}
            )
            if legacy.area_id and target.area_id is None:
                devices.async_update_device(target.id, area_id=legacy.area_id)
            for row in er.async_entries_for_config_entry(entities, previous.entry_id):
                if (
                    row.device_id != legacy.id
                    or row.platform != LEGACY_DOMAIN
                    or not row.unique_id.startswith(f"{address}_")
                ):
                    continue
                entities.async_update_entity_platform(
                    row.entity_id,
                    DOMAIN,
                    new_config_entry_id=entry.entry_id,
                    new_device_id=target.id,
                )
                if row.disabled_by == er.RegistryEntryDisabler.CONFIG_ENTRY:
                    entities.async_update_entity(row.entity_id, disabled_by=None)
