---
title: "Getting Started"
slug: /uflet/getting-started
description: "Step-by-step guide to installing μFlet, discovering devices, and building your first hardware telemetry dashboard."
---

# Getting Started with μFlet

This tutorial walks you through installing μFlet, verifying your hardware drivers with `doctor`, and building an interactive serial telemetry monitor in under 30 lines of Python.

---

## 1. Installation

Install Flet with the hardware extra, which pulls in asynchronous serial communication and firmware flashing dependencies:

```bash
pip install "flet[hardware]"
```

Alternatively, you can install dependencies using `uv`:

```bash
uv add "flet[hardware]"
```

### Verifying Installation & Drivers

Run the μFlet diagnostic tool to check your system permissions, Python dependencies, and connected microcontrollers:

```bash
flet flash --doctor
```

You will see a formatted health report:

```
                   μFlet Hardware Health Check & Diagnostics                    
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Subsystem                ┃ Status / Version       ┃ Details                  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Operating System         │ Linux 6.8.0            │ Arch: x86_64             │
│ Python Runtime           │ 3.12.2                 │ /usr/bin/python3         │
│ Dependency: pyserial     │ 3.5                    │ Required for serial I/O  │
│ Dependency: serial_async │ 0.6                    │ Required for serial I/O  │
│ Dependency: esptool      │ 4.7.0                  │ Required for ESP32 flash │
│ Serial Devices           │ 1 found                │ /dev/ttyUSB0 (ESP32-S3)  │
│ UF2 Drives (RP2040)      │ None                   │ No BOOTSEL drives        │
└──────────────────────────┴────────────────────────┴──────────────────────────┘
```

:::note[Linux Permission Note]
On Linux distributions (Ubuntu, Debian, Fedora, Arch), non-root users require membership in the `dialout` or `uucp` group to access USB serial devices directly:
```bash
sudo usermod -a -G dialout $USER
```
Log out and log back in for the group membership to take effect.
:::

---

## 2. Hello World: Serial Telemetry Monitor

Here is a complete, runnable Flet desktop application that scans for connected microcontrollers, connects asynchronously, and prints live sensor readings into a [`SerialConsole`]:

```python
import flet as ft
import uflet as uf

def main(page: ft.Page):
    page.title = "μFlet Telemetry Dashboard"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20

    # 1. Device selection dropdown with microcontroller filtering
    selector = uf.DeviceSelector(
        chip_filter=["esp32", "rp2040"],
        auto_scan=True,
    )

    # 2. Dark terminal console with ANSI colors and autoscroll
    console = uf.SerialConsole(
        max_lines=500,
        expand=True,
    )

    status_text = ft.Text("Select a device and click Connect.", italic=True)

    active_serial: uf.AsyncSerial | None = None

    async def connect_click(e):
        nonlocal active_serial
        port = selector.selected_port
        if not port:
            status_text.value = "Please select a serial port first!"
            page.update()
            return

        try:
            status_text.value = f"Connecting to {port} at 115200 baud..."
            page.update()

            active_serial = uf.AsyncSerial(
                port=port,
                baudrate=115200,
                on_line=lambda line: console.append(line + "\n"),
                on_disconnect=lambda: console.append("[SYSTEM] Device disconnected!\n"),
            )
            await active_serial.open()

            # Attach console data entry bar directly to serial writer
            console.attach_serial(active_serial)
            status_text.value = f"Connected to {port}."
            page.update()
        except Exception as err:
            status_text.value = f"Connection failed: {err}"
            page.update()

    connect_btn = ft.ElevatedButton("Connect", icon=ft.Icons.USB, on_click=connect_click)

    page.add(
        ft.Row([selector, connect_btn, status_text], alignment=ft.MainAxisAlignment.START),
        console,
    )

if __name__ == "__main__":
    ft.app(main)
```

Run the app with:
```bash
flet run app.py
```

---

## 3. Flashing Firmware from Python

Deploying new firmware to an ESP32 or Raspberry Pi Pico takes only one function call:

```python
import asyncio
import uflet as uf

async def upload():
    # Automatically detects chip type from file extension (.bin vs .uf2)
    success = await uf.flash_firmware(
        firmware="build/firmware.bin",
        port="/dev/ttyUSB0",
        chip="esp32s3",
        progress_callback=lambda p: print(f"[{p.status.upper()}] {int(p.percent * 100)}% ({p.speed_kbps:.1f} kB/s)"),
    )
    if success:
        print("Firmware flashed successfully!")

asyncio.run(upload())
```

---

## Next Steps

* [Serial Communication](serial-communication.md): Explore baud rates, line parsers, and WebSerial browser execution.
* [Firmware Flashing Engine](flashing-engine.md): Learn about memory offsets, bootloader sequences, and UF2 deployment.
* [Hardware UI Controls](controls.md): Deep dive into `DeviceSelector`, `SerialConsole`, and `FlashProgress`.
* [CLI & Diagnostics](cli-and-diagnostics.md): Automate flashing in scripts with `flet flash`.
