"""Local control catalog for three appliance models. No cloud requests at runtime."""

from .catalog import CATALOG
from .protocol import signed


def group(device, allow_cycle=False):
    catalog = CATALOG[f"{device.kind:02x}"]
    if device.kind != 0xE1 or allow_cycle:
        return catalog
    filtered = {}
    for key, spec in catalog.items():
        if key == "wash_mode":
            continue
        if key in ("work_status", "airswitch", "dryswitch"):
            spec = {
                **spec,
                "commands": {
                    option: body
                    for option, body in spec["commands"].items()
                    if option not in ("power_on", "resume", "running")
                },
            }
        filtered[key] = spec
    return filtered


def status_fields(device, raw):
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
            "operator_paused": b[1] in (2, 3) and not b[5] & 8,
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
        flags = {
            "power": (12, 0),
            "cold_water": (12, 2),
            "bathtub": (12, 6),
            "safe": (18, 3),
            "cold_water_master": (30, 7),
            "cold_water_dot": (30, 0),
            "change_litre_switch": (30, 1),
            "cold_water_ai": (31, 5),
            "cold_water_pressure": (30, 2),
            "person_mode_one": (30, 3),
            "person_mode_two": (30, 4),
            "person_mode_three": (30, 5),
            "high_temp_lock": (31, 6),
        }
        result = {
            k: ("on" if b[i] & (1 << n) else "off")
            for k, (i, n) in flags.items()
            if len(b) > i
        }
        result.update(water_heater=str(b[16]), bathtub_water_level=b[20] * 256 + b[19])
        for k, i in {
            "person_tem_one": 32,
            "person_tem_two": 33,
            "person_tem_three": 39,
        }.items():
            if len(b) > i:
                result[k] = b[i]
        if len(b) > 34:
            result["bubble"] = "on" if b[34] & 192 else "off"
        for i, bit, mode in [
            (12, 3, "shower"),
            (12, 4, "kitchen"),
            (12, 5, "thalposis"),
            (12, 7, "intelligence"),
            (26, 0, "eco"),
            (26, 1, "unfreeze"),
            (26, 2, "wash_bowl"),
            (26, 3, "high_temperature"),
            (26, 4, "baby"),
            (26, 5, "adult"),
            (26, 6, "old"),
        ]:
            if b[i] & (1 << bit):
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
        if kind == 2 and len(p) >= 3 and p[0] in (1, 2, 3):
            key = ("left_stove_off", "right_stove_off", "middle_stove_off")[p[0] - 1]
            result[key] = (
                "off" if p[1] in (0, 1) else "working" if p[1] in (2, 3, 4) else None
            )
        if kind == 9 and p and p[0] in (0, 1):
            result["ai_butler"] = "on" if p[0] else "off"
        if kind != 1:
            continue
        if len(p) > 1 and p[1] != 255:
            result["power"] = "off" if p[1] in (0, 1, 5, 7) else "on"
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


def command(device, key, option, observed, *, allow_cycle=False):
    spec = group(device, allow_cycle)[key]
    if option not in spec["commands"]:
        raise ValueError("Unsupported option")
    body = bytearray.fromhex(spec["commands"][option])
    if device.kind in (0xE1, 0xE3):
        body.extend(bytes((38 if device.kind == 0xE1 else 20) - len(body)))
    if dep := spec.get("include"):
        name, index = dep
        current = observed.get(name)
        if type(current) is not int or not 0 <= current <= 255:
            raise ValueError("Required companion setting unavailable")
        body[index] = current
    fields = bytes([len(body) + 10, device.kind, 0, 0, 0, 0, 0, 0, 2]) + body
    return b"\xaa" + signed(fields)


def matches(key, option, observed):
    if key == "work_status":
        if option == "pause":
            return observed.get("operator_paused") is True
        if option == "resume":
            return observed.get("operator_started") is True
        if option == "power_on":
            return observed.get(key) == "cancel"
    if key.endswith("_stove_off"):
        return observed.get(key) == "off"
    return observed.get(key) == option
