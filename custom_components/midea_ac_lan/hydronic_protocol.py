"""Exact 22397091 water-module frames, independent of cloud and vendor runtimes."""

# Offsets and masks describe this model's nested wire protocol.
# ruff: file-ignore[magic-value-comparison, docstring-missing-returns, docstring-missing-exception, too-many-boolean-expressions]

import math
from typing import Any

from .local_protocol import ac_envelope, crc8, frame

FLAGS = {"power": 0, "power_save": 1, "temperature_auto": 3, "ptc": 4, "go_out": 5}


def hydronic_query() -> bytes:
    """Read water telemetry without changing any operating state."""
    return frame(0xAC, 3, ac_envelope(0x12, b""))


def hydronic_control(name: str, value: bool | float) -> bytes:
    """Set one function; a manual setpoint also disables automatic temperature."""
    data = bytearray(82)
    data[:3] = b"\x00\x01\x01"
    data[11:15] = b"\x01\xc0\x02\x46"
    if name in FLAGS and isinstance(value, bool):
        data[42] = 1 << FLAGS[name]
        data[43] = data[42] if value else 0
    elif (
        name == "temperature_set"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        if not math.isfinite(value) or not 25 <= value <= 60 or int(value) != value:
            raise ValueError(
                "Water temperature must be a whole degree between 25 and 60",
            )
        data[42] = 8
        data[44] = 64
        data[45] = int(value) * 2 + 50
    else:
        raise ValueError("Unsupported hydronic control")
    data[81] = -sum(data[12:81]) & 0xFF
    return frame(0xAC, 2, ac_envelope(0xC0, bytes(data), 0))


def hydronic_status(msg: bytes) -> dict[str, Any]:
    """Decode validated status; never confuse room setpoint with water temperature."""
    if (
        len(msg) < 19
        or msg[0] != 0xAA
        or msg[1] != len(msg) - 1
        or msg[2] != 0xAC
        or msg[9] not in {2, 3, 4, 5}
        or sum(msg[1:]) & 0xFF
    ):
        return {}
    body = msg[10:-1]
    if (
        body[0] not in {0xAA, 0xBB}
        or body[1] != len(body)
        or sum(body) & 0xFF
        or crc8(body[:-2]) != body[-2]
    ):
        return {}
    data = body[6:-2]
    result: dict[str, Any] = {}
    if body[5] == 0x11 and len(data) >= 21:
        result["has"] = bool(data[20] & 64)
        for name, bit in FLAGS.items():
            result[name] = bool(data[17] & (1 << (7 if name == "go_out" else bit)))
        result["temperature_set"] = (data[19] - 50) / 2
    elif body[5] == 0xC0 and len(data) >= 37 and data[1:4] == b"\x01\xc0\x02":
        result["has_temperature_set"] = bool(data[35] & 64)
        for name, bit in FLAGS.items():
            result[name] = bool(data[34] & (1 << bit))
        result["temperature_set"] = (data[36] - 50) / 2
    elif body[5] == 0x12 and len(data) >= 10:
        for name, offset in (("in_temperature", 6), ("out_temperature", 8)):
            result[name] = (
                int.from_bytes(data[offset : offset + 2], "little", signed=True) / 100
            )
    return {"hydronic_" + key: value for key, value in result.items()}
