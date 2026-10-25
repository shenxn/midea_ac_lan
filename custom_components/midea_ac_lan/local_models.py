"""Exact-model local LAN codecs using the appliance vendor's cached Lua.

No cloud requests. Exact-model adapters for CWS-F08/845, CAX250GC1M/1
and CWGR-A1/1046. Vendor codecs are supplied privately by the user.
All transport, authentication and other models retain the upstream implementation.
"""

# Wire constants and dynamic upstream/Lua attributes intentionally mirror the protocol.
# ruff: file-ignore[magic-value-comparison, any-type, undocumented-public-init, docstring-missing-returns, docstring-missing-exception, no-self-use, too-many-boolean-expressions, import-outside-top-level]

import inspect
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from midealan.device import MideaDevice
from midealan.devices import device_selector as upstream_selector
from midealan.devices.ac import MideaACDevice
from midealan.devices.ed import MideaEDDevice

CODEC_DIR = Path(__file__).resolve().parents[2] / ".storage/midea_ac_lan/model_lua"

FILES = {
    (237, "6320088A", 1046): "T_0000_ED_6320088A_2025032701.lua",
    (237, "6360000F", 845): "T_0000_ED_6360000F_2024090502.lua",
    (172, "24297131", 1): "T_0000_AC_24297131_2024112901.lua",
}
SOFT_KEYS = [
    "velocity",
    "soft_available_big",
    "water_consumption_big",
    "water_consumption_average",
    "left_salt",
    "water_hardness",
    "flushing_days",
    "timing_regeneration_hour",
    "timing_regeneration_min",
    "regeneration_left_seconds",
    "use_days",
    "regeneration_count",
    "error",
    "soften",
    "cl_sterilization",
    "leak_water_protection",
    "micro_leak_protection",
    "leak_water",
    "micro_leak",
    "low_salt",
    "no_salt",
    "rsj_stand_by",
    "regeneration",
    "holiday_mode",
    "water_way",
    "salt_alarm_threshold",
    "leak_water_protection_value",
    "micro_leak_protection_value",
    "salt_level_sensor_error",
    "chlorine_sterilization_error",
    "flowmeter_error",
    "rtc_error",
]
PIPE_SETTINGS = [
    "custom_temperature_1",
    "custom_temperature_2",
    "custom_temperature_3",
    "quantify_1",
    "quantify_2",
    "quantify_3",
    "screenout_time",
    "human_sensing_switch",
    "cur_quantify",
]
PIPE_VOLUMES = {
    "quantify_1": (50, 100, 150),
    "quantify_2": (150, 200, 250, 300, 400, 500),
    "quantify_3": (300, 400, 500, 600, 700),
}
SOFT_SWITCHES = {"soften", "cl_sterilization"}
VENTILATION_MODES = {1: "热交换", 7: "强劲", 8: "度假", 4: "自动"}
SPEEDS = {0: "off", 40: "low", 60: "medium", 80: "high", 100: "full"}


class VendorFrame:
    """Validate a complete vendor frame before handing it to LAN transport."""

    def __init__(self, frame: str, expected_type: int, message_type: int) -> None:
        self.frame = bytes.fromhex(frame)
        if (
            len(self.frame) < 12
            or self.frame[0] != 170
            or self.frame[2] != expected_type
            or self.frame[9] != message_type
            or self.frame[1] != len(self.frame) - 1
            or sum(self.frame[1:]) % 256
        ):
            raise ValueError("Invalid vendor protocol frame")

    def serialize(self) -> bytes:
        """Return the validated wire frame."""
        return self.frame


class SoftStatusQuery(VendorFrame):
    """Identify ED status queries for transport response tracking."""


class FreshStatusQuery(VendorFrame):
    """Identify the ventilation general status query."""


class FreshRunQuery(VendorFrame):
    """Identify the ventilation running-status query."""


class FreshC003Query(VendorFrame):
    """Identify the dedicated C003 ventilation query."""


