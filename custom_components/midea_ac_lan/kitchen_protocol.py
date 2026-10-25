"""Verified CAC36QN1E1 kitchen functions carried in the nested JZ protocol."""

# Numeric positions are defined by this exact model's wire format.
# ruff: file-ignore[magic-value-comparison, docstring-missing-returns, docstring-missing-exception, too-many-boolean-expressions]

from .local_protocol import ac_envelope, crc8, frame

KITCHEN_SWITCHES = {"prepare_food": 6, "quick_fry": 7}


def kitchen_query() -> bytes:
    """Query the C002 kitchen capabilities and status over LAN."""
    return frame(0xAC, 3, ac_envelope(0xC0, b"\x00\x01\xc0\x02", 0))


def kitchen_control(name: str, enabled: bool) -> bytes:
    """Set exactly one supported switch without changing other setting masks."""
    if name not in KITCHEN_SWITCHES or not isinstance(enabled, bool):
        raise ValueError("Unsupported kitchen control")
    data = bytearray(82)
    data[:3] = b"\x00\x01\x01"
    data[11:15] = b"\x01\xc0\x02\x46"
    data[21] = 1 << KITCHEN_SWITCHES[name]
    data[22] = data[21] if enabled else 0
    data[81] = -sum(data[12:81]) & 0xFF
    return frame(0xAC, 2, ac_envelope(0xC0, bytes(data), 0))


def kitchen_status(msg: bytes) -> dict[str, bool | int]:
    """Decode supported fields only after validating both frame checksums."""
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
    if body[5] != 0xC0 or len(data) < 41 or data[1:4] != b"\x01\xc0\x02":
        return {}
    result: dict[str, bool | int] = {}
    for name, bit in KITCHEN_SWITCHES.items():
        result["kitchen_has_" + name] = bool(data[12] & (1 << bit))
        if result["kitchen_has_" + name]:
            result["kitchen_" + name] = bool(data[13] & (1 << bit))
    if data[40] & 0x80:
        result["kitchen_food_angle"] = data[40] & 0x7F
    return result
