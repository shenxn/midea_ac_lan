"""Bluetooth config, lifecycle, entity identity and transport dispatch regressions."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type]
import importlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components import midea_ac_lan
from custom_components.midea_ac_lan import ble, config_flow
from custom_components.midea_ac_lan.ble import control_entities as ce
from custom_components.midea_ac_lan.ble import migration
from custom_components.midea_ac_lan.ble.appliances import DISH, HEATER, HOOD, PURIFIER
from custom_components.midea_ac_lan.ble.controls import group
from tests.ha import MockConfigEntry

ADDRESS = "02:00:00:00:00:01"


def entry(profile: Any = PURIFIER) -> Any:
    """Apply entry."""
    return MockConfigEntry(
        domain="midea_ac_lan",
        title="BLE test",
        data={
            "transport": "bluetooth",
            "address": ADDRESS,
            "sn8": profile.sn8.decode(),
            "type": profile.kind,
        },
    )


async def test_coordinator_poll_write_and_errors(hass: Any) -> None:
    """Verify coordinator poll write and errors."""
    e = entry()
    e.add_to_hass(hass)
    coordinator = ble.Appliance(hass, e)
    link = SimpleNamespace(
        query=AsyncMock(return_value={"power": False}),
        set_option=AsyncMock(return_value={"power": True}),
    )

    @asynccontextmanager
    async def connection(*_args: Any) -> Any:
        """Yield the mocked appliance link for a coordinator request.

        Yields
        ------
        SimpleNamespace
            Mock query and setting methods.

        """
        yield link

    with patch.object(ble, "connect", connection):
        assert await coordinator._async_update_data() == {"power": False}
        await coordinator.write("control_power", "on")
        assert coordinator.data == {"power": True}
        link.set_option.assert_awaited_once_with(
            "control_power",
            "on",
            allow_cycle=False,
        )
        link.query.side_effect = ConnectionError("offline")
        with pytest.raises(UpdateFailed, match="offline"):
            await coordinator._async_update_data()
        link.set_option.side_effect = ValueError("not confirmed")
        with pytest.raises(HomeAssistantError, match="unconfirmed"):
            await coordinator.write("control_power", "on")


@pytest.mark.parametrize("profile", [DISH, PURIFIER])
async def test_setup_advertisement_backoff_and_unload(profile: Any) -> None:
    """Verify setup advertisement backoff and unload."""
    e = Mock()
    e.data = {"transport": "bluetooth"}
    coord = Mock(profile=profile, address=ADDRESS, last_update_success=True)
    coord.async_refresh = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    task = Mock()
    task.done.return_value = False

    def create_task(_hass: Any, coro: Any, _name: Any) -> Any:
        """Apply create task."""
        coro.close()
        return task

    e.async_create_background_task.side_effect = create_task
    hass = Mock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    with (
        patch.object(ble, "Appliance", return_value=coord),
        patch.object(ble.bluetooth, "async_register_callback") as register,
        patch.object(ble, "adopt_legacy_dishwasher") as adopt,
        patch.object(ble, "monotonic", return_value=100) as clock,
    ):
        assert await midea_ac_lan.async_setup_entry(hass, e)
        assert e.runtime_data is coord
        assert adopt.call_count == int(profile == DISH)
        callback = register.call_args.args[1]
        info = SimpleNamespace(time=100)
        callback(info, None)  # already healthy
        e.async_create_background_task.assert_not_called()
        coord.last_update_success = False
        callback(SimpleNamespace(time=0), None)  # stale report
        e.async_create_background_task.assert_not_called()
        callback(info, None)
        assert e.async_create_background_task.call_count == 1
        callback(info, None)  # cooldown
        clock.return_value = 131
        info.time = 131
        callback(info, None)  # still running
        assert e.async_create_background_task.call_count == 1
        task.done.return_value = True
        callback(info, None)
        assert e.async_create_background_task.call_count == 2
        listener = e.add_update_listener.call_args.args[0]
        await listener(hass, e)
        hass.config_entries.async_reload.assert_awaited_once_with(e.entry_id)
        assert await midea_ac_lan.async_unload_entry(hass, e)


@pytest.mark.parametrize("profile", [DISH, HOOD, HEATER, PURIFIER])
@pytest.mark.parametrize(
    "platform",
    [
        "sensor",
        "binary_sensor",
        "switch",
        "lock",
        "number",
        "select",
        "button",
        "climate",
    ],
)
async def test_platforms_dispatch_ble_without_lan_devices(
    profile: Any,
    platform: Any,
) -> None:
    """Verify platforms dispatch ble without lan devices."""
    coord = SimpleNamespace(
        profile=profile,
        address=ADDRESS,
        data={},
        last_update_success=True,
        allow_cycle=False,
        write=AsyncMock(),
    )
    e = SimpleNamespace(data={"transport": "bluetooth"}, runtime_data=coord)
    module = importlib.import_module("custom_components.midea_ac_lan." + platform)
    add = Mock()
    await module.async_setup_entry(Mock(), e, add)
    entities = [entity for call in add.call_args_list for entity in call.args[0]]
    for entity in entities:
        assert entity.unique_id.startswith(ADDRESS + "_")
        assert entity.device_info["identifiers"] == {("midea_ac_lan", ADDRESS)}
        if platform == "sensor":
            assert entity.native_value is None
            coord.data[entity.key] = 0
            assert entity.native_value is not None
        elif platform == "binary_sensor":
            assert entity.is_on is None
            coord.data[entity.key] = True
            assert entity.is_on is True
        elif platform == "switch" and not isinstance(entity, ce.Control):
            assert entity.is_on is None
            coord.data[entity.key] = False
            assert entity.is_on is False
            await entity.async_turn_on()
            await entity.async_turn_off()


async def test_control_entities_readback_unknowns_and_commands() -> None:  # ruff: ignore[too-many-statements] - Exercise every control surface against one shared coordinator.
    """Verify control entities readback unknowns and commands."""
    coord = SimpleNamespace(
        profile=PURIFIER,
        address=ADDRESS,
        data={},
        last_update_success=True,
        write=AsyncMock(),
    )
    toggle = ce.Toggle(coord, "sleep", group(PURIFIER)["sleep"])
    assert toggle.is_on is None
    assert toggle.available
    coord.last_update_success = False
    assert not toggle.available
    coord.last_update_success = True
    coord.data = {
        "controls": {
            "sleep": "on",
            "lock": "off",
            "lightness": "35",
            "gear": "high",
            "power": "on",
        },
        "temperature": 42,
        "outlet": 40,
        "child_lock": True,
    }
    assert toggle.is_on is True
    await toggle.async_turn_on()
    await toggle.async_turn_off()
    lock = ce.PurifierLock(coord, "lock", group(PURIFIER)["lock"])
    assert lock.is_locked is False
    await lock.async_lock()
    await lock.async_unlock()
    oldlock = ce.ChildLock(coord, "cloud_lock", "Lock")
    assert oldlock.is_locked is True
    await oldlock.async_lock()
    await oldlock.async_unlock()
    choice = ce.Choice(coord, "gear", group(HOOD)["gear"])
    assert choice.current_option == "high"
    await choice.async_select_option("off")
    brightness = ce.Brightness(coord, "lightness", group(HOOD)["lightness"])
    assert brightness.value == 35
    await brightness.async_set_native_value(40)
    with pytest.raises(ValueError, match="Integer"):
        await brightness.async_set_native_value(40.5)
    button = ce.BurnerOff(coord, "left_stove_off", group(HOOD)["left_stove_off"])
    assert not button.available
    coord.data["controls"]["left_stove_off"] = "working"
    assert button.available
    await button.async_press()
    thermostat = ce.Thermostat(coord, "water_heater", group(HEATER)["water_heater"])
    assert thermostat.hvac_mode == HVACMode.HEAT
    assert thermostat.native_target_temperature == 42
    assert thermostat.native_current_temperature == 40
    await thermostat.async_set_temperature(temperature=43)
    for mode in [HVACMode.OFF, HVACMode.HEAT]:
        await thermostat.async_set_hvac_mode(mode)
    with pytest.raises(ValueError, match="Unsupported"):
        await thermostat.async_set_hvac_mode(HVACMode.COOL)
    with pytest.raises(ValueError, match="whole"):
        await thermostat.async_set_temperature(temperature=42.5)
    coord.data = {"controls": {"power": "off", "sleep": "off"}}
    assert thermostat.hvac_mode == HVACMode.OFF
    assert toggle.is_on is False
    assert choice.current_option is None
    assert brightness.native_value is None
    assert lock.is_locked is None
    coord.data = None
    assert thermostat.hvac_mode is None
    assert thermostat.native_current_temperature is None


async def test_config_flow_discovery_filter_and_options() -> None:
    """Verify config flow discovery filter and options."""
    flow = config_flow.MideaLanConfigFlow()
    flow.hass = Mock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    flow.async_create_entry = Mock(return_value={"created": True})
    advertisements = [
        SimpleNamespace(
            address=ADDRESS,
            manufacturer_data={1704: b"x" + PURIFIER.sn8 + b"ED"},
        ),
        SimpleNamespace(address="unknown", manufacturer_data={}),
        SimpleNamespace(
            address="mismatch",
            manufacturer_data={1704: b"x" + PURIFIER.sn8 + b"E1"},
        ),
    ]
    with patch.object(
        ble.bluetooth,
        "async_discovered_service_info",
        return_value=advertisements,
    ):
        form = await flow.async_step_user({"action": "bluetooth"})
        assert form["step_id"] == "bluetooth_device"
        assert await flow.async_step_bluetooth_device({"address": ADDRESS}) == {
            "created": True,
        }
        assert flow.async_create_entry.call_args.kwargs["data"]["sn8"] == "63200872"
    with patch.object(ble.bluetooth, "async_discovered_service_info", return_value=[]):
        assert (await flow.async_step_bluetooth_device())[
            "reason"
        ] == "no_ble_appliances"
    dish = config_flow.MideaLanOptionsFlowHandler(entry(DISH))
    assert (await dish.async_step_init())["step_id"] == "init"
    result = await dish.async_step_init({"allow_dishwasher_cycle": True})
    assert result["data"] == {"allow_dishwasher_cycle": True}
    assert (await config_flow.MideaLanOptionsFlowHandler(entry()).async_step_init())[
        "reason"
    ] == "ble_no_options"


def test_legacy_migration_only_transfers_disabled_address_matched_entities() -> None:
    """Verify legacy migration only transfers disabled address matched entities."""
    hass = Mock()
    e = SimpleNamespace(entry_id="new")
    previous = SimpleNamespace(unique_id=ADDRESS, disabled_by=None, entry_id="old")
    hass.config_entries.async_entries.return_value = [previous]
    devices = Mock()
    entities = Mock()
    with (
        patch.object(migration.dr, "async_get", return_value=devices),
        patch.object(migration.er, "async_get", return_value=entities),
        patch.object(migration.dr, "async_entries_for_config_entry") as olddevices,
        patch.object(migration.er, "async_entries_for_config_entry") as oldentities,
    ):
        with pytest.raises(ConfigEntryNotReady, match="Disable"):
            migration.adopt_legacy_dishwasher(hass, e, ADDRESS)
        previous.disabled_by = "user"
        hass.config_entries.async_entries.return_value = [
            SimpleNamespace(unique_id="other"),
            previous,
        ]
        legacy = SimpleNamespace(
            id="legacy",
            identifiers={(migration.LEGACY_DOMAIN, ADDRESS)},
            area_id="kitchen",
        )
        olddevices.return_value = [SimpleNamespace(identifiers=set()), legacy]
        target = SimpleNamespace(id="target", area_id=None)
        devices.async_get_or_create.return_value = target
        base = {
            "device_id": "legacy",
            "platform": migration.LEGACY_DOMAIN,
            "unique_id": ADDRESS + "_status",
            "entity_id": "sensor.test",
            "disabled_by": migration.er.RegistryEntryDisabler.CONFIG_ENTRY,
        }
        oldentities.return_value = [
            SimpleNamespace(**{**base, "device_id": "other"}),
            SimpleNamespace(**{**base, "platform": "other"}),
            SimpleNamespace(**{**base, "unique_id": "other"}),
            SimpleNamespace(**base),
            SimpleNamespace(
                **{**base, "entity_id": "sensor.second", "disabled_by": "user"},
            ),
        ]
        migration.adopt_legacy_dishwasher(hass, e, ADDRESS)
        assert entities.async_update_entity_platform.call_count == 2
        entities.async_update_entity.assert_called_once_with(
            "sensor.test",
            disabled_by=None,
        )
        devices.async_update_device.assert_called_once_with("target", area_id="kitchen")
        target.area_id = "existing"
        migration.adopt_legacy_dishwasher(hass, e, ADDRESS)
        assert devices.async_update_device.call_count == 1
