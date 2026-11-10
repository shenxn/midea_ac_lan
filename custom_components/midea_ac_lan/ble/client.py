"""Open a short authenticated GATT session through HA's Bluetooth manager."""

import asyncio
from time import monotonic
from contextlib import asynccontextmanager
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache
from homeassistant.components import bluetooth
from .protocol import NOTIFY, SERVICE, WRITE, Session
from .controls import command, matches, status_fields
from .appliances import idle, parse, setting


class Link:
    def __init__(self, client, profile, address):
        self.profile = profile
        self.client = client
        self.session = Session(profile.kind, profile.sn8, address)
        self.buf = bytearray()
        self.queue = asyncio.Queue(maxsize=32)

    def notified(self, _, chunk):
        self.buf.extend(chunk)
        while len(self.buf) >= 3:
            if self.buf[:2] != b"\xaa\x55" or self.buf[2] < 4:
                self.buf.clear()
                return
            size = self.buf[2] + 2
            if len(self.buf) < size:
                return
            raw = bytes(self.buf[:size])
            del self.buf[:size]
            if not self.queue.full():
                self.queue.put_nowait(raw)

    async def send(self, data):
        await self.client.write_gatt_char(WRITE, data, response=True)

    async def receive(self, cmd, timeout):
        async with asyncio.timeout(timeout):
            while True:
                received, body = self.session.decode(await self.queue.get())
                if received == cmd:
                    return body

    async def step(self, cmd, make_packet):
        packet = make_packet()
        for attempt in range(3):
            if cmd == 1 and attempt:
                packet = make_packet()
            await self.send(packet)
            try:
                return await self.receive(cmd, 1.7)
            except TimeoutError:
                continue
        raise TimeoutError(f"No reply to BLE handshake step {cmd}")

    async def handshake(self):
        s = self.session
        await self.step(1, lambda: s.packet(1, s.open_id))
        peer = await self.step(2, lambda: s.packet(2, b""))
        result = await self.step(3, lambda: s.confirm(peer))
        if result[:1] != b"\x01":
            raise ValueError("Appliance rejected BLE session")

    async def query(self):
        for delay in (0.18, 1, 1.5, 2):
            await self.send(self.session.request(self.profile.query))
            try:
                async with asyncio.timeout(delay):
                    while True:
                        raw = await self.receive(4, delay)
                        if raw[9:10] == b"\x03" and raw[2:3] == bytes(
                            [self.profile.kind]
                        ):
                            state = parse(self.profile, raw)
                            state["controls"] = status_fields(self.profile, raw)
                            return state
            except TimeoutError:
                continue
        raise TimeoutError("No fresh appliance status")

    async def set_option(self, key, value, *, allow_cycle=False):
        if key.startswith("control_"):
            field = key.removeprefix("control_")
            state = await self.query()
            observed = state["controls"]
            frame = command(
                self.profile, field, value, observed, allow_cycle=allow_cycle
            )
            if field.endswith("_stove_off") and observed.get(field) not in (
                "off",
                "working",
            ):
                raise ValueError("Burner has not reported state")
            if matches(field, value, observed):
                return state
            await self.send(self.session.request(frame))
            # One write only. Poll until the appliance confirms the desired state.
            for delay in (0.45, 0.8, 1.5):
                await asyncio.sleep(delay)
                state = await self.query()
                if matches(field, value, state["controls"]):
                    return state
            raise ValueError(f"Appliance did not confirm {field}")
        frame = setting(self.profile, key, value)
        state = await self.query()
        if state[key] == value:
            return state
        if not idle(self.profile, state):
            raise ValueError("Only adjustable while appliance is idle")
        await self.send(self.session.request(frame))
        # Some modules discard the first business message after a pause. Only
        # retry an idempotent setting after querying its actual state.
        for attempt in range(3):
            await asyncio.sleep(0.55)
            state = await self.query()
            if state[key] == value:
                return state
            if not idle(self.profile, state):
                break
            if attempt == 0:
                await self.send(self.session.request(frame))
        raise ValueError("Appliance setting not confirmed by readback")


@asynccontextmanager
async def connect(hass, profile, address):
    info = bluetooth.async_last_service_info(hass, address, connectable=True)
    get_device = lambda: bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    device = get_device()
    if (
        not device
        or not info
        or info.manufacturer_data.get(1704, b"")[1:11]
        != profile.sn8 + f"{profile.kind:02X}".encode()
    ):
        raise ConnectionError("Matching COLMO advertisement unavailable")
    if monotonic() - info.time > 90:
        raise ConnectionError("Waiting for a new appliance advertisement")
    client = await establish_connection(
        BleakClientWithServiceCache,
        device,
        profile.name,
        max_attempts=2,
        ble_device_callback=get_device,
    )
    try:
        if client.services.get_service(SERVICE) is None:
            raise ValueError("Appliance BLE service absent")
        link = Link(client, profile, address)
        await client.start_notify(NOTIFY, link.notified)
        await link.handshake()
        yield link
    finally:
        await client.disconnect()
