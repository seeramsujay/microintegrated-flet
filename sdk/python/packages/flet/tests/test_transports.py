import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flet.controls.services.usb_serial import UsbSerialDataEvent
from flet.hardware import (
    AsyncSerial,
    BleTransport,
    MqttTransport,
    RfcommTransport,
    TcpTransport,
    Transport,
    TransportError,
    UdpTransport,
    UsbHostTransport,
    WebSocketTransport,
    transport_from_url,
)
from flet.hardware.bluetooth import BLE_UART_PROFILES, BleDeviceInfo


class LoopbackTransport(Transport):
    """In-memory transport that echoes writes back as received data."""

    scheme = "loop"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sent = []

    async def _open(self):
        pass

    async def _close(self):
        pass

    async def _write(self, data):
        self.sent.append(data)
        self._feed_data(data)
        return len(data)


# ---------------------------------------------------------------------------
# Base transport behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_wakes_up_when_transport_closes():
    t = LoopbackTransport()
    await t.open()
    reader = asyncio.ensure_future(t.read_line())
    await asyncio.sleep(0.01)
    assert not reader.done()
    t._feed_data(b"partial")
    await t.close()
    # Previously readers blocked forever once the port closed.
    assert await asyncio.wait_for(reader, 1) == "partial"
    assert await t.read() == b""


@pytest.mark.asyncio
async def test_on_line_does_not_steal_from_read_line():
    t = LoopbackTransport()
    lines = []
    t.on_line = lines.append
    await t.open()
    await t.write_line("hello", newline="\n")
    assert lines == ["hello\n"]
    assert await t.read_line(timeout=1) == "hello\n"
    await t.close()


@pytest.mark.asyncio
async def test_read_timeout_and_buffer_limit():
    t = LoopbackTransport(max_buffer=8)
    await t.open()
    with pytest.raises(asyncio.TimeoutError):
        await t.read_line(timeout=0.05)
    t._feed_data(b"0123456789ABCDEF")
    assert t.in_waiting == 8
    assert await t.read() == b"89ABCDEF"
    await t.close()


@pytest.mark.asyncio
async def test_async_callbacks_and_disconnect():
    t = LoopbackTransport()
    got = []
    disconnected = []

    async def on_data(chunk):
        got.append(chunk)

    t.on_data = on_data
    t.on_disconnect = lambda: disconnected.append(True)
    await t.open()
    await t.write(b"x")
    await asyncio.sleep(0.01)
    assert got == [b"x"]
    t._connection_lost()
    await asyncio.sleep(0.01)
    assert not t.is_open
    assert disconnected == [True]


@pytest.mark.asyncio
async def test_write_when_closed_raises():
    t = LoopbackTransport()
    with pytest.raises(TransportError):
        await t.write(b"x")


# ---------------------------------------------------------------------------
# URL factory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, cls, attrs",
    [
        ("/dev/ttyUSB0", AsyncSerial, {"port": "/dev/ttyUSB0", "baudrate": 115200}),
        ("COM3", AsyncSerial, {"port": "COM3"}),
        ("serial:///dev/ttyACM0?baud=9600", AsyncSerial, {"baudrate": 9600}),
        ("serial://COM7", AsyncSerial, {"port": "COM7"}),
        ("tcp://192.168.4.1:8888", TcpTransport, {"host": "192.168.4.1", "port": 8888}),
        ("telnet://esp32.local", TcpTransport, {"port": 23}),
        ("udp://10.0.0.5:4210?local_port=4211", UdpTransport, {"local_port": 4211}),
        ("ws://esp32.local/ws?binary=true", WebSocketTransport, {"binary": True}),
        (
            "mqtt://u:p%40ss@broker:1884?rx=dev/out&tx=dev/in&qos=1",
            MqttTransport,
            {
                "port": 1884,
                "username": "u",
                "password": "p@ss",
                "rx_topics": ["dev/out"],
                "tx_topic": "dev/in",
                "qos": 1,
            },
        ),
        (
            "mqtts://broker?rx=1&rx=2",
            MqttTransport,
            {"port": 8883, "rx_topics": ["1", "2"]},
        ),
        ("ble://AA:BB:CC:DD:EE:FF", BleTransport, {"device": "AA:BB:CC:DD:EE:FF"}),
        ("ble://My%20ESP32", BleTransport, {"device": "My ESP32"}),
        (
            "rfcomm://00:11:22:33:44:55/3",
            RfcommTransport,
            {"address": "00:11:22:33:44:55", "channel": 3},
        ),
        ("bt://00-11-22-33-44-55", RfcommTransport, {"address": "00:11:22:33:44:55"}),
    ],
)
def test_transport_from_url(url, cls, attrs):
    t = transport_from_url(url)
    assert isinstance(t, cls)
    for key, value in attrs.items():
        assert getattr(t, key) == value


