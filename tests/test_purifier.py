"""632009CN protocol parity, integrity, isolation and honest state regressions."""

# Test literals are independent protocol vectors and range boundaries.
# ruff: file-ignore[pytest-raises-too-broad, any-type]

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from midealan.const import ProtocolVersion

from custom_components.midea_ac_lan.local_entities import register_local_entities
from custom_components.midea_ac_lan.local_models import (
    Purifier632009CN,
    Softener845,
    device_selector,
)
from custom_components.midea_ac_lan.local_protocol import frame
from custom_components.midea_ac_lan.purifier_protocol import (
    FIELDS,
    FLAGS,
    purifier_control,
    purifier_query,
    purifier_status,
)

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/purifier_632009cn.json").read_text(),
)


def make(model: str = "632009CN") -> Any:
    """Create an offline device through the actual model dispatcher."""
    return device_selector(
        name="test",
        device_id=123,
        device_type=237,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model=model,
        subtype=845,
        customize="",
    )


@pytest.mark.parametrize("case", VECTORS["encode"])
def test_commands_match_vendor_oracle(case: dict) -> None:
    """Compare each command byte against independently generated vendor output."""
    assert purifier_control(case["attribute"], case["value"]).hex() == case["hex"]


def test_query_matches_vendor() -> None:
    """Query must match the official complete-status request."""
    assert purifier_query().hex() == VECTORS["query"]


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_decode_matches_vendor(case: dict) -> None:
    """Numeric and flag interpretation matches the vendor on varied bit patterns."""
    parsed = purifier_status(bytes.fromhex(case["hex"]))
    expected = case["expected"]
    for key, value in parsed.items():
        vendor = expected[key]
        if isinstance(value, bool):
            vendor = vendor == "on" if isinstance(vendor, str) else bool(vendor)
        assert value == vendor, key
    assert set(parsed) == {
        name for fields in FIELDS.values() for name, *_ in fields
    } | {name for fields in FLAGS.values() for name, *_ in fields}


@pytest.mark.parametrize("case", VECTORS["decode"])
def test_integrity_and_atomic_rejection(case: dict) -> None:
    """Truncation, corruption and short known records cannot partially change state."""
    data = bytes.fromhex(case["hex"])
    d = make()
    d.process_message(data)
    before = dict(d.attributes)
    for length in range(len(data)):
        assert d.process_message(data[:length]) == {}
    for index in range(len(data)):
        damaged = bytearray(data)
        damaged[index] ^= 1
        assert d.process_message(bytes(damaged)) == {}
    assert d.process_message(frame(237, 3, bytes.fromhex("ff01010110000010ff"))) == {}
    assert d.attributes == before


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("quantify_21", 190),
        ("quantify_21", 1010),
        ("quantify_22", 3010),
        ("quantify_23", 990),
        ("quantify_23", 5010),
        ("quantify_23", 1001),
        ("quantify_23", True),
        ("quantify_23", "3500"),
        ("quantify_23", float("nan")),
        ("cur_quantify", 24),
        ("cur_quantify", True),
        ("power", "on"),
        ("out_water", True),
        ("heat", True),
        ("filter_reset", True),
    ],
)
def test_reject_invalid_or_dangerous_controls(name: str, value: object) -> None:
    """Never clamp invalid volumes or expose undocumented physical operations."""
    with pytest.raises(ValueError):
        purifier_control(name, value)


def test_exact_dispatch_and_no_optimistic_state() -> None:
    """Same subtype softener is isolated; only device readback updates values."""
    d = make()
    assert isinstance(d, Purifier632009CN)
    assert isinstance(make("6360000F"), Softener845)
    assert not isinstance(make("unknown"), Purifier632009CN)
    d.build_send = Mock()  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="report"):
        d.set_attribute("purifier_quantify_23", 3500)
    d.process_message(bytes.fromhex(VECTORS["decode"][0]["hex"]))
    old = d.attributes["purifier_quantify_23"]
    d.set_attribute("purifier_quantify_23", 3500)
    assert d.attributes["purifier_quantify_23"] == old
    assert len(d.build_send.call_args_list) == 2
    assert d.build_send.call_args_list[0].args[0].serialize() == purifier_control(
        "quantify_23",
        3500,
    )
    assert d.build_send.call_args_list[1].args[0].serialize() == purifier_query()
    assert not d.build_init_query()


def test_unknown_records_and_ack() -> None:
    """Unknown extension records are skipped, ACKs are never treated as status."""
    assert purifier_status(frame(237, 3, bytes.fromhex("ff0101fe1f77011005"))) == {
        "error": 5,
    }
    assert purifier_status(frame(237, 2, bytes.fromhex("ff0101011005"))) == {}


def test_entity_metadata_is_model_scoped() -> None:
    """New default entities stay within the precise model and have bounded controls."""
    devices: dict = {
        237: {"entities": {}},
        172: {"entities": {}},
        182: {"entities": {}},
    }
    register_local_entities(devices)
    entries = {
        k: v for k, v in devices[237]["entities"].items() if k.startswith("purifier_")
    }
    assert len(entries) == 16
    assert all(
        v["models"] == ["632009CN"] and v["subtypes"] == [845] for v in entries.values()
    )
    assert entries["purifier_quantify_23"]["max"] == 5000
