"""Independent codec parity and model isolation for the J37 hood."""

# ruff: file-ignore[pytest-raises-too-broad]
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from midealan.const import ProtocolVersion

from custom_components.midea_ac_lan.hood_model import Hood730007C9, device_selector
from custom_components.midea_ac_lan.hood_protocol import hood_control, hood_status

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/hood_730007c9.json").read_text(),
)


@pytest.mark.parametrize("case", VECTORS["encode"])
def test_encoding(case: dict) -> None:
    """Match independent vendor output without bundling vendor code."""
    assert hood_control(case["attribute"], case["value"]).hex() == case["hex"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_decode_and_corruption(case: dict) -> None:
    """Missing or corrupt packets must not invent confirmed device state."""
    msg = bytes.fromhex(case["hex"])
    expected = {
        k: v == "on" if isinstance(v, str) else v for k, v in case["expected"].items()
    }
    assert hood_status(msg) == expected
    for n in range(len(msg)):
        assert hood_status(msg[:n]) == {}
        bad = bytearray(msg)
        bad[n] ^= 1
        assert hood_status(bytes(bad)) == {}


def test_scope_and_confirmed_state() -> None:
    """Unknown models use upstream; writes require readback and are not optimistic."""
    args = {
        "name": "test",
        "device_id": 123,
        "device_type": 182,
        "ip_address": "127.0.0.1",
        "port": 6444,
        "token": "",
        "key": "",
        "device_protocol": ProtocolVersion.V3,
        "model": "730007C9",
        "subtype": 0,
        "customize": "",
    }
    d = device_selector(**args)
    assert isinstance(d, Hood730007C9)
    assert d.preset_modes == ["off", "level_1", "level_2", "level_3", "level_4"]
    d.build_send = Mock()  # type: ignore[method-assign]
    with pytest.raises(ValueError):
        d.set_attribute("hood_gesture", False)
    d.process_message(bytes.fromhex(VECTORS["decode"][0]["hex"]))
    assert d.attributes["hood_gesture"] is True
    d.set_attribute("hood_gesture", False)
    assert d.build_send.call_count == 2
    assert d.attributes["hood_gesture"] is True
    args["model"] = "unknown"
    assert not isinstance(device_selector(**args), Hood730007C9)


@pytest.mark.parametrize(
    ("name", "value"),
    [("wind_pressure", True), ("stove", True), ("gesture", "off")],
)
def test_invalid_controls(name: str, value: object) -> None:
    """Reject unsupported writes instead of silently accepting them."""
    with pytest.raises(ValueError):
        hood_control(name, value)
