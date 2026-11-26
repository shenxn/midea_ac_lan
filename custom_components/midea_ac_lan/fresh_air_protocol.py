"""Read-only 0x10 engineering telemetry for dedicated fresh-air model 24297131."""

# Offsets and masks describe this model's nested 0x10 running-status payload.
# ruff: file-ignore[magic-value-comparison, docstring-missing-returns, docstring-missing-exception, too-many-boolean-expressions]

from typing import Any

from .local_protocol import crc8

FRESH_AIR_ENGINEERING_KEYS = (
    "fresh_air_intake_actual_level",
    "fresh_air_exhaust_actual_level",
    "fresh_air_intake_fan_rpm_raw",
    "fresh_air_exhaust_fan_rpm_raw",
    "fresh_air_operating_mode",
    "fresh_air_fault",
    "fresh_air_protection",
)

# Only fault/protection bits corresponding to hardware present on CAX250GC1M.
FAULT_RULES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("风机失速", ((16, 0x10),)),
    ("风机故障", ((94, 0x01),)),
    ("温度传感器故障", ((16, 0x02), (21, 0x10), (94, 0x20))),
    ("主板参数故障", ((16, 0x40), (16, 0x80), (94, 0x40), (94, 0x80))),
    ("通信故障", ((15, 0x01), (15, 0x08), (22, 0x01), (22, 0x02))),
)

PROTECTION_RULES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("室外低温保护", ((18, 0x20), (94, 0x04))),
    ("防凝露保护", ((18, 0x10), (94, 0x02))),
    ("低温防凝露保护", ((21, 0x02),)),
    ("室外高温保护", ((18, 0x40), (94, 0x08))),
)


def _collect_labels(
    data: bytes,
    rules: tuple[tuple[str, tuple[tuple[int, int], ...]], ...],
) -> list[str]:
    """Return labels whose mapped byte/bit masks are set within the payload."""
    return [
        label
        for label, checks in rules
        if any(len(data) > offset and (data[offset] & mask) for offset, mask in checks)
    ]


def fresh_air_engineering_status(msg: bytes) -> dict[str, Any]:
    """Decode validated 0x10 running telemetry for CAX250GC1M without inventing state."""
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
        len(body) < 8
        or body[0] not in {0xAA, 0xBB}
        or body[1] != len(body)
        or sum(body) & 0xFF
        or crc8(body[:-2]) != body[-2]
    ):
        return {}
    if body[5] != 0x10:
        return {}
    data = body[6:-2]
    result: dict[str, Any] = {}
    if len(data) > 21:
        protections = _collect_labels(data, PROTECTION_RULES)
        if len(data) > 108 and data[106] == 2 and (data[108] & 0x04):
            protections.append("除霜")
        result["fresh_air_protection"] = "、".join(protections) if protections else "正常"
    if len(data) > 22:
        faults = _collect_labels(data, FAULT_RULES)
        result["fresh_air_fault"] = "、".join(faults) if faults else "正常"
    if len(data) > 55:
        result["fresh_air_exhaust_actual_level"] = data[52]
        result["fresh_air_exhaust_fan_rpm_raw"] = data[53]
        result["fresh_air_intake_actual_level"] = data[54]
        result["fresh_air_intake_fan_rpm_raw"] = data[55]
    if len(data) > 58:
        result["fresh_air_operating_mode"] = data[58] & 0x0F
    return result
