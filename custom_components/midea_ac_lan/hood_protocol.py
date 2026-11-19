"""Native 730007C9 hood settings and checked, non-optimistic status decoding."""

# ruff: file-ignore[magic-value-comparison, docstring-missing-returns, docstring-missing-exception, any-type, too-many-boolean-expressions]
from typing import Any

from .local_protocol import frame

SETTINGS = {"gesture": 3, "linkage": 8}


def hood_control(name: str, value: Any) -> bytes:
    """Encode only known hood settings; never issue a stove or cleaning command."""
    if type(value) is not bool:
        raise ValueError("Hood settings require a boolean")
    if name in SETTINGS:
        body = bytes((0x11, 1, 2, SETTINGS[name], int(value)))
        if name == "gesture":
            body += b"\xff\xff"
    elif name == "wisdom_wind":
        body = bytes((0x11, 1, 1, 0xFF, 0x0D, 1 if value else 2, 0xFF, 0xFF))
    else:
        raise ValueError("Unsupported hood setting")
    return frame(0xB6, 2, body)


def hood_status(msg: bytes) -> dict[str, Any]:
    """Decode complete v2 B6 records, skipping unsupported sentinel fields."""
    if (
        len(msg) < 14
        or msg[0] != 0xAA
        or msg[1] != len(msg) - 1
        or msg[2] != 0xB6
        or msg[8] != 2
        or msg[9] not in {3, 4}
        or msg[10] != 0x11
        or sum(msg[1:]) & 255
    ):
        return {}
    result: dict[str, Any] = {}
    position = 11
    # The final byte before the checksum is the message sequence number.
    end = len(msg) - 2
    while position < end:
        if position + 2 > end:
            return {}
        tag, size = msg[position : position + 2]
        position += 2
        if position + size > end:
            return {}
        p = msg[position : position + size]
        position += size
        if tag != 1:
            continue
        if size < 20:
            return {}
        if p[1] != 255:
            result["wisdom_wind"] = p[1] == 13
        if p[12] != 255:
            result["linkage"] = p[12] != 0
        if p[13] != 255:
            result["gesture"] = p[13] >= 128
        if p[19] != 255:
            result["error_code"] = p[19]
        if size >= 29 and p[27] != 255:
            result["wind_pressure"] = int.from_bytes(p[27:29], "big")
    return result