class Codec:
    """Serialize access to one private model Lua runtime."""

    def __init__(
        self,
        filename: str,
        subtype: int,
        serial_number: str | None = None,
    ) -> None:
        self.lock = threading.RLock()
        self.info = {"deviceSubType": str(subtype)}
        if serial_number:
            self.info["deviceSN"] = serial_number
        # LuaRuntime is provided by a compiled extension, invisible to pylint.
        # pylint: disable-next=no-name-in-module
        from lupa.lua51 import LuaRuntime

        root = Path(__file__).parent / "model_lua"
        source = CODEC_DIR / filename
        # Preserve manual installations of the original local patch.
        if not source.is_file():
            source = root / filename
        if not source.is_file():
            raise FileNotFoundError(
                f"Exact-model codec {filename} is missing. Place your privately "
                f"obtained copy in {CODEC_DIR}; see doc/local-model-adapters.md.",
            )
        self.lua = LuaRuntime(
            unpack_returned_tuples=True,
            register_eval=False,
            register_builtins=False,
        )
        self.lua.execute(
            "package.path = "
            + json.dumps(str(root / "?.lua"))
            + ' .. ";" .. package.path; print=function(...) end',
        )
        self.lua.execute("python=nil")
        self.lua.execute(source.read_text(encoding="utf-8"))
        # The vendor codec needs no filesystem/process/network access after load.
        self.lua.execute(
            "os=nil; io=nil; dofile=nil; loadfile=nil; "
            "package=nil; require=nil; debug=nil",
        )

    def encode(
        self,
        kind: str,
        value: dict[str, Any],
        status: dict[str, Any] | None = None,
    ) -> str:
        """Encode a query or control using the last appliance status."""
        payload = {"deviceinfo": self.info, kind: value}
        if status is not None:
            payload["status"] = status
        with self.lock:
            return cast("str", self.lua.globals().jsonToData(json.dumps(payload)))

    def decode(self, msg: bytes) -> dict[str, Any]:
        """Decode appliance bytes into vendor status fields."""
        with self.lock:
            result = self.lua.globals().dataToJson(
                json.dumps({"deviceinfo": self.info, "msg": {"data": msg.hex()}}),
            )
            return cast("dict[str, Any]", json.loads(result).get("status", {}))


