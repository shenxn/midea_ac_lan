"""Model-scoped LAN controls for the 730007C9 hood."""

from typing import Any

from homeassistant.const import Platform


def register_hood_entities(entities: dict[str, Any]) -> None:
    """Register only documented controls and read-only pressure diagnostics."""
    common = {"models": ["730007C9"], "subtypes": [0], "default": True}
    for key, name in (
        ("wisdom_wind", "智能换气"),
        ("gesture", "挥手感应"),
        ("linkage", "烟灶联动"),
    ):
        entities["hood_" + key] = {**common, "type": Platform.SWITCH, "name": name}
    for key, name in (("error_code", "故障代码"), ("wind_pressure", "风压读数")):
        entities["hood_" + key] = {
            **common,
            "type": Platform.SENSOR,
            "name": name,
            "default": key != "wind_pressure",
        }
