"""Exact-model 632009CN adapter using only the existing LAN transport."""

# ruff: file-ignore[any-type, undocumented-public-init, docstring-missing-returns, docstring-missing-exception, no-self-use]

import inspect
from typing import Any

from midealan.device import MideaDevice
from midealan.devices import device_selector as upstream_selector
from midealan.devices.ed import MideaEDDevice

from .purifier_protocol import SWITCHES as PURIFIER_SWITCHES
from .purifier_protocol import (
    VOLUMES,
    purifier_control,
    purifier_query,
    purifier_status,
)


class PurifierFrame:
    """A complete native UART frame for the library transport."""

    def __init__(self, packet: bytes) -> None:
        self.packet = packet

    def serialize(self) -> bytes:
        """Return the frame for authenticated LAN transport."""
        return self.packet


class PurifierStatusQuery(PurifierFrame):
    """Identify the purifier FF status query for response tracking."""


class Purifier632009CN(MideaEDDevice):
    """Expose confirmed purifier settings without optimistic state updates."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._purifier_reported: set[str] = set()
        # Explicit unknowns prevent upstream defaults from looking like readback.
        for name in {*VOLUMES, *PURIFIER_SWITCHES, "cur_quantify"}:
            self._attributes["purifier_" + name] = None

    def build_init_query(self) -> list[PurifierFrame]:  # type: ignore[override]
        """Avoid unrelated generic ED probes."""
        return []

    def build_query(self) -> list[PurifierFrame]:  # type: ignore[override]
        """Poll the complete native FF status."""
        return [PurifierStatusQuery(purifier_query())]

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Publish only device-reported values and retain existing sensor IDs."""
        data = purifier_status(msg)
        self._purifier_reported.update(data)
        parsed = {"purifier_" + key: value for key, value in data.items()}
        for key in ("power", "in_tds", "out_tds", "error"):
            if key in data:
                parsed[key] = data[key]
        if "water_consumption" in data:
            parsed["water_consumption"] = data["water_consumption"] / 1000
            parsed["purifier_water_consumption"] = data["water_consumption"] / 1000
        for slot in (1, 2):
            if f"life_{slot}" in data:
                parsed[f"life{slot}"] = data[f"life_{slot}"]
        self._attributes.update(parsed)
        return parsed

    def set_attribute(self, attr: str, value: Any) -> None:
        """Send an allowlisted setting only after the appliance reported it."""
        name = attr.removeprefix("purifier_")
        packet = purifier_control(name, value)
        if name not in self._purifier_reported:
            raise ValueError("Wait for the appliance to report this setting")
        self.build_send(PurifierFrame(packet))
        # A query, rather than an optimistic assignment, confirms device state.
        self.build_send(self.build_query()[0])


def device_selector(*args: Any, **kwargs: Any) -> MideaDevice | None:
    """Minimal deployment hook; all other devices retain their existing adapter."""
    bound = inspect.signature(upstream_selector).bind(*args, **kwargs)
    bound.apply_defaults()
    values = dict(bound.arguments)
    if (int(values["device_type"]), values["model"], int(values["subtype"])) != (
        237,
        "632009CN",
        845,
    ):
        return upstream_selector(*args, **kwargs)
    values.pop("device_type")
    return Purifier632009CN(**values)
