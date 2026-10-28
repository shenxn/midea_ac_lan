"""Entity definitions limited to verified local model adapters."""

from typing import Any

from homeassistant.const import Platform


def register_local_entities(devices: dict[int, Any]) -> None:
    """Register exact-model metadata without mutating shared exclusion lists."""
    soft = devices[237]["entities"]
    names = {
        "water_consumption_today": ("今日用水量", "L"),
        "pre_regeneration_days": ("预再生天数", "d"),
        "days_since_last_regeneration": ("距上次再生天数", "d"),
        "days_since_last_two_regeneration": ("距上上次再生天数", "d"),
        "regeneration_stages": ("再生总阶段数", None),
        "regeneration_current_stages": ("再生当前阶段", None),
        "regeneration_current_stages_name": ("再生阶段代码", None),
        "left_salt": ("剩余盐量", "%"),
        "soft_available_big": ("可用软水量", "L"),
        "water_consumption_big": ("累计用水量", "L"),
        "water_consumption_average": ("日均用水量", "L"),
        "velocity": ("流速", "L/min"),
        "use_days": ("使用天数", "d"),
        "regeneration_count": ("再生次数", None),
        "regeneration_left_seconds": ("再生剩余时间", "s"),
        "water_hardness": ("进水硬度", "ppm"),
        "flushing_days": ("设定再生周期", "d"),
        "timing_regeneration_hour": ("设定再生小时", None),
        "timing_regeneration_min": ("设定再生分钟", None),
        "salt_alarm_threshold": ("低盐报警阈值", "%"),
        "leak_water_protection_value": ("漏水保护阈值", "L"),
        "micro_leak_protection_value": ("微漏保护阈值", "min"),
        "error": ("故障代码", None),
    }
    binary = {
        "holiday_mode": "假日模式",
        "leak_water": "漏水报警",
        "micro_leak": "微漏报警",
        "low_salt": "低盐报警",
        "no_salt": "缺盐报警",
        "rsj_stand_by": "待机",
        "regeneration": "正在再生",
        "leak_water_protection": "漏水保护已启用",
        "micro_leak_protection": "微漏保护已启用",
        "salt_level_sensor_error": "盐位传感器故障",
        "chlorine_sterilization_error": "氯杀菌故障",
        "flowmeter_error": "流量计故障",
        "rtc_error": "时钟故障",
    }
    for key, (name, unit) in names.items():
        soft["f08_" + key] = {
            "type": Platform.SENSOR,
            "name": name,
            "unit": unit,
            "models": ["6360000F"],
            "subtypes": [845],
            "required_attribute": "f08_" + key,
        }
    for key, name in binary.items():
        soft["f08_" + key] = {
            "type": Platform.BINARY_SENSOR,
            "name": name,
            "models": ["6360000F"],
            "subtypes": [845],
            "required_attribute": "f08_" + key,
        }
    for key, name in {"soften": "软化功能", "cl_sterilization": "氯杀菌"}.items():
        soft["f08_" + key] = {
            "type": Platform.SWITCH,
            "name": name,
            "models": ["6360000F"],
            "subtypes": [845],
            "required_attribute": "f08_" + key,
        }
    for key, limit in [("water_hardness", 999), ("flushing_days", 30)]:
        soft["f08_" + key].update(
            {
                "type": Platform.NUMBER,
                "min": 30 if key == "water_hardness" else 0,
                "max": limit,
                "step": 1,
            },
        )
    soft["f08_regeneration_time"] = {
        "type": Platform.TIME,
        "name": "再生时刻",
        "models": ["6360000F"],
        "subtypes": [845],
        "required_attribute": "f08_timing_regeneration_hour",
        "hour_attr": "f08_timing_regeneration_hour",
        "min_attr": "f08_timing_regeneration_min",
        "combined_attribute": "f08_regeneration_time",
        "state_attribute": "f08_timing_regeneration_hour",
    }
    for key, name, unit, values in (
        ("leak_protection_setting", "大量漏水保护设置", "L", range(200, 951, 50)),
        ("micro_leak_setting", "微漏提醒设置", "min", range(10, 91, 5)),
    ):
        soft["f08_" + key] = {
            "type": Platform.SELECT,
            "name": name,
            "models": ["6360000F"],
            "subtypes": [845],
            "required_attribute": "f08_" + key,
            "options": {0: "关闭", **{v: f"{v} {unit}" for v in values}},
        }
    ac = devices[172]["entities"]
    for key, name, kind in [
        ("ventilation_power", "新风总开关", Platform.SWITCH),
        ("fresh_air_remove_odor", "新风除菌", Platform.SWITCH),
        ("ventilation_mode", "新风运行模式代码", Platform.SENSOR),
        ("fresh_filter_time", "新风滤网已用寿命", Platform.SENSOR),
    ]:
        ac[key] = {
            "type": kind,
            "name": name,
            "models": ["24297131"],
            "subtypes": [1],
            "required_attribute": key,
        }

    ac["fresh_filter_time"]["unit"] = "%"
    ac["fresh_filter_remaining"] = {
        "type": Platform.SENSOR,
        "name": "新风滤网剩余寿命",
        "unit": "%",
        "models": ["24297131"],
        "subtypes": [1],
        "required_attribute": "fresh_filter_remaining",
        "default": True,
    }
    ac["ventilation_preset"] = {
        "type": Platform.SELECT,
        "name": "新风运行模式",
        "models": ["24297131"],
        "subtypes": [1],
        "required_attribute": "ventilation_preset",
        "default": True,
        "options": {1: "热交换", 7: "强劲", 8: "度假", 4: "自动"},
    }

    pipe = devices[237]["entities"]
    common = {"models": ["6320088A"], "subtypes": [1046], "default": True}
    for slot in (1, 2, 3):
        key = f"a1_custom_temperature_{slot}"
        pipe[key] = {
            **common,
            "type": Platform.NUMBER,
            "name": f"水温第{slot}档",
            "unit": "°C",
            "min": 35,
            "max": 45 if slot == 1 else 99,
            "step": 1,
            "required_attribute": key,
        }
    for slot, volumes in {
        1: (50, 100, 150),
        2: (150, 200, 250, 300, 400, 500),
        3: (300, 400, 500, 600, 700),
    }.items():
        key = f"a1_quantify_{slot}"
        pipe[key] = {
            **common,
            "type": Platform.SELECT,
            "name": f"水量第{slot}档",
            "options": {v: f"{v} mL" for v in volumes},
            "required_attribute": key,
        }
    for key, name, options in [
        (
            "a1_cur_quantify",
            "当前定量档位",
            {0: "关定量", 1: "第一档", 2: "第二档", 3: "第三档"},
        ),
        (
            "a1_screenout_time",
            "息屏时间",
            {v: f"{v} 秒" for v in (10, 30, 60, 120, 180, 300)},
        ),
    ]:
        pipe[key] = {
            **common,
            "type": Platform.SELECT,
            "name": name,
            "options": options,
            "required_attribute": key,
        }
    pipe["a1_human_sensing_switch"] = {
        **common,
        "type": Platform.SWITCH,
        "name": "感应亮屏",
        "required_attribute": "a1_human_sensing_switch",
    }

    # These generic entities do not describe the verified appliance models.
    for dtype, model, subtype, keys in [
        (172, "24297131", 1, ["climate"]),
        (
            237,
            "6360000F",
            845,
            ["water_consumption", "water_kind", "no_obsolete_water_mode"],
        ),
        (237, "6320088A", 1046, ["heat_start", "cur_quantify"]),
    ]:
        for key in keys:
            config = devices[dtype]["entities"].get(key)
            if config is not None:
                excluded = list(config.get("excluded_devices", []))
                config["excluded_devices"] = excluded
                if (model, subtype) not in excluded:
                    excluded.append((model, subtype))

    for key, name, platform in [
        ("prepare_food", "备菜", Platform.SWITCH),
        ("quick_fry", "爆炒", Platform.SWITCH),
        ("food_angle", "备菜爆炒风向值", Platform.SENSOR),
    ]:
        devices[172]["entities"]["kitchen_" + key] = {
            "type": platform,
            "name": name,
            "models": ["22397091"],
            "subtypes": [1],
            "required_attribute": "kitchen_" + key,
        }

    for key, name, platform, unit in [
        ("error", "故障代码", Platform.SENSOR, None),
        ("lack_water", "缺水状态", Platform.BINARY_SENSOR, None),
        ("heat_status", "加热状态", Platform.BINARY_SENSOR, None),
        ("leaking_protect_status", "漏水保护状态", Platform.BINARY_SENSOR, None),
        ("effluent_ml", "出水量读数", Platform.SENSOR, "mL"),
    ]:
        pipe["a1_" + key] = {
            "type": platform,
            "name": name,
            "unit": unit,
            "models": ["6320088A"],
            "subtypes": [1046],
            "required_attribute": "a1_" + key,
        }

    for key, name, platform in (
        ("power", "温控", Platform.CLIMATE),
        ("ptc", "电辅热", Platform.SWITCH),
        ("power_save", "节能", Platform.SWITCH),
        ("go_out", "外出", Platform.SWITCH),
        ("in_temperature", "进水温度", Platform.SENSOR),
        ("out_temperature", "出水温度", Platform.SENSOR),
    ):
        config = {
            "type": platform,
            "name": name,
            "models": ["22397091"],
            "subtypes": [1],
            "device_group": "hydronic",
            "required_attribute": "hydronic_" + key,
            "available_attribute": "hydronic_has",
            "available_value_attribute": "hydronic_" + key,
        }
        if platform == Platform.SENSOR:
            config.update(
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        devices[172]["entities"]["hydronic_" + key] = config
