---
title: "Serial Communication"
slug: /uflet/serial-communication
description: "Comprehensive guide to asynchronous serial streaming across Desktop, WebSerial, and Mobile USB-OTG with μFlet."
---

# Serial Communication & Streaming

Reliable, non-blocking serial communication is the cornerstone of embedded systems companion applications. μFlet's [`AsyncSerial`] abstraction provides unified streaming across Desktop OSes, modern web browsers, and Android mobile devices.

---

## 1. Discovering Serial Devices

Use [`list_serial_ports()`] to scan for attached hardware:

```python
import uflet as uf

ports = uf.list_serial_ports()
for p in ports:
    print(f"Device: {p.device}")
    print(f"  Description:  {p.description}")
    print(f"  VID:PID:      {p.vid:04X}:{p.pid:04X}" if p.vid else "  VID:PID: None")
    print(f"  Manufacturer: {p.manufacturer}")
    print(f"  Is ESP32:     {p.is_esp32()}")
    print(f"  Is RP2040:    {p.is_rp2040()}")
```

### Automatic Microcontroller Heuristics

[`SerialPortInfo`] provides built-in heuristics identifying common microcontroller development boards and USB-UART bridges:

* **ESP32 Detection** (`p.is_esp32()`): Matches Espressif USB JTAG/serial VID (`0x303A`), Silicon Labs CP210x (`0x10C4`), WCH CH340 (`0x1A86`), FTDI (`0x0403`), and device strings.
* **RP2040 Detection** (`p.is_rp2040()`): Matches Raspberry Pi Foundation VID (`0x2E8A`), CDC ACM PIDs (`0x000A`), and description tokens.
* **Microcontroller Detection** (`p.is_microcontroller()`): Aggregates all known embedded boards to filter out internal system COM ports (like `/dev/ttyS0` or `COM1`).

---

## 2. Asynchronous Serial Stream API

[`AsyncSerial`] integrates directly with Python's `asyncio` event loop. It avoids blocking the UI thread during high-throughput serial telemetry.

### Basic Context Manager Usage

```python
import asyncio
import uflet as uf

async def monitor():
    async with uf.AsyncSerial(
        port="/dev/ttyUSB0",
        baudrate=115200,
        timeout=1.0,
    ) as ser:
        # Write bytes or string
        await ser.write_line("GET_TEMP")

        # Read line asynchronously
        response = await ser.read_line()
        print(f"Sensor responded: {response}")

asyncio.run(monitor())
```

### Event-Driven Callbacks

For continuous streaming (such as IMU or GPS telemetry), attach asynchronous or synchronous callbacks:

```python
def handle_incoming_line(line: str):
    print(f"Telemetry: {line}")

def handle_disconnect():
    print("Microcontroller unplugged!")

ser = uf.AsyncSerial(
    port="/dev/ttyACM0",
    baudrate=921600,
    on_line=handle_incoming_line,
    on_disconnect=handle_disconnect,
)
await ser.open()
```

### Method Reference

| Method | Description |
| :--- | :--- |
| `await open()` | Opens the serial connection and initializes reader tasks. |
| `await close()` | Closes streams and cleanly cancels background reader tasks. |
| `await read(size)` | Reads up to `size` bytes from the stream buffer without blocking. |
| `await read_line()` | Reads bytes until `\n` or `\r\n` is encountered, decoding as UTF-8. |
| `await read_until(delim)` | Reads bytes until a specific delimiter (e.g. `b"\x00"`) is found. |
| `await write(data)` | Transmits bytes or string to the microcontroller. |
| `await write_line(data)` | Transmits data followed by newline (`\r\n`). |
| `await set_dtr(state)` | Toggles Data Terminal Ready (DTR) pin (useful for hardware reset). |
| `await set_rts(state)` | Toggles Request To Send (RTS) pin (used to enter bootloaders). |

---

## 3. Platform Transports

### Desktop (Linux, macOS, Windows)

On desktop operating systems, μFlet uses `serial-asyncio` backed by OS-level file descriptors (`epoll` on Linux, `kqueue` on macOS, and overlapped I/O on Windows).

If `serial-asyncio` is unavailable, μFlet falls back to a threaded consumer queue, ensuring non-blocking operations across all environments.

### Browser / WebAssembly (Pyodide & WebSerial)

When running Flet apps in the browser via WebAssembly (Pyodide), native OS sockets and serial drivers are inaccessible.

μFlet includes a WebSerial transport adapter that connects directly to the browser's W3C `navigator.serial` API:

```python
# In browser (Pyodide), navigator.serial requests user permission via a dialog
ser = uf.AsyncSerial(port="webserial", baudrate=115200)
await ser.open()
```

:::info[Browser Compatibility]
WebSerial requires a Chromium-based browser (Google Chrome, Microsoft Edge, Brave, Opera) running on a secure origin (`https://` or `http://localhost`).
:::

### Mobile USB-Host / OTG (Android)

On Android devices, microcontrollers can be plugged in directly using a USB OTG cable. μFlet bridges Android's `UsbManager` and `UsbDeviceConnection` using Flutter `MethodChannel` and `EventChannel`:

```python
import flet as ft
from flet.controls.services.usb_serial import UsbSerial

def main(page: ft.Page):
    usb = UsbSerial(
        baud_rate=115200,
        on_data=lambda e: print(f"USB OTG Received: {e.data}"),
        on_device_attached=lambda e: print(f"Attached: {e.device_name}"),
        on_device_detached=lambda e: print(f"Detached: {e.device_name}"),
    )
    page.services.append(usb)

ft.app(main)
```

The Android client automatically requests USB device permissions from the user when connected.
