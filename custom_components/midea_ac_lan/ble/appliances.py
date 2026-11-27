"""Exact-model BLE addresses, query codecs, and reversible settings."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-returns, docstring-missing-exception, magic-value-comparison, too-many-boolean-expressions]
from dataclasses import dataclass
from typing import Any

from . import dishwasher, purifier
from .protocol import signed

RATED_LITRE = {
    0: 6,
    4: 8,
    8: 10,
    12: 12,
    16: 14,
    24: 20,
    28: 13,
    32: 15,
    36: 18,
    40: 11,
    44: 17,
}
HEATER_ERRORS = (
    (13, 0, "E0"),
    (13, 1, "E1"),
    (13, 2, "E2"),
    (13, 3, "E3"),
    (13, 4, "E4"),
    (13, 5, "E5"),
    (13, 6, "E6"),
    (13, 7, "E8"),
    (14, 0, "EA"),
    (14, 1, "EE"),
    (37, 0, "F2"),
    (37, 1, "C0"),
    (37, 2, "C1"),
    (37, 3, "C2"),
    (37, 4, "C3"),
    (37, 5, "C4"),
    (37, 6, "C5"),
    (37, 7, "C6"),
    (38, 0, "C7"),
    (38, 1, "C8"),
    (38, 2, "EH"),
    (38, 7, "EF"),
    (48, 2, "CE"),
)


def _heater_error(b: bytes) -> str:
    """Decode the active E3 fault code from status payload bytes."""
    for index, bit, code in HEATER_ERRORS:
        if len(b) > index and b[index] & (1 << bit):
            return code
    return "无故障"


def _parse_heater(raw: bytes) -> dict[str, Any]:
    """Decode exact-model 5111102Z gas water heater telemetry."""
    b = raw[:-1]
    power = bool(b[12] & 1)
    burning = bool(b[12] & 2)
    rated_litre = RATED_LITRE.get(b[25] & 0xFC, 16)
    error_code = _heater_error(b)
    water_volume = b[17]
    zero_cold_active = bool(b[31] & 0x0E)
    if error_code != "无故障":
        work_status = "有故障"
    elif not power:
        work_status = "已关机"
    elif burning and zero_cold_active:
        work_status = "零冷水·加热中"
    elif not burning and zero_cold_active:
        work_status = "零冷水·保温中"
    elif burning and water_volume > 27:
        work_status = "加热中"
    else:
        work_status = "待机中"
    state: dict[str, Any] = {
        "power": power,
        "burning": burning,
        "temperature": b[16],
        "outlet": b[15],
        "beep": bool(b[38] & 16),
        "work_status": work_status,
        "inlet": b[36],
        "return_water": b[24],
        "water_flow": round(water_volume / 10, 1),
        "gas_lift_percent": (
            min(100, int(b[28] / rated_litre * 100)) if burning else 0
        ),
        "change_litre": b[28] if (b[30] & 2) and burning else rated_litre,
        "error_code": error_code,
    }
    if len(b) > 44:
        state["cold_conservation_duration"] = round(b[44] / 10, 1)
    if len(b) > 50:
        state["new_filter_problem"] = bool(b[50] & 8)
        state["cruise_antifreeze"] = not bool(b[50] & 1)
        state["cruise_antifreeze_error"] = bool(b[50] & 2)
    return state


@dataclass(frozen=True)
class Appliance:
    """Appliance interface for exact-model Bluetooth appliances."""

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
PURIFIER = Appliance(
    "CWRC-S1000",
    b"63200872",
    0xED,
    "净水机",
    b"\xaa" + signed(bytes.fromhex("0ced00000000000003ff01")),
)
DEVICES = {device.sn8.decode(): device for device in (HOOD, HEATER, DISH, PURIFIER)}
COLMO_COMPANY_ID = 1704
_AD_TYPE_MANUFACTURER_DATA = 0xFF
_MIN_MANUFACTURER_AD_LEN = 3


def _manufacturer_payloads(info: Any) -> list[bytes]:
    """Return COLMO manufacturer payloads from parsed data and raw AD structures."""
    payloads: list[bytes] = []
    mdata = getattr(info, "manufacturer_data", None)
    if mdata and (parsed := mdata.get(COLMO_COMPANY_ID)):
        payloads.append(parsed)
    raw = getattr(info, "raw", None)
    if not isinstance(raw, (bytes, bytearray)):
        return payloads
    pos = 0
    total = len(raw)
    while pos < total:
        length = raw[pos]
        end = pos + 1 + length
        if length == 0 or end > total:
            break
        if (
            length >= _MIN_MANUFACTURER_AD_LEN
            and raw[pos + 1] == _AD_TYPE_MANUFACTURER_DATA
            and int.from_bytes(raw[pos + 2 : pos + 4], "little") == COLMO_COMPANY_ID
        ):
            payload = bytes(raw[pos + 4 : end])
            if payload not in payloads:
                payloads.append(payload)
        pos = end
    return payloads


def match_advertisement(info: Any) -> Appliance | None:
    """Match a Bluetooth service info against supported exact-model COLMO frames."""
    for payload in _manufacturer_payloads(info):
        model = DEVICES.get(payload[1:9].decode("ascii", errors="ignore"))
        if model and payload[9:11] == f"{model.kind:02X}".encode():
            return model
    return None


def parse(device: Any, raw: bytes) -> Any:
    """Validate an exact-model status frame before exposing fields."""
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
    if device == PURIFIER:
        return purifier.parse_body(raw[10:-1])
    if device == HEATER and raw[10:12] == b"\x01\x01" and len(raw) >= 40:
        return _parse_heater(raw)
    if device == HOOD and raw[8] == 2:
        pos = 11
        while pos + 2 <= len(raw) - 1:
            kind, length = raw[pos : pos + 2]
            if pos + 2 + length > len(raw) - 1:
                break
            pkg = raw[pos + 2 : pos + 2 + length]
            if kind == 1 and len(pkg) >= 7 and 255 not in {pkg[1], pkg[2], pkg[6]}:
                return {
                    "power": pkg[1] not in {0, 1, 5, 7},
                    "gear": pkg[2],
                    "light": bool(pkg[6]),
                }
            pos += 2 + length
    raise ValueError("Unsupported status format")


def idle(device: Any, state: Any) -> bool:
    """Check reported state before changing an isolated preference."""
    if device == DISH:
        return state["status"] == 0 and not state["operator"]
    if device == HOOD:
        return not state["power"] and state["gear"] == 0
    return not state["power"] and not state["burning"]


def setting(device: Any, key: str, value: Any) -> bytes:
    """Encode one supported isolated preference."""
    if device == DISH:
        return dishwasher.setting_frame(key, value)
    if type(value) is not bool:
        raise ValueError("Invalid switch value")
    if device == HOOD and key == "light":
        fields = bytearray.fromhex("12b6000000000000021101020200ffffff")
        fields[13] = int(value)
    elif device == HEATER and key == "beep":
        fields = bytearray.fromhex(
            "1ee3000000000000021415000000000000000000000000000000000000",
        )
        fields[11] = fields[28] = int(value)
    else:
        raise ValueError("Unsupported appliance setting")
    return b"\xaa" + signed(fields)
