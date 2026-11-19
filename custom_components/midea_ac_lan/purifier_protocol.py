"""Native 632009CN purifier protocol; no cloud or vendor runtime dependency."""

# Wire offsets and ranges are the model's protocol, not application constants.
# ruff: file-ignore[magic-value-comparison, any-type, docstring-missing-returns, docstring-missing-exception, too-many-boolean-expressions]

from typing import Any

from .local_protocol import frame

VOLUMES = {
    "quantify_21": (200, 1000),
    "quantify_22": (200, 3000),
    "quantify_23": (1000, 5000),
}
SWITCHES = {
    "power": 0x100,
    "sleep": 0x104,
    "lock": 0x201,
    "no_obsolete_water": 0x20B,
    "wash": 0x300,
}
FIELDS = {
    0x001: (("error", 0, 1),),
    0x010: (("life_1", 0, 1), ("life_2", 1, 1)),
    0x011: (("water_consumption", 0, 4),),
    0x013: (("in_tds", 0, 2), ("out_tds", 2, 2)),
    0x014: (("countdown_filter_1", 0, 1), ("countdown_filter_2", 1, 1)),
    0x016: (("maxlife_1", 0, 1), ("maxlife_2", 1, 1)),
    0x021: (("custom_temperature_1", 0, 1),),
    0x023: (("cur_quantify", 5, 1),),
    0x038: (("quantify_21", 0, 2), ("quantify_22", 2, 2), ("quantify_23", 4, 2)),
}
FLAGS = {
    0x000: (
        ("filter", 0, 0),
        ("wash", 0, 2),
        ("standby_status", 0, 3),
        ("heat_status", 1, 5),
        ("lock", 2, 0),
        ("out_water", 2, 1),
        ("lack_water", 2, 2),
        ("out_hot_water", 2, 6),
        ("power", 3, 0),
        ("sleep", 3, 1),
        ("backflow", 3, 5),
    ),
    0x03C: (("no_obsolete_water", 0, 6),),
}


def purifier_query() -> bytes:
    """Request the complete model status."""
    return frame(0xED, 3, b"\xff\x01")


def purifier_control(name: str, value: Any) -> bytes:
    """Encode one bounded setting, never a dispensing or filter-reset command."""
    if name in VOLUMES:
        low, high = VOLUMES[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not low <= value <= high
            or value % 10
        ):
            raise ValueError("Volume must be in the model range in 10 mL steps")
        tag = 0x202
        payload = bytes((int(name[-2:]),)) + int(value).to_bytes(2, "little")
    elif name == "cur_quantify":
        if type(value) is not int or value not in {0, 21, 22, 23}:
            raise ValueError("Unsupported purifier preset")
        tag, payload = 0x20D, bytes((value, 0, 0))
    elif name in SWITCHES:
        if type(value) is not bool:
            raise ValueError("Purifier switch requires a boolean")
        tag, payload = SWITCHES[name], bytes((int(value), 0, 0))
    else:
        raise ValueError("Unsupported purifier control")
    return frame(0xED, 2, b"\x15\x01\x01" + tag.to_bytes(2, "little") + payload)


def purifier_status(msg: bytes) -> dict[str, Any]:
    """Atomically decode checked FF records; ACKs do not confirm a setting."""
    if (
        len(msg) < 14
        or msg[0] != 0xAA
        or msg[1] != len(msg) - 1
        or msg[2] != 0xED
        or msg[9] not in {3, 4}
        or sum(msg[1:]) & 255
        or msg[10:12] != b"\xff\x01"
    ):
        return {}
    result: dict[str, Any] = {}
    end, offset = len(msg) - 1, 13
    while offset < end:
        if offset + 2 > end:
            return {}
        tag = msg[offset] | ((msg[offset + 1] & 15) << 8)
        length = msg[offset + 1] >> 4
        offset += 2
        if not length or offset + length > end:
            return {}
        payload = msg[offset : offset + length]
        for name, start, width in FIELDS.get(tag, ()):
            if start + width > length:
                return {}
            result[name] = int.from_bytes(payload[start : start + width], "little")
        for name, start, bit in FLAGS.get(tag, ()):
            if start >= length:
                return {}
            result[name] = bool(payload[start] & (1 << bit))
        offset += length
    return result
