"""Exact-model hood adapter retaining upstream fan and light entity identities."""

# ruff: file-ignore[any-type, undocumented-public-init, docstring-missing-returns, docstring-missing-exception]
import inspect
from typing import Any

from midealan.device import MideaDevice
from midealan.devices.b6 import MideaB6Device

from .hood_protocol import hood_control, hood_status
from .purifier_model import PurifierFrame
from .purifier_model import device_selector as previous_selector


class Hood730007C9(MideaB6Device):
    """Add four documented speeds and confirmed model-specific settings."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._default_speeds = {
            0: "off",
            1: "level_1",
            2: "level_2",
            3: "level_3",
            4: "level_4",
        }
        self.set_customize(kwargs.get("customize", ""))
        self._hood_reported: set[str] = set()
        for key in ("wisdom_wind", "gesture", "linkage", "error_code", "wind_pressure"):
            self._attributes["hood_" + key] = None

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Publish validated device reports; command ACKs do not confirm state."""
        data = hood_status(msg)
        if not data:
            return {}
        status = super().process_message(msg)
        self._hood_reported.update(data)
        extra = {"hood_" + k: v for k, v in data.items()}
        self._attributes.update(extra)
        return status | extra

    def set_attribute(self, attr: str, value: Any) -> None:
        """Send a supported setting and query its actual state."""
        if not attr.startswith("hood_"):
            super().set_attribute(attr, value)
            return
        name = attr.removeprefix("hood_")
        packet = hood_control(name, value)
        if name not in self._hood_reported:
            raise ValueError("Wait for the hood to report this setting")
        self.build_send(PurifierFrame(packet))
        self.build_send(self.build_query()[0])


def device_selector(*args: Any, **kwargs: Any) -> MideaDevice | None:
    """Minimal deployment hook preserving the purifier and other appliances."""
    from midealan.devices import device_selector as upstream_selector  # ruff: ignore[import-outside-top-level]

    bound = inspect.signature(upstream_selector).bind(*args, **kwargs)
    bound.apply_defaults()
    values = dict(bound.arguments)
    if (int(values["device_type"]), values["model"], int(values["subtype"])) != (
        182,
        "730007C9",
        0,
    ):
        return previous_selector(*args, **kwargs)
    values.pop("device_type")
    return Hood730007C9(**values)
