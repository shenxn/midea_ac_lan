"""Local control catalog for three appliance models. No cloud requests at runtime."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-returns, docstring-missing-exception, magic-value-comparison, ambiguous-unicode-character-string]
from typing import Any

# BLE state and catalog mappings contain heterogeneous protocol values.
from .catalog import CATALOG
from .protocol import signed
from .purifier import CONTROLS


def group(device: Any, allow_cycle: bool = False) -> Any:
    """Return the model catalog with cycle-start commands gated by opt-in."""
    if device.kind == 0xED:
        return CONTROLS
    catalog = CATALOG[f"{device.kind:02x}"]
    if device.kind != 0xE1 or allow_cycle:
        return catalog
    filtered = {}
    for key, original_spec in catalog.items():
        spec = original_spec
        if key == "wash_mode":
            continue
        if key in {"work_status", "airswitch", "dryswitch"}:
            spec = {
                **spec,
                "commands": {
                    option: body
                    for option, body in spec["commands"].items()
                    if option not in {"power_on", "resume", "running"}
                },
            }
        filtered[key] = spec
    return filtered


def status_fields(device: Any, raw: bytes) -> Any:  # ruff: ignore[complex-structure, too-many-statements] - Keep exact-model wire field tables together for auditing.
    """Decode controls from the model-specific reported status."""
    result: dict[str, Any]
    if device.kind == 0xE1:
        b = raw[10:-1]
        flags = b[4]
        result = {
            "waterswitch": "on" if flags & 4 else "off",
            "uvswitch": "on" if flags & 2 else "off",
            "airswitch": "running"
            if b[5] & 64
            else "waiting"
            if b[5] & 32
            else "cancel",
            "dryswitch": "running"
            if flags & 32
            else "waiting"
            if flags & 16
            else "cancel",
            "dry_step_switch": "cancel" if flags & 1 else "waiting",
            "air_set_hour": str(b[17]),
            "work_status": {
                0: "power_off",
                1: "cancel",
                2: "order",
                3: "work",
                4: "error",
            }.get(b[1]),
            "operator_paused": b[1] in {2, 3} and not b[5] & 8,
            "operator_started": bool(b[5] & 8),
        }
        if len(b) > 61:
            result["knock_sensor_door_action"] = "on" if b[61] & 32 else "off"
        modes = {
            int(body[4:6], 16): name
            for name, body in group(device, True)
            .get("wash_mode", {})
            .get("commands", {})
            .items()
            if body.startswith("0803") and len(body) >= 6
        }
        result["wash_mode"] = (
            modes.get(b[2]) if b[1] == 3 else "待机（停止）" if b[1] == 0 else None
        )
        return result
    if device.kind == 0xE3:
        b = raw[:-1]
        heater_flags = {
            "power": (12, 0),
            "cold_water_master": (30, 7),
            "cold_water_dot": (30, 0),
            "cold_water_pressure": (30, 2),
        }
        result = {
            k: ("on" if b[i] & (1 << n) else "off")
            for k, (i, n) in heater_flags.items()
            if len(b) > i
        }
        result["water_heater"] = str(b[16])
        if len(b) > 38:
            result["cold_water_conservation"] = (
                "节能零冷水" if b[38] & 64 else "保温零冷水"
            )
        if len(b) > 40:
            result["cold_hold_duration"] = str(b[40])
        if len(b) > 50:
            result["new_filter_reset"] = "abnormal" if b[50] & 8 else "normal"
        for i, bit, mode in [
            (12, 3, "标准洗"),
            (26, 4, "婴儿浴"),
            (26, 0, "ECO"),
        ]:
            if len(b) > i and b[i] & (1 << bit):
                result["mode"] = mode
                break
        return result
    result = {}
    i = 11
    while i + 2 <= len(raw) - 1:
        kind, size = raw[i : i + 2]
        p = raw[i + 2 : i + 2 + size]
        i += 2 + size
        if i > len(raw) - 1:
            break
        if kind == 2 and len(p) >= 3 and p[0] in {1, 2, 3}:
            key = ("left_stove_off", "right_stove_off", "middle_stove_off")[p[0] - 1]
            result[key] = (
                "off" if p[1] in {0, 1} else "working" if p[1] in {2, 3, 4} else None
            )
        if kind == 9 and p and p[0] in {0, 1}:
            result["ai_butler"] = "on" if p[0] else "off"
        if kind != 1:
            continue
        if len(p) > 1 and p[1] != 255:
            result["power"] = "off" if p[1] in {0, 1, 5, 7} else "on"
            result["wisdom_wind"] = "on" if p[1] == 13 else "off"
            result["inverter"] = "on" if p[1] == 8 else "off"
        if len(p) > 2:
            result["gear"] = {
                0: "off",
                1: "low",
                2: "medium",
                3: "high",
                4: "extreme",
            }.get(p[2])
        if len(p) > 7 and p[7] != 255:
            result["lightness"] = str(p[7])
        for key, index, threshold in [
            ("linkage", 12, 0),
            ("smoke_detector", 10, 7),
            ("air_curtain_switch", 51, 0),
        ]:
            if len(p) > index and p[index] != 255:
                result[key] = "on" if p[index] > threshold else "off"
        if len(p) > 13 and p[13] != 255:
            result["gesture"] = "on" if p[13] & 128 else "off"
            result["gesture_value"] = {
                1: "power_toggle",
                2: "adjust_speed",
                3: "light_toggle",
                4: "power_and_speed",
            }.get(p[13] & 15)
            result["gesture_sensitivity_value"] = {
                1: "low",
                2: "medium",
                3: "high",
            }.get((p[13] >> 4) & 7)
    return result


def command(
    device: Any,
    key: str,
    option: str,
    observed: Any,
    *,
    allow_cycle: bool = False,
) -> bytes:
    """Encode a catalog command with any required current companion setting."""
    spec = group(device, allow_cycle)[key]
    if option not in spec["commands"]:
        raise ValueError("Unsupported option")
    body = bytearray.fromhex(spec["commands"][option])
    if device.kind in {0xE1, 0xE3}:
        body.extend(bytes((38 if device.kind == 0xE1 else 20) - len(body)))
    if dep := spec.get("include") or spec.get("include_for", {}).get(option):
        name, index, *bounds = dep
        low, high = bounds if bounds else (0, 255)
        current = observed.get(name)
        if isinstance(current, str) and current.isdigit():
            current = int(current)
        if type(current) is not int or not low <= current <= high:
            raise ValueError("Required companion setting unavailable")
        body[index] = current
    fields = bytes([len(body) + 10, device.kind, 0, 0, 0, 0, 0, 0, 2]) + body
    return b"\xaa" + signed(fields)


def matches(key: str, option: str, observed: dict[str, object]) -> bool:
    """Check whether device readback confirms the requested setting."""
    if key == "work_status":
        if option == "pause":
            return observed.get("operator_paused") is True
        if option == "resume":
            return observed.get("operator_started") is True
        if option == "power_on":
            return observed.get(key) == "cancel"
    if key.endswith("_stove_off"):
        return observed.get(key) == "off"
    if key == "cold_hold_duration":
        return (
            observed.get(key) == option
            and observed.get("cold_water_conservation") == "保温零冷水"
        )
    if key == "new_filter_reset":
        return observed.get(key) == "normal"
    return observed.get(key) == option
