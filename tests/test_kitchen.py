"""Kitchen extensions checked against independent model-specific vectors."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from midea_ac_lan.kitchen_protocol import kitchen_control, kitchen_query, kitchen_status
from midea_ac_lan.local_models import Kitchen22397091
from midealan.const import ProtocolVersion
from midealan.devices.ac.message import (
    SubProtocolQuery10,
    SubProtocolQuery11,
    SubProtocolQuery30,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures/kitchen.json").read_text())


@pytest.mark.parametrize("case", VECTORS["encode"])
def test_vendor_encode(case: dict[str, Any]) -> None:
    """Single-function masks match the model's independent codec."""
    assert kitchen_control(case["name"], case["enabled"]).hex() == case["hex"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_vendor_decode(case: dict[str, Any]) -> None:
    """Capability masks control exposure and corrupt packets cannot change state."""
    packet = bytes.fromhex(case["hex"])
    assert kitchen_status(packet) == case["expected"]
    for length in range(len(packet)):
        assert kitchen_status(packet[:length]) == {}
    for index in range(len(packet)):
        bad = bytearray(packet)
        bad[index] ^= 1
        assert kitchen_status(bytes(bad)) == {}


def test_query_vector() -> None:
    """Query matches the vendor's read-only C002 request."""
    assert kitchen_query().hex() == "aa16ac00000000000203aa0c0000ffc00001c002418739"


def test_adapter_requires_live_capability_and_does_not_guess_state() -> None:
    """Do not send before capability evidence or optimistically report success."""
    device: Any = Kitchen22397091(
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model="22397091",
        subtype=1,
        customize="",
    )
    # A new connection must not depend on a fallback suppressed by C002 success.
    assert device.build_init_query() == []
    queries = device.build_query()
    assert isinstance(queries[0], SubProtocolQuery10)
    assert isinstance(queries[1], SubProtocolQuery11)
    assert isinstance(queries[2], SubProtocolQuery30)
    device.build_send = Mock()
    with pytest.raises(ValueError, match="not confirmed"):
        device.set_attribute("kitchen_prepare_food", True)
    case = next(
        x
        for x in VECTORS["decode"]
        if x["expected"].get("kitchen_prepare_food") is False
    )
    assert device.process_message(bytes.fromhex(case["hex"])) == case["expected"]
    device.set_attribute("kitchen_prepare_food", True)
    assert device.get_attribute("kitchen_prepare_food") is False
    device.build_send.assert_called_once()
    with pytest.raises(ValueError, match="Unsupported kitchen"):
        device.set_attribute("kitchen_prepare_food", "on")
