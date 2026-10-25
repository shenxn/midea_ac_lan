"""Read-only pipe telemetry with independent bit-position oracle vectors."""

import json
from pathlib import Path
from typing import Any

import pytest
from midea_ac_lan.local_models import PipeDispenser1046
from midea_ac_lan.local_protocol import ModelCodec
from midealan.const import ProtocolVersion

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/pipe_telemetry.json").read_text(),
)


@pytest.mark.parametrize("case", VECTORS)
def test_pipe_telemetry(case: dict[str, Any]) -> None:
    """Faults, each flag bit and volume bytes match the model's vendor codec."""
    packet = bytes.fromhex(case["hex"])
    parsed = ModelCodec(237, 1046).decode(packet)
    for key, value in case["expected"].items():
        assert parsed[key] == value
    soft = ModelCodec(237, 845).decode(packet)
    assert not any(key in soft for key in case["expected"] if key != "error")
    for length in range(len(packet)):
        assert ModelCodec(237, 1046).decode(packet[:length]) == {}


def test_optional_telemetry_stays_unknown_until_reported() -> None:
    """Missing fields do not become healthy defaults or writable controls."""
    device = PipeDispenser1046(
        name="test",
        device_id=123,
        ip_address="127.0.0.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model="6320088A",
        subtype=1046,
        customize="",
    )
    assert device.get_attribute("a1_error") is None
    assert device.get_attribute("a1_lack_water") is None
    for case in VECTORS:
        mapped = device.process_message(bytes.fromhex(case["hex"]))
        for key, value in case["expected"].items():
            assert mapped["a1_" + key] == (
                value == "on" if isinstance(value, str) else value
            )
    with pytest.raises(ValueError, match="Unsupported"):
        device.set_attribute("a1_lack_water", False)
