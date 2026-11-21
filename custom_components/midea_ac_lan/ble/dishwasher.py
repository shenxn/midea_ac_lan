"""CDG16QA83K status and isolated user preferences."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-returns, docstring-missing-exception, magic-value-comparison, too-many-boolean-expressions]
from typing import Any

# BLE state and catalog mappings contain heterogeneous protocol values.
from .protocol import signed


def appliance(body: bytes | bytearray, kind: int) -> bytes:
    """Wrap the dishwasher body with a checked UART header."""
    fields = bytes([10 + len(body), 0xE1, 0, 0, 0, 0, 0, 0, kind]) + body
    return b"\xaa" + signed(fields)


QUERY = appliance(b"\x00", 3)


def setting_frame(key: str, enabled: bool) -> bytes:
    """Encode a bounded dishwasher preference."""
    if type(enabled) is not bool:
        raise ValueError("Invalid setting value")
    body = bytearray(38)
    if key == "beep":
        body[:16] = b"\xff" * 16
        body[0:2] = b"\x90\x05"
        body[6] = int(enabled)
    elif key == "child_lock":
        body[:2] = bytes((0x83, 3 if enabled else 4))
    else:
        raise ValueError("Unsupported setting")
    return appliance(body, 2)


def parse_status(frame: bytes) -> Any:
    """Validate and decode the dishwasher status response."""
    if (
        len(frame) < 50
        or frame[:1] != b"\xaa"
        or frame[2] != 0xE1
        or len(frame) != frame[1] + 1
        or sum(frame[1:]) % 256
        or frame[9:11] != b"\x03\x00"
    ):
        raise ValueError("Unexpected E1 query response")
    b = frame[10:-1]
    return {
        "status": b[1],
        "program": b[2],
        "stage": b[9],
        "error": b[10],
        "temperature": b[11],
        "remaining": b[6] + 256 * b[32],
        "door": bool(b[5] & 1),
        "low_rinse": bool(b[5] & 2),
        "low_salt": bool(b[5] & 4),
        "water_lack": bool(b[5] & 128),
        "child_lock": bool(b[5] & 16),
        "beep": bool(b[37] & 32),
        "auto_door": bool(b[4] & 64),
        "light": bool(b[37] & 128),
        "storage": bool(b[5] & 64),
        "storage_remaining": b[18],
        "salt_level": b[13],
        "rinse_level": b[24],
        "humidity": b[33],
        "operator": bool(b[5] & 8),
    }