class VendorMixin:
    """Adapt model-specific payloads to the existing encrypted LAN transport."""

    _attributes: dict[str, Any]
    build_send: Callable[[Any], None]

    def _map_status(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _init_codec(self, dtype: int, kwargs: dict[str, Any]) -> None:
        self._vendor_codec = Codec(
            FILES[dtype, kwargs["model"], kwargs["subtype"]],
            kwargs["subtype"],
            kwargs.get("serial_number"),
        )
        self._vendor_status: dict[str, Any] = {}
        self._vendor_lock = threading.RLock()
        self._vendor_type = dtype

    def build_init_query(self) -> list[VendorFrame]:
        """Skip generic discovery commands for these exact models."""
        return []

    def _frame(self, kind: str, value: dict[str, Any]) -> VendorFrame:
        return VendorFrame(
            self._vendor_codec.encode(
                kind,
                value,
                self._vendor_status if kind == "control" else None,
            ),
            self._vendor_type,
            3 if kind == "query" else 2,
        )

    def build_query(self) -> list[VendorFrame]:
        """Return the model-specific polling sequence."""
        with self._vendor_lock:
            queries = (
                [(SoftStatusQuery, {})]
                if self._vendor_type == 237
                else [
                    (FreshStatusQuery, {}),
                    (FreshRunQuery, {"query_type": "run_status"}),
                    (FreshC003Query, {"query_type": "c003_query"}),
                ]
            )
            return [
                cls(self._vendor_codec.encode("query", q), self._vendor_type, 3)
                for cls, q in queries
            ]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Apply only appliance-reported state from supported message types."""
        if (
            len(msg) < 12
            or msg[0] != 170
            or msg[2] != self._vendor_type
            or msg[9] not in {2, 3, 4, 5}
        ):
            return {}
        with self._vendor_lock:
            data = self._vendor_codec.decode(msg)
            self._vendor_status.update(data)
            parsed = self._map_status(data)
            self._attributes.update(parsed)
            return parsed

    def _send_control(self, control: dict[str, Any]) -> None:
        with self._vendor_lock:
            if not self._vendor_status:
                raise ValueError("Wait for device status before control")
            frame = self._frame("control", control)
        self.build_send(frame)
        # No optimistic state: report only subsequent appliance acknowledgements.


# The upstream subclasses narrow query return types to their own packet classes.
class Softener845(VendorMixin, MideaEDDevice):  # type: ignore[misc]
    """Expose verified softener telemetry and bounded settings."""

    def __init__(self, **kwargs: Any) -> None:
        self._init_codec(237, kwargs)
        super().__init__(**kwargs)
        self._attributes = dict.fromkeys(SOFT_KEYS)
        self._attributes.update({"f08_" + k: None for k in SOFT_KEYS})

    def _map_status(self, data: dict[str, Any]) -> dict[str, Any]:
        parsed = {
            k: (v == "on" if v in {"on", "off"} else v)
            for k, v in data.items()
            if k in SOFT_KEYS
        }
        aliases = {"f08_" + k: v for k, v in parsed.items()}
        if "leak_water_protection_value" in parsed:
            aliases["f08_leak_water_protection_value"] = (
                parsed["leak_water_protection_value"] * 10
            )
        return {**parsed, **aliases}

    def set_attribute(self, attr: str, value: Any) -> None:
        """Validate a supported setting before sending a local command."""
        attr = str(attr).removeprefix("f08_")
        if attr in SOFT_SWITCHES and isinstance(value, bool):
            self._send_control({attr: "on" if value else "off"})
        elif (
            attr in {"water_hardness", "flushing_days"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and int(value) == value
            and (1 if attr == "water_hardness" else 0)
            <= value
            <= (999 if attr == "water_hardness" else 15)
        ):
            self._send_control({attr: int(value)})
        else:
            raise ValueError("Unsupported or unverified softener control")


# The upstream subclasses narrow query return types to their own packet classes.
class FreshAir24297131(VendorMixin, MideaACDevice):  # type: ignore[misc]
    """Control dedicated ventilation independently of AC thermostat commands."""

    def __init__(self, **kwargs: Any) -> None:
        self._init_codec(172, kwargs)
        super().__init__(**kwargs)
        self._attributes.update(
            dict.fromkeys(
                [
                    "fresh_air_power",
                    "fresh_air_fan_speed",
                    "fresh_air_mode",
                    "fresh_air_exhaust_power",
                    "fresh_air_exhaust_speed",
                    "fresh_air_exhaust_mode",
                    "ventilation_power",
                    "fresh_air_remove_odor",
                    "ventilation_mode",
                    "fresh_filter_time",
                    "fresh_filter_remaining",
                    "ventilation_preset",
                ],
            ),
        )

    @property
    def fresh_air_fan_speeds(self) -> list[str]:
        """Intake presets shared by the fan entity."""
        return list(SPEEDS.values())

    @property
    def fresh_air_exhaust_fan_speeds(self) -> list[str]:
        """Exhaust presets shared by the fan entity."""
        return list(SPEEDS.values())

    def _map_status(self, data: dict[str, Any]) -> dict[str, Any]:
        parsed = {}
        direct = {
            "indoor_temperature": "indoor_temperature",
            "new_wind_outdoor_temperature": "outdoor_temperature",
            "fresh_air_intake_fan_speed": "fresh_air_fan_speed",
            "fresh_air_exhaust_fan_speed": "fresh_air_exhaust_speed",
            "fresh_air_mode": "ventilation_mode",
            "fresh_filter_time": "fresh_filter_time",
        }
        for source, target in direct.items():
            if source in data:
                parsed[target] = data[source]
        for source, target in {
            "new_wind_machine": "ventilation_power",
            "new_wind_machine_intake_switch": "fresh_air_power",
            "new_wind_machine_exhaust_switch": "fresh_air_exhaust_power",
            "fresh_air_remove_odor": "fresh_air_remove_odor",
        }.items():
            if source in data:
                parsed[target] = data[source] in {1, "on"}
        if "fresh_air_mode" in data:
            parsed["ventilation_preset"] = data["fresh_air_mode"]
        if "fresh_filter_time" in data:
            used = data["fresh_filter_time"]
            parsed["fresh_filter_remaining"] = (
                max(0, 100 - used)
                if isinstance(used, (int, float)) and used >= 0
                else None
            )
        merged = {**self._attributes, **parsed}
        for prefix, speed in [
            ("fresh_air", "fresh_air_fan_speed"),
            ("fresh_air_exhaust", "fresh_air_exhaust_speed"),
        ]:
            power = merged.get(prefix + "_power")
            parsed[prefix + "_mode"] = (
                "off" if power is False else SPEEDS.get(merged.get(speed, -1))
            )
        return parsed

    def set_attribute(self, attr: str, value: Any) -> None:
        """Validate a supported setting before sending a local command."""
        attr = str(attr)
        flags = {
            "fresh_air_power": "new_wind_machine_intake_switch",
            "fresh_air_exhaust_power": "new_wind_machine_exhaust_switch",
            "ventilation_power": "new_wind_machine",
            "fresh_air_remove_odor": "fresh_air_remove_odor",
        }
        speeds = {
            "fresh_air_fan_speed": (
                "fresh_air_intake_fan_speed",
                "new_wind_machine_intake_switch",
            ),
            "fresh_air_exhaust_speed": (
                "fresh_air_exhaust_fan_speed",
                "new_wind_machine_exhaust_switch",
            ),
        }
        if attr in {"fresh_air_mode", "fresh_air_exhaust_mode"}:
            if value not in SPEEDS.values():
                raise ValueError("Unsupported speed preset")
            speed = next(k for k, v in SPEEDS.items() if v == value)
            return self.set_attribute(
                "fresh_air_fan_speed"
                if attr == "fresh_air_mode"
                else "fresh_air_exhaust_speed",
                speed,
            )
        if attr == "ventilation_preset":
            if isinstance(value, bool) or value not in VENTILATION_MODES:
                raise ValueError("Unsupported ventilation mode for this model")
            if self._vendor_status.get("special_machine_type") != 1:
                raise ValueError(
                    "Dedicated ventilation model not confirmed by appliance",
                )
            control = {"fresh_air_mode": int(value), "fresh_air_mode_enable": 1}
        elif attr in flags and isinstance(value, bool):
            field = flags[attr]
            control = {field: int(value), field + "_enable": 1}
        elif (
            attr in speeds
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and int(value) == value
            and 0 <= value <= 100
        ):
            field, power = speeds[attr]
            control = {power: int(value > 0), power + "_enable": 1}
            if value > 0:
                control.update({field: int(value), field + "_enable": 1})
        else:
            raise ValueError("Unsupported or unverified fresh-air control")
        # Force the documented C003 dedicated fresh-air command, not AC controls.
        control["new_wind_single_control"] = 1
        self._send_control(control)
        return None


# The upstream subclasses narrow query return types to their own packet classes.
class PipeDispenser1046(VendorMixin, MideaEDDevice):  # type: ignore[misc]
    """CWGR-A1 settings only; no remote dispensing, drain or heating commands."""

    def __init__(self, **kwargs: Any) -> None:
        self._init_codec(237, kwargs)
        super().__init__(**kwargs)
        for key in PIPE_SETTINGS:
            self._attributes["a1_" + key] = None

    def _map_status(self, data: dict[str, Any]) -> dict[str, Any]:
        parsed = {}
        for source, target in {
            "power": "power",
            "lock": "child_lock",
            "sleep": "sleep_status",
            "out_water": "out_water",
            "out_hot_water": "out_hot_water",
        }.items():
            if source in data:
                parsed[target] = data[source] in {True, "on"}
        for source, target in {
            "input_temperature_Sensing": "input_temperature_sensing",
            "water_kind": "water_kind",
            "cur_quantify": "cur_quantify",
        }.items():
            if source in data:
                parsed[target] = data[source]
        if "standby_status" in data:
            parsed["standby_status"] = data["standby_status"] in {True, "on"}
        if "water_consumption" in data:
            # Preserve upstream ED water-consumption scaling for existing history.
            parsed["water_consumption"] = data["water_consumption"] / 1000
        for key in PIPE_SETTINGS:
            if key not in data:
                continue
            value = data[key]
            if key == "human_sensing_switch":
                value = value in {True, "on"}
            elif key.startswith("quantify_"):
                value *= 10  # device units are 10 mL for preset slots 1..3
            parsed["a1_" + key] = value
        return parsed

    def set_attribute(self, attr: str, value: Any) -> None:
        """Validate a supported setting before sending a local command."""
        attr = str(attr).removeprefix("a1_")
        attr = {"child_lock": "lock"}.get(attr, attr)
        if attr in {"power", "lock", "human_sensing_switch"} and isinstance(
            value,
            bool,
        ):
            control = {attr: "on" if value else "off"}
        elif (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and int(value) == value
        ):
            value = int(value)
            if attr.startswith("custom_temperature_") and attr in PIPE_SETTINGS:
                maximum = 45 if attr.endswith("_1") else 99
                if not 35 <= value <= maximum:
                    raise ValueError("Temperature outside exact model range")
                control = {attr: value}
            elif attr in PIPE_VOLUMES and value in PIPE_VOLUMES[attr]:
                control = {attr: value // 10}
            elif (
                attr == "screenout_time"
                and value in {10, 30, 60, 120, 180, 300}
                or attr == "cur_quantify"
                and value in {0, 1, 2, 3}
            ):
                control = {attr: value}
            else:
                raise ValueError("Unsupported pipeline-machine setting")
        else:
            raise ValueError("Unsupported pipeline-machine control")
        self._send_control(control)


def device_selector(*args: Any, **kwargs: Any) -> MideaDevice | None:
    """Dispatch exact model/subtype pairs and preserve upstream selection otherwise."""
    bound = inspect.signature(upstream_selector).bind(*args, **kwargs)
    bound.apply_defaults()
    values = bound.arguments
    key = (int(values["device_type"]), values["model"], int(values["subtype"]))
    if key not in FILES:
        return upstream_selector(*args, **kwargs)
    values = dict(values)
    values.pop("device_type")
    cls = {
        (237, "6360000F", 845): Softener845,
        (237, "6320088A", 1046): PipeDispenser1046,
        (172, "24297131", 1): FreshAir24297131,
    }[key]
    return cls(**values)
