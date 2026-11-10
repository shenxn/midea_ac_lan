"""Exact-model BLE addresses, query codecs, and reversible settings."""

from dataclasses import dataclass
from . import dishwasher
from .protocol import signed


@dataclass(frozen=True)
class Appliance:
    model: str
    sn8: bytes
    kind: int
    name: str
    query: bytes


HOOD = Appliance(
    "CXEP930W-C3 AIR",
    b"730006AE",
    0xB6,
    "油烟机",
    bytes.fromhex("aa0bb600000000000003112b"),
)
HEATER = Appliance(
    "JSLQ27-CTE816",
    b"5111102Z",
    0xE3,
    "燃气热水器",
    bytes.fromhex("aa1ee3000000000000030101000000000000000000000000000000000000fa"),
)
DISH = Appliance("CDG16QA83K", b"7600002B", 0xE1, "洗碗机", dishwasher.QUERY)
DEVICES = {device.sn8.decode(): device for device in (HOOD, HEATER, DISH)}


def parse(device, raw):
    if device == DISH:
        return dishwasher.parse_status(raw)
    if (
        len(raw) < 13
        or raw[0] != 170
        or raw[2] != device.kind
        or raw[1] + 1 != len(raw)
        or sum(raw[1:]) % 256
        or raw[9] != 3
    ):
        raise ValueError("Invalid appliance status")
    if device == HEATER and raw[10:12] == b"\x01\x01" and len(raw) >= 40:
        return {
            "power": bool(raw[12] & 1),
            "burning": bool(raw[12] & 2),
            "temperature": raw[16],
            "outlet": raw[15],
            "beep": bool(raw[38] & 16),
        }
    if device == HOOD and raw[8] == 2:
        pos = 11
        while pos + 2 <= len(raw) - 1:
            kind, length = raw[pos : pos + 2]
            if pos + 2 + length > len(raw) - 1:
                break
            pkg = raw[pos + 2 : pos + 2 + length]
            if kind == 1 and len(pkg) >= 7 and 255 not in (pkg[1], pkg[2], pkg[6]):
                return {
                    "power": pkg[1] not in (0, 1, 5, 7),
                    "gear": pkg[2],
                    "light": bool(pkg[6]),
                }
            pos += 2 + length
    raise ValueError("Unsupported status format")


def idle(device, state):
    if device == DISH:
        return state["status"] == 0 and not state["operator"]
    if device == HOOD:
        return not state["power"] and state["gear"] == 0
    return not state["power"] and not state["burning"]


def setting(device, key, value):
    if device == DISH:
        return dishwasher.setting_frame(key, value)
    if type(value) is not bool:
        raise ValueError("Invalid switch value")
    if device == HOOD and key == "light":
        fields = bytearray.fromhex("12b6000000000000021101020200ffffff")
        fields[13] = int(value)
    elif device == HEATER and key == "beep":
        fields = bytearray.fromhex(
            "1ee3000000000000021415000000000000000000000000000000000000"
        )
        fields[11] = fields[28] = int(value)
    else:
        raise ValueError("Unsupported appliance setting")
    return b"\xaa" + signed(fields)
