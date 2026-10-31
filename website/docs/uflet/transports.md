---
title: "Wireless & Network Transports"
slug: /uflet/transports
description: "Talk to microcontrollers over USB serial, Bluetooth LE, Bluetooth Classic SPP, WiFi (TCP, UDP, WebSocket) and MQTT with one async API."
---

# Wireless & Network Transports

Every μFlet link (USB serial, Bluetooth, WiFi or MQTT) is a `Transport` with the same API as [`AsyncSerial`](serial-communication.md). Code written against one works with all of them:

```python
import uflet as uf

async with await uf.connect("ble://AA:BB:CC:DD:EE:FF") as link:
    await link.write_line("STATUS")
    print(await link.read_line(timeout=5))
```

Install the optional drivers with:

```bash
pip install 'flet[hardware]'
```

---

## Connection URLs

`uf.connect(url)` opens a link; `uf.transport_from_url(url)` creates one without opening it. Query parameters are passed to the transport constructor, and keyword arguments override them.

| URL | Transport | Typical device |
| :--- | :--- | :--- |
| `/dev/ttyUSB0`, `COM3`, `serial:///dev/ttyACM0?baudrate=9600` | `AsyncSerial` | Any board over USB, UART adapters |
| `serial:///dev/rfcomm0`, `serial:///dev/cu.HC-05` | `AsyncSerial` | Paired Bluetooth Classic devices exposed as a port by the OS |
| `rfcomm://00:11:22:33:44:55/1`, `bt://…` | `RfcommTransport` | HC-05 / HC-06, ESP32 `BluetoothSerial` (Linux, Windows) |
| `ble://AA:BB:CC:DD:EE:FF`, `ble://MyDevice` | `BleTransport` | Nordic UART, HM-10 / HC-08, Microchip RN487x, any notify+write GATT pair |
| `tcp://192.168.4.1:23`, `telnet://esp32.local`, `tls://…` | `TcpTransport` | ESP32 `WiFiServer`, ESP-Link, ser2net, ESPHome stream server |
| `udp://192.168.1.50:4210?local_port=4210` | `UdpTransport` | Sensor nodes broadcasting telemetry |
| `ws://esp32.local/ws`, `wss://…` | `WebSocketTransport` | ESPAsyncWebServer, MicroPython WebREPL |
| `mqtt://user:pass@broker:1883?rx=dev/out&tx=dev/in`, `mqtts://…` | `MqttTransport` | Devices on Mosquitto, HiveMQ, EMQX, AWS IoT |

Short aliases are accepted in URLs: `baud` (→ `baudrate`), `rx` / `tx` (MQTT topics), `service`, `rx_char`, `tx_char` (BLE UUIDs) and `timeout` (→ `connect_timeout`).

---

## Common API

| Member | Description |
| :--- | :--- |
| `await open()` / `await close()` | Connect / disconnect. Also usable as `async with`. |
| `await read(n=-1, timeout=None)` | Wait for data and return up to `n` bytes; `b""` once closed. |
| `await read_line(timeout=None)` | Read up to and including `\n`, decoded as UTF-8. |
| `await read_until(delim, timeout=None)` | Read up to and including `delim`. |
| `await write(data)` / `await write_line(text, newline="\r\n")` | Send bytes or text. |
| `on_data`, `on_line`, `on_error`, `on_disconnect` | Callbacks (sync or `async`); can be passed to the constructor. |
| `is_open`, `in_waiting`, `description` | Connection state, unread byte count, endpoint label. |

Readers waiting on `read*()` are released when the link closes, and a remote disconnect (unplugged cable, BLE out of range, TCP reset) closes the transport and fires `on_disconnect`. Unread data is capped at `max_buffer` bytes (1 MiB by default), dropping the oldest bytes first.

---

## Bluetooth Low Energy

Phone apps such as *Serial Bluetooth Terminal* and *nRF Toolbox* talk to devices over a "BLE UART" GATT service. `BleTransport` auto-detects the Nordic UART Service, HM-10 (`FFE0`/`FFE1`), and Microchip transparent UART, then falls back to the first notify + write characteristic pair. Writes are chunked to the negotiated MTU.

```python
devices = await uf.scan_ble_devices(timeout=5, uart_only=True)
for d in devices:
    print(d.display_name())   # "ESP32-UART | AA:BB:… | -48 dBm | UART:nus"

link = uf.BleTransport(
    devices[0].address,
    # Optional - only needed for custom GATT services:
    # service_uuid="…", rx_char_uuid="…", tx_char_uuid="…",
)
```

On macOS, devices are identified by a CoreBluetooth UUID instead of a MAC address; use the address `scan_ble_devices()` returns, or the device name.

## Bluetooth Classic (SPP)

Pair the device in the OS first. On Linux and Windows `RfcommTransport` connects directly over an RFCOMM socket. On macOS (or if you prefer), open the serial port the OS creates for the paired device with `AsyncSerial`: `/dev/cu.<device-name>` on macOS, an outgoing `COMx` port on Windows, or `/dev/rfcomm0` on Linux after `sudo rfcomm bind 0 <address> 1`.

## WiFi: TCP, UDP and WebSocket

```python
# ESP32 sketch: WiFiServer server(23); ... client.println(sensor.read());
async with await uf.connect("tcp://192.168.4.1:23") as link:
    while line := await link.read_line():
        print(line.strip())
```

`UdpTransport` with no remote host listens on `local_port` and replies to the last device that sent it a datagram, which suits sensors that broadcast. `WebSocketTransport` sends text frames by default; pass `binary=True` for binary frames.

## MQTT

The device publishes on `rx_topic` and subscribes to `tx_topic`. Every message payload is fed into the stream, so `read_line()` works as long as the device ends messages with a newline; otherwise set `append_newline=True`. Use `on_message` to see topics, subscribe to several topics with a list (or repeat `rx=` in the URL), and use `publish()` to send to other topics. The connection reconnects automatically unless `reconnect=False`.

```python
link = uf.MqttTransport(
    "broker.hivemq.com",
    rx_topic=["greenhouse/+/telemetry"],
    tx_topic="greenhouse/cmd",
    append_newline=True,
)
link.on_message = lambda topic, payload: print(topic, payload)
await link.open()
await link.write("fan=on")
```

---

## In the UI and the terminal

`SerialConsole.attach()` works with any transport:

```python
console = uf.SerialConsole(title="BLE CONSOLE", expand=True)
link = uf.transport_from_url("ble://MyESP32")
console.attach(link)
await link.open()
```

From the command line, `flet monitor` opens an interactive terminal over any URL:

```bash
flet monitor --list                       # schemes + serial ports
flet monitor --scan-ble                   # find BLE UART devices
flet monitor ble://AA:BB:CC:DD:EE:FF
flet monitor tcp://192.168.4.1:23 -t      # with timestamps
flet monitor "mqtt://broker?rx=dev/out&tx=dev/in" --eol lf
flet monitor /dev/ttyUSB0 -b 9600 -s "AT" --duration 1   # send, print reply, exit
```

`flet flash --doctor` reports which transports are available on the current machine.