def test_transport_from_url_errors():
    with pytest.raises(ValueError):
        transport_from_url("gopher://x")
    with pytest.raises(ValueError):
        transport_from_url("not-a-port")


# ---------------------------------------------------------------------------
# WiFi transports against real local servers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tcp_transport_echo():
    async def handle(reader, writer):
        while data := await reader.read(100):
            writer.write(data.upper())
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, TcpTransport("127.0.0.1", port) as t:
        await t.write_line("ping", newline="\n")
        assert await t.read_line(timeout=2) == "PING\n"


@pytest.mark.asyncio
async def test_tcp_transport_detects_remote_close():
    async def handle(reader, writer):
        writer.write(b"bye\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        t = TcpTransport("127.0.0.1", port)
        await t.open()
        assert await t.read_line(timeout=2) == "bye\n"
        assert await asyncio.wait_for(t.read(), 2) == b""
        assert not t.is_open


@pytest.mark.asyncio
async def test_tcp_transport_connection_refused():
    with pytest.raises(TransportError):
        await TcpTransport("127.0.0.1", 1, connect_timeout=2).open()


@pytest.mark.asyncio
async def test_udp_transport_roundtrip():
    server = UdpTransport(local_host="127.0.0.1")
    await server.open()
    port = server.local_address[1]
    client = UdpTransport("127.0.0.1", port, local_host="127.0.0.1")
    await client.open()
    try:
        await client.write(b"temp=21.5\n")
        assert await server.read_line(timeout=2) == "temp=21.5\n"
        # Listening side replies to the last peer.
        await server.write(b"ack\n")
        assert await client.read_line(timeout=2) == "ack\n"
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_websocket_transport_echo():
    websockets = pytest.importorskip("websockets.asyncio.server")

    async def echo(ws):
        async for message in ws:
            await ws.send(message)

    async with websockets.serve(echo, "127.0.0.1", 0) as server:
        port = list(server.sockets)[0].getsockname()[1]
        async with WebSocketTransport(f"ws://127.0.0.1:{port}") as t:
            await t.write_line("hello", newline="\n")
            assert await t.read_line(timeout=2) == "hello\n"


# ---------------------------------------------------------------------------
# Serial over a real pseudo-terminal pair
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX pty")
@pytest.mark.asyncio
async def test_async_serial_over_pty():
    pytest.importorskip("serial_asyncio")
    import tty

    master, slave = os.openpty()
    tty.setraw(master)
    port = os.ttyname(slave)
    try:
        async with AsyncSerial(port, baudrate=115200) as ser:
            assert ser.serial is not None
            await ser.write_line("AT", newline="\n")
            data = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, os.read, master, 100),
                2,
            )
            assert data == b"AT\n"
            os.write(master, b"OK\r\n")
            assert await ser.read_line(timeout=2) == "OK\r\n"
            # DTR/RTS must reach the pyserial object behind serial_asyncio
            # (ptys have no modem lines, so swap in a stub to observe it).
            underlying = ser.serial
            stub = types.SimpleNamespace(dtr=None, rts=None)
            with patch.object(type(ser), "serial", stub):
                await ser.set_dtr(True)
                await ser.set_rts(False)
            assert (stub.dtr, stub.rts) == (True, False)
            assert hasattr(underlying, "dtr")
    finally:
        os.close(master)
        os.close(slave)


# ---------------------------------------------------------------------------
# MQTT (fake aiomqtt client)
# ---------------------------------------------------------------------------


class FakeMqttClient:
    instances = []

    def __init__(self, hostname, **kwargs):
        self.hostname = hostname
        self.kwargs = kwargs
        self.subscribed = []
        self.published = []
        self.queue = asyncio.Queue()
        FakeMqttClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.queue.put(None)

    async def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))

    async def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))

    @property
    def messages(self):
        async def gen():
            while (msg := await self.queue.get()) is not None:
                yield msg

        return gen()


@pytest.mark.asyncio
async def test_mqtt_transport_with_fake_client():
    fake = types.SimpleNamespace(Client=FakeMqttClient)
    FakeMqttClient.instances.clear()
    with patch.dict(sys.modules, {"aiomqtt": fake}):
        t = MqttTransport(
            "broker", rx_topic="dev/out", tx_topic="dev/in", append_newline=True
        )
        seen = []
        t.on_message = lambda topic, payload: seen.append((topic, payload))
        await t.open()
        client = FakeMqttClient.instances[0]
        assert client.hostname == "broker"
        assert client.kwargs["port"] == 1883
        assert client.subscribed == [("dev/out", 0)]

        await t.write_line("LED ON", newline="")
        assert client.published == [("dev/in", b"LED ON", 0, False)]

        await client.queue.put(types.SimpleNamespace(topic="dev/out", payload=b"OK"))
        assert await t.read_line(timeout=1) == "OK\n"
        assert seen == [("dev/out", b"OK")]
        await t.close()


