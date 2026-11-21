"""Authenticated BLE framing, fragmented replies, retry and readback regressions."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type]
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from custom_components.midea_ac_lan.ble import client, protocol
from custom_components.midea_ac_lan.ble.appliances import DISH, HOOD, PURIFIER

ADDRESS = "02:00:00:00:00:01"


def reply(session: Any, command: Any, body: Any, mode: Any = 2) -> Any:
    """Encode peer replies with the independently selected transport key."""
    key = session.root if mode == 2 else session.key
    encrypted = protocol.encrypt(key, bytes([command, 1, len(body)]) + body)
    return b"\xaa\x55" + protocol.signed(
        bytes([len(encrypted) + 4, 1, mode]) + encrypted,
    )


def test_secure_session_roundtrip_and_ecdh() -> None:
    """Verify secure session roundtrip and ecdh."""
    s = protocol.Session(PURIFIER.kind, PURIFIER.sn8, ADDRESS)
    assert s.decode(s.packet(1, s.open_id)) == (1, s.open_id)
    peer_key = ec.generate_private_key(ec.SECP256R1())
    peer = peer_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )[1:]
    cmd, body = s.decode(s.confirm(peer))
    assert cmd == 3
    assert len(body) == 64 + len(s.identity) + 16
    assert s.decode(s.request(PURIFIER.query)) == (4, PURIFIER.query)
    # Some E1 firmware excludes byte 0x20 from its business checksum.
    business = b"\x20" + protocol.signed(
        bytes([len(PURIFIER.query) + 4, 0]) + PURIFIER.query,
    )
    assert s.decode(reply(s, 4, business, 3)) == (4, PURIFIER.query)


@pytest.mark.parametrize("raw", [b"", b"\xaa\x55\x04\x00\x01\x00", b"wrong envelope"])
def test_invalid_outer_frames(raw: Any) -> None:
    """Verify invalid outer frames."""
    with pytest.raises(ValueError, match="envelope"):
        protocol.Session(HOOD.kind, HOOD.sn8, ADDRESS).decode(raw)


def test_security_and_business_validation() -> None:
    """Verify security and business validation."""
    s = protocol.Session(HOOD.kind, HOOD.sn8, ADDRESS)
    with pytest.raises(ValueError, match="security"):
        s.decode(b"\xaa\x55" + protocol.signed(b"\x04\x01\x02"))
    with pytest.raises(ValueError, match="session key"):
        s.decode(b"\xaa\x55" + protocol.signed(bytes([24, 1, 3]) + bytes(20)))
    encrypted = protocol.encrypt(s.root, b"\x01\x01\x03x")
    with pytest.raises(ValueError, match="security frame"):
        s.decode(
            b"\xaa\x55"
            + protocol.signed(bytes([len(encrypted) + 4, 1, 2]) + encrypted),
        )
    for body in [b"", b"\x21\x04\x00\xdb", b"\x20\x05\x00\xdb", b"\x20\x04\x00\x01"]:
        with pytest.raises(ValueError, match="appliance envelope"):
            s.decode(reply(s, 4, body))


def make_link(profile: Any = HOOD) -> Any:
    """Apply make link."""
    return client.Link(AsyncMock(), profile, ADDRESS)


def test_notification_fragmentation_and_queue_bound() -> None:
    """Verify notification fragmentation and queue bound."""
    link = make_link()
    packet = link.session.packet(1, b"test")
    link.notified(None, packet[:4])
    assert link.queue.empty()
    link.notified(None, packet[4:] + packet)
    assert link.queue.get_nowait() == packet
    assert link.queue.get_nowait() == packet
    link.notified(None, b"bad")
    assert not link.buf
    link.notified(None, b"\xaa\x55\x01")
    assert not link.buf
    for _ in range(35):
        link.notified(None, packet)
    assert link.queue.qsize() == 32


async def test_receive_filters_handshake_steps() -> None:
    """Verify receive filters handshake steps."""
    link = make_link()
    link.queue.put_nowait(link.session.packet(2, b"old"))
    link.queue.put_nowait(link.session.packet(1, b"current"))
    assert await link.receive(1, 1) == b"current"


async def test_handshake_retry_and_rejection() -> None:
    """Verify handshake retry and rejection."""
    link = make_link()
    link.receive = AsyncMock(side_effect=[TimeoutError, b"ok"])
    packet = Mock(return_value=b"request")
    assert await link.step(1, packet) == b"ok"
    assert packet.call_count == 2
    link.receive = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(TimeoutError, match="handshake"):
        await link.step(2, packet)
    link.session.confirm = Mock(return_value=b"confirm")

    async def step(cmd: Any, factory: Any) -> bytes:
        """Retry one handshake step with bounded timeouts."""
        factory()
        return b"\x01" if cmd == 3 else b"peer"

    link.step = AsyncMock(side_effect=step)
    await link.handshake()
    link.session.confirm.assert_called_once_with(b"peer")
    link.step = AsyncMock(side_effect=[b"", b"peer", b"\x00"])
    with pytest.raises(ValueError, match="rejected"):
        await link.handshake()


async def test_query_filters_frames_and_retries() -> None:
    """Verify query filters frames and retries."""
    link = make_link()
    raw = bytes(9) + b"\x03" + bytes(5)
    valid = bytearray(raw)
    valid[2] = HOOD.kind
    link.session.request = Mock(return_value=b"request")
    link.receive = AsyncMock(side_effect=[TimeoutError, raw, bytes(valid)])
    with (
        patch.object(client, "parse", return_value={"power": False}),
        patch.object(client, "status_fields", return_value={"light": "off"}),
    ):
        assert await link.query() == {"power": False, "controls": {"light": "off"}}
    link.receive = AsyncMock(return_value=bytes(valid))
    with patch.object(client, "parse", return_value={"controls": {"power": "on"}}):
        assert await link.query() == {"controls": {"power": "on"}}
    link.receive = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(TimeoutError, match="fresh"):
        await link.query()


async def test_control_queries_before_and_after_single_write() -> None:
    """Verify control queries before and after single write."""
    link = make_link(PURIFIER)
    off = {"controls": {"sleep": "off"}}
    on = {"controls": {"sleep": "on"}}
    link.query = AsyncMock(side_effect=[off, off, on])
    link.send = AsyncMock()
    link.session.request = Mock(return_value=b"command")
    with patch.object(
        client,
        "asyncio",
        SimpleNamespace(timeout=client.asyncio.timeout, sleep=AsyncMock()),
    ):
        assert await link.set_option("control_sleep", "on") == on
    link.send.assert_awaited_once()
    link.query = AsyncMock(return_value=on)
    link.send.reset_mock()
    assert await link.set_option("control_sleep", "on") == on
    link.send.assert_not_awaited()
    link.query = AsyncMock(return_value=off)
    with (
        patch.object(
            client,
            "asyncio",
            SimpleNamespace(timeout=client.asyncio.timeout, sleep=AsyncMock()),
        ),
        pytest.raises(ValueError, match="did not confirm"),
    ):
        await link.set_option("control_sleep", "on")
    hood = make_link()
    hood.query = AsyncMock(return_value={"controls": {}})
    with pytest.raises(ValueError, match="Burner"):
        await hood.set_option("control_left_stove_off", "press")
    hood.query = AsyncMock(return_value={"controls": {"left_stove_off": "off"}})
    assert await hood.set_option("control_left_stove_off", "press") == {
        "controls": {"left_stove_off": "off"},
    }


async def test_isolated_setting_retries_only_while_idle() -> None:
    """Verify isolated setting retries only while idle."""
    link = make_link()
    off = {"power": False, "gear": 0, "light": False}
    on = {**off, "light": True}
    link.session.request = Mock(return_value=b"command")
    link.send = AsyncMock()
    link.query = AsyncMock(return_value=on)
    assert await link.set_option("light", True) == on
    link.send.assert_not_awaited()
    link.query = AsyncMock(return_value={**off, "power": True})
    with pytest.raises(ValueError, match="idle"):
        await link.set_option("light", True)
    link.query = AsyncMock(side_effect=[off, off, on])
    with patch.object(
        client,
        "asyncio",
        SimpleNamespace(timeout=client.asyncio.timeout, sleep=AsyncMock()),
    ):
        assert await link.set_option("light", True) == on
    assert link.send.await_count == 2
    for replies in [[off, {**off, "power": True}], [off] * 4]:
        link.query = AsyncMock(side_effect=replies)
        with (
            patch.object(
                client,
                "asyncio",
                SimpleNamespace(timeout=client.asyncio.timeout, sleep=AsyncMock()),
            ),
            pytest.raises(ValueError, match="not confirmed"),
        ):
            await link.set_option("light", True)


async def test_connect_guards_and_disconnects_on_handshake_failure() -> None:
    """Verify connect guards and disconnects on handshake failure."""
    info = SimpleNamespace(manufacturer_data={1704: b"x" + HOOD.sn8 + b"B6"}, time=100)
    device = object()
    fake = AsyncMock()
    fake.services = Mock()
    with (
        patch.object(
            client.bluetooth,
            "async_last_service_info",
            return_value=info,
        ) as get_info,
        patch.object(
            client.bluetooth,
            "async_ble_device_from_address",
            return_value=device,
        ) as get_device,
        patch.object(client, "monotonic", return_value=100),
        patch.object(
            client,
            "establish_connection",
            new=AsyncMock(return_value=fake),
        ) as establish,
        patch.object(client.Link, "handshake", new=AsyncMock()) as handshake,
    ):
        async with client.connect(Mock(), HOOD, ADDRESS) as link:
            assert link.client is fake
        fake.disconnect.assert_awaited_once()
        assert establish.call_args.kwargs["ble_device_callback"]() is device
        handshake.side_effect = ValueError("handshake")
        with pytest.raises(ValueError, match="handshake"):
            async with client.connect(Mock(), HOOD, ADDRESS):
                pytest.fail("Handshake failure must not yield a link")
        fake.services.get_service.return_value = None
        with pytest.raises(ValueError, match="service absent"):
            async with client.connect(Mock(), HOOD, ADDRESS):
                pytest.fail("Missing service must not yield a link")
        info.time = -1
        with pytest.raises(ConnectionError, match="new appliance"):
            async with client.connect(Mock(), HOOD, ADDRESS):
                pytest.fail("Stale advertisement must not connect")
        info.manufacturer_data = {}
        with pytest.raises(ConnectionError, match="Matching"):
            async with client.connect(Mock(), HOOD, ADDRESS):
                pytest.fail("Unknown model must not connect")
        get_info.return_value = None
        get_device.return_value = None
        with pytest.raises(ConnectionError, match="Matching"):
            async with client.connect(Mock(), DISH, ADDRESS):
                pytest.fail("Missing scanner must not connect")


def test_business_request_requires_authenticated_session() -> None:
    """Never send business commands with the root key before ECDH completes."""
    session = protocol.Session(HOOD.kind, HOOD.sn8, ADDRESS)
    with pytest.raises(ValueError, match="Missing session key"):
        session.request(HOOD.query)
