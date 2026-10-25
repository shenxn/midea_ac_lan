"""Native wire codecs for the three exact-model adapters.

Only the fields exposed by local_models are implemented. Transport encryption
remains in midea-lan. Unknown records are skipped; malformed frames are rejected
atomically, without inventing missing state or enabling unverified controls.
"""

# Numeric offsets, masks and identifiers are the wire specification.
# ruff: file-ignore[magic-value-comparison, docstring-missing-returns, docstring-missing-exception, undocumented-public-init]

from typing import Any


def crc8(data: bytes | bytearray) -> int:
    """Compute the reflected Dallas/Maxim CRC used by the nested AC envelope."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8C if crc & 1 else 0)
    return crc


def frame(device_type: int, message_type: int, body: bytes) -> bytes:
    """Wrap a body in the appliance UART header and additive checksum."""
    header = bytes(
        (
            0xAA,
            len(body) + 10,
            device_type,
            0,
            0,
            0,
            0,
            0,
            2 if device_type == 0xAC else 0,
            message_type,
        ),
    )
    packet = header + body
    return packet + bytes((-sum(packet[1:]) & 0xFF,))


def ac_envelope(command: int, payload: bytes, address: int = 0xFF) -> bytes:
    """Build the nested JZ envelope including its CRC and additive checksum."""
    packet = bytes((0xAA, len(payload) + 8, 0, address, 0xFF, command)) + payload
    packet += bytes((crc8(packet),))
    return packet + bytes((-sum(packet) & 0xFF,))


# Record -> (field, byte offset in value, width). All integer values are LE.
ED_FIELDS = {
    0x001: (("error", 0, 1),),
    0x011: (("water_consumption", 0, 4),),
    0x020: (("water_kind", 0, 1),),
    0x021: (
        ("custom_temperature_1", 0, 1),
        ("custom_temperature_2", 1, 1),
        ("custom_temperature_3", 2, 1),
    ),
    0x023: (
        ("quantify_1", 0, 1),
        ("quantify_2", 1, 1),
        ("quantify_3", 2, 1),
        ("cur_quantify", 5, 1),
    ),
    0x036: (("screenout_time", 0, 2),),
    0x207: (("input_temperature_Sensing", 0, 1),),
    0x901: (("velocity", 0, 1),),
    0x902: (("soft_available_big", 0, 4),),
    0x903: (("water_consumption_big", 0, 4),),
    0x904: (("water_consumption_today", 0, 2),),
    0x90B: (("pre_regeneration_days", 0, 1),),
    0x913: (
        ("days_since_last_regeneration", 2, 1),
        ("days_since_last_two_regeneration", 3, 1),
    ),
    0x918: (
        ("regeneration_stages", 0, 1),
        ("regeneration_current_stages", 1, 1),
        ("regeneration_current_stages_name", 2, 1),
    ),
    0x905: (("water_consumption_average", 0, 2),),
    0x906: (("left_salt", 0, 1),),
    0x907: (("salt_alarm_threshold", 0, 1),),
    0x909: (
        ("leak_water_protection_value", 0, 1),
        ("micro_leak_protection_value", 1, 1),
    ),
    0x90A: (("water_hardness", 0, 2),),
    0x90C: (
        ("flushing_days", 0, 1),
        ("timing_regeneration_hour", 2, 1),
        ("timing_regeneration_min", 3, 1),
    ),
    0x90D: (("regeneration_left_seconds", 0, 2),),
    0x910: (("use_days", 0, 2), ("regeneration_count", 2, 2)),
}
ED_FLAGS = {
    0x000: (
        ("standby_status", 0, 3),
        ("lock", 2, 0),
        ("out_water", 2, 1),
        ("out_hot_water", 2, 6),
        ("power", 3, 0),
        ("sleep", 3, 1),
    ),
    0x048: (("human_sensing_switch", 0, 0),),
    0x90F: (
        ("leak_water", 0, 0),
        ("micro_leak", 0, 1),
        ("low_salt", 0, 2),
        ("no_salt", 0, 3),
        ("salt_level_sensor_error", 2, 0),
        ("chlorine_sterilization_error", 2, 1),
        ("flowmeter_error", 2, 2),
        ("rtc_error", 2, 3),
    ),
    0x911: (
        ("rsj_stand_by", 0, 0),
        ("regeneration", 0, 1),
        ("holiday_mode", 0, 2),
        ("leak_water_protection", 0, 3),
        ("micro_leak_protection", 0, 4),
        ("cl_sterilization", 0, 5),
    ),
    0x914: (("soften", 0, 0), ("water_way", 0, 1)),
}
PIPE_FIELDS = {0x037: (("effluent_ml", 0, 2),)}
PIPE_FLAGS = {
    0x000: (("heat_status", 1, 5), ("lack_water", 2, 2)),
    0x03C: (("leaking_protect_status", 1, 5),),
}
FRESH_FLAGS = (
    "new_wind_machine",
    "fresh_air_remove_odor",
    "new_wind_machine_intake_switch",
    "new_wind_machine_exhaust_switch",
)


def _decode_ed(body: bytes, *, pipe: bool = False) -> dict[str, Any]:
    """Decode FF/01 status records with 12-bit IDs and a four-bit length."""
    if len(body) < 3 or body[:2] != b"\xff\x01":
        return {}
    result: dict[str, Any] = {}
    offset = 3  # FF, protocol version, category
    while offset < len(body):
        if offset + 2 > len(body):
            raise ValueError("Truncated ED record header")
        identifier = body[offset] | ((body[offset + 1] & 15) << 8)
        size = body[offset + 1] >> 4
        offset += 2
        value = body[offset : offset + size]
        if len(value) != size:
            raise ValueError("Truncated ED record value")
        fields = ED_FIELDS.get(identifier, ()) + (
            PIPE_FIELDS.get(identifier, ()) if pipe else ()
        )
        for name, start, width in fields:
            if start + width > size:
                raise ValueError("Short ED numeric record")
            result[name] = int.from_bytes(
                value[start : start + width],
                "little",
                signed=name == "input_temperature_Sensing",
            )
        flags = ED_FLAGS.get(identifier, ()) + (
            PIPE_FLAGS.get(identifier, ()) if pipe else ()
        )
        for name, start, bit in flags:
            if start >= size:
                raise ValueError("Short ED flag record")
            enabled = bool(value[start] & (1 << bit))
            result[name] = (
                int(enabled)
                if name == "standby_status"
                else ("on" if enabled else "off")
            )
        offset += size
    return result


def _decode_ac(body: bytes) -> dict[str, Any]:
    """Decode only fields present in general, running or dedicated C003 status."""
    if (
        len(body) < 8
        or body[0] not in {0xAA, 0xBB}
        or body[1] != len(body)
        or sum(body) & 0xFF
        or crc8(body[:-2]) != body[-2]
    ):
        raise ValueError("Invalid JZ envelope")
    command, data = body[5], body[6:-2]
    result: dict[str, Any] = {}
    if command in {0x11, 0x20, 0xF1}:
        # General status has a mandatory prefix and optional firmware extensions.
        if len(data) < 17:
            raise ValueError("Short AC general status")
        result.update(
            new_wind_machine="on" if data[4] & 8 else "off",
            fresh_air_mode=data[15],
        )
        if len(data) > 36:
            result["fresh_air_remove_odor"] = (data[36] >> 7) & 1
        for index, name in (
            (61, "new_wind_machine_type"),
            (62, "fresh_air_intake_fan_speed"),
            (63, "fresh_air_exhaust_fan_speed"),
        ):
            if len(data) > index:
                result[name] = data[index] if index == 61 else data[index] & 0x7F
        if len(data) > 55:
            result["new_wind_machine_intake_switch"] = (data[55] >> 5) & 1
            result["new_wind_machine_exhaust_switch"] = (data[55] >> 6) & 1
    elif command == 0x10:
        if len(data) < 9:
            raise ValueError("Short AC running status")
        result["indoor_temperature"] = (
            int.from_bytes(data[7:9], "little", signed=True) / 100
        )
        if len(data) > 58:
            result["special_machine_type"] = (data[58] >> 4) & 7
        if len(data) > 62:
            result["new_wind_outdoor_temperature"] = (
                int.from_bytes(data[61:63], "little", signed=True) / 100
            )
        if len(data) > 63:
            result["fresh_filter_time"] = data[63]
    elif command == 0xC0 and len(data) >= 4 and data[1:4] == b"\x01\xc0\x03":
        if len(data) < 16:
            raise ValueError("Short C003 status")
        result["new_wind_machine_type"] = data[6]
        for bit, name in enumerate(FRESH_FLAGS):
            result[name] = (data[9] >> bit) & 1
        result["new_wind_machine"] = "on" if data[9] & 1 else "off"
        result["fresh_air_mode"] = data[10] & 0x1F
        result["fresh_air_intake_fan_speed"] = data[11] & 0x7F
        result["fresh_air_exhaust_fan_speed"] = data[12] & 0x7F
    return result


class ModelCodec:
    """Encode verified controls and decode status without any vendor runtime."""

    def __init__(self, device_type: int, subtype: int) -> None:
        if (device_type, subtype) not in {(0xED, 845), (0xED, 1046), (0xAC, 1)}:
            raise ValueError("Unsupported local protocol")
        self.device_type = device_type
        self.subtype = subtype
        self._pack_id = 0
        self._address = 0

    def encode(
        self,
        kind: str,
        value: dict[str, Any],
        status: dict[str, Any] | None = None,
    ) -> str:
        """Encode one query or the allowlisted command supplied by the adapter."""
        if kind not in {"query", "control"}:
            raise ValueError("Unsupported message kind")
        if self.device_type == 0xED:
            body = b"\xff\x01" if kind == "query" else self._ed_control(value)
        else:
            body = self._ac_message(kind, value, status or {})
        return frame(self.device_type, 3 if kind == "query" else 2, body).hex()

    def _ed_control(self, control: dict[str, Any]) -> bytes:
        if self.subtype == 845:
            compound = self._soft_compound_control(control)
            if compound is not None:
                return b"\x15\x01\x01" + compound
        if len(control) != 1:
            raise ValueError("Exactly one ED setting is required")
        name, value = next(iter(control.items()))
        switches = (
            {"soften": 0x0906, "cl_sterilization": 0x090C}
            if self.subtype == 845
            else {"power": 0x0100, "lock": 0x0201, "human_sensing_switch": 0x0118}
        )
        if name in switches and value in {"on", "off"}:
            tag, payload = switches[name], bytes((int(value == "on"), 0, 0))
        elif self.subtype == 845 and name in {"water_hardness", "flushing_days"}:
            tag = 0x0900 if name == "water_hardness" else 0x0901
            payload = b"\x00" + int(value).to_bytes(2, "little")
        elif self.subtype == 1046 and name in {
            "custom_temperature_1",
            "custom_temperature_2",
            "custom_temperature_3",
        }:
            tag, payload = 0x0401, bytes((int(value), 9 + int(name[-1]), 0))
        elif self.subtype == 1046 and name in {
            "quantify_1",
            "quantify_2",
            "quantify_3",
        }:
            tag, payload = (
                0x0202,
                bytes((int(name[-1]),)) + int(value).to_bytes(2, "little"),
            )
        elif self.subtype == 1046 and name == "screenout_time":
            tag, payload = 0x0108, b"\x00" + int(value).to_bytes(2, "little")
        elif self.subtype == 1046 and name == "cur_quantify":
            tag, payload = 0x020D, bytes((int(value), 0, 0))
        else:
            raise ValueError("Unsupported ED command")
        return b"\x15\x01\x01" + tag.to_bytes(2, "little") + payload

    @staticmethod
    def _soft_compound_control(control: dict[str, Any]) -> bytes | None:
        """Encode one atomic setting, never split coupled values into commands."""
        if set(control) == {"timing_regeneration_hour", "timing_regeneration_min"}:
            hour, minute = (
                control["timing_regeneration_hour"],
                control["timing_regeneration_min"],
            )
            if (
                type(hour) is not int
                or type(minute) is not int
                or not (0 <= hour <= 23 and 0 <= minute <= 59)
            ):
                raise ValueError("Invalid regeneration time")
            return bytes((2, 9, 0, hour, minute))
        for name, tag, values in (
            ("leak_water_protection", 9, range(20, 96, 5)),
            ("micro_leak_protection", 10, range(10, 91, 5)),
        ):
            if set(control) == {name, name + "_value"}:
                enabled, value = control[name], control[name + "_value"]
                if enabled not in {"on", "off"} or type(value) is not int:
                    raise ValueError("Invalid protection setting")
                if (enabled == "off" and value != 0) or (
                    enabled == "on" and value not in values
                ):
                    raise ValueError("Invalid protection range")
                return bytes((tag, 9, int(enabled == "on"), value, 0))
        return None

    def _ac_message(
        self,
        kind: str,
        value: dict[str, Any],
        status: dict[str, Any],
    ) -> bytes:
        if kind == "query":
            query = value.get("query_type")
            if query is None:
                return ac_envelope(0x11, b"")
            if query == "run_status":
                return ac_envelope(0x10, b"\x01")
            if query == "c003_query":
                return ac_envelope(
                    0xC0,
                    bytes((self._pack_id, 1, 0xC0, 3)),
                    self._address,
                )
            raise ValueError("Unsupported AC query")
        fields = set(FRESH_FLAGS) | {
            "fresh_air_mode",
            "fresh_air_intake_fan_speed",
            "fresh_air_exhaust_fan_speed",
        }
        allowed = (
            fields | {name + "_enable" for name in fields} | {"new_wind_single_control"}
        )
        if (
            value.get("new_wind_single_control") != 1
            or not fields.intersection(value)
            or set(value) - allowed
        ):
            raise ValueError("Unsupported dedicated ventilation command")
        self._pack_id = int(status.get("pack_id", 0))
        self._address = int(status.get("machine_address", 0))
        data = bytearray(31)
        data[:3] = bytes((self._pack_id, 1, 1))
        data[11:15] = b"\x01\xc0\x03\x13"
        data[15] = int(status.get("new_wind_machine_type", 0))
        for bit, name in enumerate(FRESH_FLAGS):
            if name in value:
                data[17] |= 1 << bit
                if value[name] in {1, "1", "on"}:
                    data[18] |= 1 << bit
        for name, offset in (
            ("fresh_air_mode", 19),
            ("fresh_air_intake_fan_speed", 20),
            ("fresh_air_exhaust_fan_speed", 21),
        ):
            if name in value:
                data[offset] = int(value[name]) | 0x80
        data[30] = -sum(data[12:30]) & 0xFF
        return ac_envelope(0xC0, bytes(data), self._address)

    def decode(self, msg: bytes) -> dict[str, Any]:
        """Return a validated status update, or no update for malformed input."""
        if (
            len(msg) < 12
            or msg[0] != 0xAA
            or msg[1] != len(msg) - 1
            or msg[2] != self.device_type
            or sum(msg[1:]) & 0xFF
        ):
            return {}
        if msg[9] not in {2, 3, 4, 5}:
            return {}
        try:
            if self.device_type == 0xED:
                return (
                    _decode_ed(msg[10:-1], pipe=self.subtype == 1046)
                    if msg[9] in {3, 4}
                    else {}
                )
            result = _decode_ac(msg[10:-1])
            self._pack_id = self._address = 0
        except ValueError:
            return {}
        else:
            return result
