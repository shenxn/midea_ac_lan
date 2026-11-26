"""HA metadata for the exact GR-A540XFS local protocol profile."""

from typing import Any

from homeassistant.const import Platform


def register_fridge_entities(entities: dict[str, Any]) -> None:
    """Expose confirmed local fields and exclude incompatible generic sensors."""
    profile = {"models": ["00000003"], "subtypes": [38], "default": True}
    for key, config in entities.items():
        if key not in {"refrigerator_door", "freezer_door"}:
            config["excluded_devices"] = [
                *config.get("excluded_devices", []),
                ("00000003", 38),
            ]
    selects = {
        "chilled_const": (
            "冰鲜室模式",
            {
                "normal": "普通冰鲜",
                "power_low_temp": "冰晶",
                "deli_chilled": "熟食冰鲜",
            },
        ),
        "chilled_temp": (
            "冰鲜室温度模式",
            {"not_set": "未设置", "chilled": "冰鲜", "thawing": "解冻"},
        ),
        "power_saving_mode": (
            "节能模式",
            {
                "normal": "关闭",
                "power_saving_auto": "自动节能",
                "power_saving_auto_plus": "加强自动节能",
                "power_saving": "节能",
                "low_power_cooling": "低功耗制冷",
            },
        ),
        "cooling": (
            "上层冷冻模式",
            {
                "normal": "普通冷冻",
                "quick_freezing": "快速冷冻",
                "rough_heat_removal": "余热去除",
                "cool_cooking": "冷却料理",
                "timer": "定时冷却",
                "frozen_rice": "米饭冷冻",
            },
        ),
        "ice_making": (
            "制冰模式",
            {"normal": "普通制冰", "quick": "快速制冰", "off": "停止制冰"},
        ),
        "lighting": ("照明亮度", {"dim": "暗", "medium": "中", "standard": "标准"}),
    }
    for key, (name, options) in selects.items():
        entities[key] = {
            **profile,
            "type": Platform.SELECT,
            "name": name,
            "options": options,
            "required_attribute": key,
        }
    for key, name in {
        "vegetable_sterilization": "蔬菜室UV除菌",
        "night_mode": "夜间照明模式",
        "auto_door_left": "左侧自动门",
        "auto_door_right": "右侧自动门",
        "light_blue_led": "蓝色指示灯",
    }.items():
        entities[key] = {
            **profile,
            "type": Platform.SWITCH,
            "name": name,
            "required_attribute": key,
        }
    for key, name in {
        "refrigerator_level": "冷藏强度档位",
        "freezer_level": "冷冻强度档位",
        "auto_door_left_strength": "左侧自动门力度",
        "auto_door_right_strength": "右侧自动门力度",
    }.items():
        entities[key] = {
            **profile,
            "type": Platform.NUMBER,
            "name": name,
            "min": 1,
            "max": 5,
            "step": 1,
            "required_attribute": key,
        }
    for key, name in {
        "night_start": "夜间模式开始",
        "night_end": "夜间模式结束",
    }.items():
        entities[key] = {
            **profile,
            "type": Platform.TIME,
            "name": name,
            "hour_attr": key + "_hour",
            "min_attr": key + "_min",
            "combined_attribute": key,
            "required_attribute": key + "_hour",
        }
    for area, name in {
        "ceiling": "顶部",
        "door": "门",
        "chilled": "冰鲜室",
        "vege": "蔬菜室",
    }.items():
        for mode, label in {"normal": "日间", "night": "夜间"}.items():
            key = f"{area}_light_{mode}"
            entities[key] = {
                **profile,
                "type": Platform.NUMBER,
                "name": f"{name}{label}亮度",
                "min": 0,
                "max": 100,
                "step": 1,
                "unit": "%",
                "required_attribute": key,
            }
    for key, name in {
        "ice_door": "制冰室门",
        "vegetable_door": "蔬菜室门",
        "upper_freezer_door": "上层冷冻室门",
        "ice_tray_cleaning": "制冰盘清洁中",
        "defrost_moisture": "除霜保湿",
        "defrost_precool": "除霜预冷",
        "defrost_active": "除霜中",
        "weekly_reminder": "每周语音提醒",
    }.items():
        entities[key] = {
            **profile,
            "type": Platform.BINARY_SENSOR,
            "name": name,
            "required_attribute": key,
        }
    for key, name, unit, device_class in (
        ("ambient_temperature", "冰箱周围温度", "°C", "temperature"),
        ("error_code", "故障代码", None, None),
        ("cooling_timer", "冷却计时器", "min", "duration"),
        ("ice_making_status", "制冰运行状态", None, None),
    ):
        entities[key] = {
            **profile,
            "type": Platform.SENSOR,
            "name": name,
            "unit": unit,
            "required_attribute": key,
        }
        if device_class:
            entities[key]["device_class"] = device_class
    # Rolling 24-hour energy is NOT a total_increasing Energy-dashboard meter.
