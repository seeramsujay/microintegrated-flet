---
title: "Hardware UI Controls"
slug: /uflet/controls
description: "Specialized UI controls for microcontroller dashboards: DeviceSelector, SerialConsole, and FlashProgress."
---

# Hardware UI Controls

μFlet includes a suite of hardware-focused UI controls designed to accelerate building diagnostic tools, configuration utilities, and desktop companion dashboards.

---

## 1. `DeviceSelector`

[`DeviceSelector`] is a specialized dropdown container that discovers, filters, and monitors connected serial devices in real-time.

```python
import flet as ft
import uflet as uf

selector = uf.DeviceSelector(
    chip_filter=["esp32", "rp2040"],  # Only show ESP32 and Pico devices
    auto_scan=True,                    # Poll in background for hardware hotplugging
    scan_interval=2.0,                 # Scan every 2 seconds
    on_select=lambda e: print(f"Selected port: {selector.selected_port}"),
    on_device_connected=lambda port: print(f"Plugged in: {port.device}"),
    on_device_disconnected=lambda port: print(f"Unplugged: {port.device}"),
)
```

### Properties

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `selected_port` | `Optional[str]` | `None` | The currently selected device path (e.g. `/dev/ttyUSB0` or `COM3`). |
| `chip_filter` | `str \| list[str]` | `None` | Filters listed ports by chip type (`"esp32"`, `"rp2040"`, `"pico"`). |
| `vid_filter` | `int \| list[int]` | `None` | Filters listed ports by USB Vendor ID (e.g. `0x10C4`, `0x2E8A`). |
| `auto_scan` | `bool` | `False` | When `True`, periodically polls system ports for hotplug events. |
| `scan_interval`| `float` | `2.0` | Interval in seconds between background scans when `auto_scan=True`. |

### Events & Methods

* **`on_select`**: Fired when the user selects a port from the dropdown.
* **`on_device_connected`**: Fired when a new microcontroller is physically plugged into USB.
* **`on_device_disconnected`**: Fired when a connected board is removed.
* **`refresh()`**: Manually triggers an immediate port scan and refreshes dropdown options.

---

## 2. `SerialConsole`

[`SerialConsole`] provides a high-throughput, dark-themed terminal view for serial debugging. It parses ANSI escape sequences into styled text spans and includes a bottom data-entry bar.

```python
import flet as ft
import uflet as uf

console = uf.SerialConsole(
    max_lines=1000,         # Retain up to 1000 lines before pruning
    auto_scroll=True,       # Stick to the bottom as new lines arrive
    font_size=12,           # Terminal font size in pixels
    expand=True,            # Expand to fill available layout space
)

# Append lines with ANSI color escape codes
console.append("\x1b[32m[OK]\x1b[0m Sensor initialized successfully.\n")
console.append("\x1b[31m[ERROR]\x1b[0m I2C timeout on address 0x68.\n")

# Wire directly to an active serial port
# User typing in the console entry bar will transmit to the device automatically
ser = uf.AsyncSerial(port="/dev/ttyUSB0", baudrate=115200)
console.attach_serial(ser)
```

### Features

* **ANSI Color Codes**: Translates `\x1b[31m` (red), `\x1b[32m` (green), `\x1b[33m` (yellow), `\x1b[34m` (blue), and bold styling directly into Flet [`TextSpan`] styles.
* **High Throughput Buffer**: Automatically truncates older lines when buffer exceeds `max_lines` to preserve memory and rendering performance.
* **Interactive Entry Bar**: Built-in text field with configurable line endings (`\r\n`, `\n`, `\r`, or `none`) and raw HEX transmission mode (e.g. `01 03 00 00 00 02 C4 0B`).
* **Toolbar Controls**: Built-in buttons for auto-scroll toggle, stream pause/resume, and buffer clearing.

### Methods

* **`append(text: str)`**: Appends a raw string (with optional ANSI escape codes) to the terminal view.
* **`clear()`**: Clears the console line buffer.
* **`attach_serial(serial_instance)`**: Binds the console entry bar directly to an [`AsyncSerial`] instance.

---

## 3. `FlashProgress`

[`FlashProgress`] is a progress dashboard widget that renders multi-stage firmware deployment metrics.

```python
import flet as ft
import uflet as uf

progress = uf.FlashProgress()

# Update directly from a FlashProgressUpdate event
update = uf.FlashProgressUpdate(
    status="writing",
    percent=0.65,
    speed_kbps=245.8,
    bytes_written=665600,
    total_bytes=1024000,
    chip_name="ESP32-S3",
    elapsed_time=2.7,
    message="Writing at 0x10000 (65%)...",
)
progress.update_from_event(update)
```

### Display Elements

1. **Phase Status Glyphs**: Visual indicators for stages:
   * `idle`: Waiting icon
   * `connecting`, `erasing`, `writing`, `verifying`: Animated spinner
   * `complete`: Green checkmark
   * `error`: Red alert icon
2. **Transfer Rate**: Real-time throughput in kB/s.
3. **Sector Metrics**: Shows current erased/written sectors against total sectors.
4. **Elapsed Timer**: Live duration clock tracking upload time.

### Methods

* **`update_from_event(event: FlashProgressUpdate)`**: Updates all labels, progress bars, and status icons from a progress event.
* **`reset()`**: Resets the control back to the `idle` state.
