"""COLMO CWRC-S1000 status records and isolated control commands."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-returns, docstring-missing-exception, magic-value-comparison]
from typing import Any

SENSORS = {
    "in_tds": ("进水 TDS", "mg/L"),
    "out_tds": ("出水 TDS", "mg/L"),
    "ro_life": ("RO 滤芯剩余寿命", "%"),
    "pcb_life": ("PCB 滤芯剩余寿命", "%"),
    "inlet": ("进水温度", "°C"),
    "error": ("故障代码", None),
}

BINARY = {
    "standby": "待机",
    "out_water": "正在出水",
    "lack_water": "缺水",
}

_SWITCHES = {
    "wash": ("冲洗", "0003"),
    "drainage": ("排水", "0402"),
    "antifreeze": ("防冻", "0305"),
}
CONTROLS: dict[str, dict[str, Any]] = {
    **{
        key: {
            "platform": "switch",
            "name": name,
            "commands": {
                "off": "150101" + tag + "000000",
                "on": "150101" + tag + "010000",
            },
        }
        for key, (name, tag) in _SWITCHES.items()
    },
    "zero_water_mode": {
        "platform": "select",
        "name": "智享零陈水",
        "commands": {
            "关闭": "1501010f02000000",
            "标准模式": "1501030f020100000b020100001302000000",
            "极致模式": "1501030f0201000013020100000b02000000",
        },
    },
}

# (name, offset, byte width); numeric values are little-endian.
_NUMBERS = {
    0x001: (("error", 0, 1),),
    0x010: (("ro_life", 0, 1), ("pcb_life", 1, 1)),
    0x013: (("in_tds", 0, 2), ("out_tds", 2, 2)),
    0x207: (("inlet", 0, 1),),
}
_FLAGS = {
    0x000: (
        ("wash", 0, 2),
        ("standby", 0, 3),
        ("out_water", 2, 1),
        ("lack_water", 2, 2),
        ("drainage", 2, 5),
        ("power", 3, 0),
    ),
    0x03C: (
        ("antifreeze", 0, 0),
        ("no_obsolete_water", 0, 6),
        ("smart_no_obsolete_water", 1, 3),
        ("extreme_mode", 2, 5),
    ),
}


def parse_body(body: bytes) -> Any:
    """Decode complete purifier records without inventing missing fields."""
    if body[:3] != bytes.fromhex("ff0103"):
        raise ValueError("Unsupported purifier status format")
    state: dict[str, Any] = {}
    offset = 3
    while offset < len(body):
        header = body[offset : offset + 2]
        if len(header) != 2:
            raise ValueError("Truncated purifier record")
        tag = header[0] | ((header[1] & 15) << 8)
        size = header[1] >> 4
        value = body[offset + 2 : offset + 2 + size]
        if len(value) != size:
            raise ValueError("Truncated purifier value")
        for key, start, width in _NUMBERS.get(tag, ()):
            if start + width > size:
                raise ValueError("Short purifier numeric field")
            state[key] = int.from_bytes(
                value[start : start + width],
                "little",
                signed=key == "inlet",
            )
        for key, start, bit in _FLAGS.get(tag, ()):
            if start >= size:
                raise ValueError("Short purifier flag field")
            state[key] = bool(value[start] & (1 << bit))
        offset += size + 2
    if "power" not in state:
        raise ValueError("Incomplete purifier status")
    controls = {key: "on" if state[key] else "off" for key in _SWITCHES if key in state}
    if "smart_no_obsolete_water" in state:
        if not state["smart_no_obsolete_water"]:
            controls["zero_water_mode"] = "关闭"
        elif state.get("no_obsolete_water"):
            controls["zero_water_mode"] = "标准模式"
        else:
            controls["zero_water_mode"] = "极致模式"
    state["controls"] = controls
    return state