@pytest.mark.asyncio
async def test_mqtt_transport_requires_topics():
    with pytest.raises(TransportError):
        await MqttTransport("broker").open()


# ---------------------------------------------------------------------------
# Bluetooth LE (fake bleak client)
# ---------------------------------------------------------------------------


def _char(uuid, props, max_write=244):
    return types.SimpleNamespace(
        uuid=uuid, properties=props, max_write_without_response_size=max_write
    )


def _fake_bleak(services):
    client = MagicMock()
    client.services = services
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    module = types.SimpleNamespace(
        BleakClient=MagicMock(return_value=client),
        BleakScanner=types.SimpleNamespace(find_device_by_name=AsyncMock()),
    )
    return module, client


@pytest.mark.asyncio
async def test_ble_transport_nordic_uart():
    service, rx_uuid, tx_uuid = BLE_UART_PROFILES["nus"]
    rx = _char(rx_uuid, ["notify"])
    tx = _char(tx_uuid, ["write", "write-without-response"], max_write=20)
    module, client = _fake_bleak(
        [types.SimpleNamespace(uuid=service, characteristics=[rx, tx])]
    )
    with patch.dict(sys.modules, {"bleak": module}):
        t = BleTransport("AA:BB:CC:DD:EE:FF")
        await t.open()
        client.start_notify.assert_awaited_once()
        notify_cb = client.start_notify.await_args.args[1]

        # Writes are chunked to the characteristic's max size.
        await t.write(b"x" * 45)
        sizes = [len(c.args[1]) for c in client.write_gatt_char.await_args_list]
        assert sizes == [20, 20, 5]
        assert client.write_gatt_char.await_args.kwargs["response"] is False

        notify_cb(rx, bytearray(b"hello\n"))
        assert await t.read_line(timeout=1) == "hello\n"
        await t.close()
        client.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_ble_transport_generic_fallback_and_name_lookup():
    rx = _char("0000abcd-0000-1000-8000-00805f9b34fb", ["indicate"])
    tx = _char("0000abce-0000-1000-8000-00805f9b34fb", ["write"])
    module, client = _fake_bleak(
        [
            types.SimpleNamespace(
                uuid="0000abc0-0000-1000-8000-00805f9b34fb", characteristics=[rx, tx]
            )
        ]
    )
    module.BleakScanner.find_device_by_name.return_value = object()
    with patch.dict(sys.modules, {"bleak": module}):
        t = BleTransport("MyDevice")
        await t.open()
        module.BleakScanner.find_device_by_name.assert_awaited_once()
        await t.write(b"hi")
        assert client.write_gatt_char.await_args.kwargs["response"] is True
        await t.close()


def test_ble_device_info_profile():
    info = BleDeviceInfo(
        address="AA",
        name="HM10",
        rssi=-40,
        service_uuids=[BLE_UART_PROFILES["hm10"][0]],
    )
    assert info.uart_profile == "hm10"
    assert "UART:hm10" in info.display_name()


@pytest.mark.asyncio
async def test_rfcomm_unsupported_platform_message():
    with (
        patch("flet.hardware.bluetooth.is_rfcomm_supported", return_value=False),
        pytest.raises(TransportError, match="AsyncSerial"),
    ):
        await RfcommTransport("00:11:22:33:44:55").open()


# ---------------------------------------------------------------------------
# Mobile USB host (UsbSerial service)
# ---------------------------------------------------------------------------


def test_usb_serial_data_event_decoding():
    assert UsbSerialDataEvent(name="data", control=None, data=b"\x01\x02").raw_data == (
        b"\x01\x02"
    )
    assert UsbSerialDataEvent(name="data", control=None, data="AQI=").raw_data == (
        b"\x01\x02"
    )


@pytest.mark.asyncio
async def test_usb_host_transport():
    service = MagicMock()
    service.on_data = None
    service.on_device_detached = None
    service.open_port = AsyncMock(return_value=True)
    service.close_port = AsyncMock(return_value=True)
    service.write_data = AsyncMock(return_value=3)

    t = UsbHostTransport(service, baudrate=9600)
    await t.open()
    service.open_port.assert_awaited_once()
    assert service.open_port.await_args.kwargs["baud_rate"] == 9600

    service.on_data(types.SimpleNamespace(raw_data=b"hi\n"))
    assert await t.read_line(timeout=1) == "hi\n"
    assert await t.write(b"abc") == 3

    await t.close()
    assert service.on_data is None
    service.close_port.assert_awaited_once()

    service.open_port = AsyncMock(return_value=False)
    with pytest.raises(TransportError):
        await UsbHostTransport(service).open()
