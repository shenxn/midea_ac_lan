"""Model-scoped entities for the 632009CN purifier."""

from typing import Any

from homeassistant.const import Platform


def register_purifier_entities(soft: dict[str, Any]) -> None:
    """Add only controls verified for the exact 632009CN model."""
    purifier = {"models": ["632009CN"], "subtypes": [845], "default": True}
    for slot, low, high in ((21, 200, 1000), (22, 200, 3000), (23, 1000, 5000)):
        soft[f"purifier_quantify_{slot}"] = {
            **purifier,
            "type": Platform.NUMBER,
            "name": f"定量{slot - 20}",
            "min": low,
            "max": high,
            "step": 10,
            "unit": "mL",
        }
    soft["purifier_cur_quantify"] = {
        **purifier,
        "type": Platform.SELECT,
        "name": "定量档位",
        "options": {0: "关定量", 21: "定量1", 22: "定量2", 23: "定量3"},
    }
    for key, name in (
        ("lock", "童锁"),
        ("sleep", "屏幕关闭"),
        ("no_obsolete_water", "零陈水"),
        ("wash", "滤芯冲洗"),
    ):
        soft["purifier_" + key] = {**purifier, "type": Platform.SWITCH, "name": name}
    for key, name, unit in (
        ("life_1", "RO滤芯寿命", "%"),
        ("life_2", "PCB滤芯寿命", "%"),
        ("error", "故障代码", None),
    ):
        soft["purifier_" + key] = {
            **purifier,
            "type": Platform.SENSOR,
            "name": name,
            "unit": unit,
        }
    for key, name in (
        ("filter", "滤芯报警"),
        ("standby_status", "待机状态"),
        ("out_water", "正在出水"),
        ("lack_water", "缺水"),
        ("backflow", "回流状态"),
    ):
        soft["purifier_" + key] = {
            **purifier,
            "type": Platform.BINARY_SENSOR,
            "name": name,
        }
    # Generic controls must not advertise operations the exact adapter rejects.
    for key in (
        "cur_quantify",
        "wash",
        "heat",
        "antifreeze",
        "water_kind",
        "heat_start",
        "no_obsolete_water_mode",
    ):
        config = soft.get(key)
        if config is not None:
            excluded = list(config.get("excluded_devices", []))
            if ("632009CN", 845) not in excluded:
                excluded.append(("632009CN", 845))
            config["excluded_devices"] = excluded
