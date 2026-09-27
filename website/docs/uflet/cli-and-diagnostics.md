---
title: "CLI & Diagnostics"
slug: /uflet/cli-and-diagnostics
description: "Reference guide for `flet flash`, `flet doctor`, and build-time hardware packaging with μFlet."
---

# CLI & Diagnostics Reference

μFlet includes a command-line interface for flashing firmware without writing any code, automated health diagnostics, and production packaging integration with `flet build`.

---

## 1. `flet flash` Reference

The `flet flash` subcommand deploys binary images to connected microcontrollers with rich terminal progress bars.

```bash
flet flash -f <firmware_path> [options]
```

### Options & Arguments

| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--firmware` | `-f` | *(Required)* | Path to the binary file (`.bin` for ESP32, `.uf2` for RP2040 Pico). |
| `--port` | `-p` | `auto` | Serial port path (e.g. `/dev/ttyUSB0`, `COM3`) or mounted drive directory. |
| `--chip` | `-c` | `auto` | Target chip: `esp32`, `esp32s2`, `esp32s3`, `esp32c3`, `esp32c6`, `esp8266`, `rp2040`. |
| `--baud` | `-b` | `460800` | Baud rate for serial flashing. Common speeds: `115200`, `460800`, `921600`, `1500000`. |
| `--offset` | | `auto` | Flash memory offset in hex (e.g. `0x0`, `0x1000`). |
| `--erase` | `--erase-all` | `False` | Erases all flash sectors before programming. |
| `--list-ports`| `-l` | | Prints a formatted table of connected serial ports and microcontrollers. |
| `--list-drives`| | | Prints a table of mounted RP2040 UF2 bootloader volumes. |
| `--doctor` | `-d` | | Runs the μFlet hardware health check and diagnostics report. |

### Usage Examples

#### Flashing an ESP32-S3 over USB at 921600 Baud
```bash
flet flash -c esp32s3 -f build/firmware.bin -p /dev/ttyACM0 -b 921600 --erase
```

#### Flashing a Raspberry Pi Pico (RP2040)
```bash
# Automatically detects mounted RPI-RP2 drive
flet flash -f build/firmware.uf2
```

#### Enumerating Connected Hardware
```bash
flet flash -l
```

Output:
```
                      Connected Serial Ports & Microcontrollers                      
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Device / Port ┃ Description                    ┃ VID:PID ┃ Manufacturer ┃ Chip Detection    ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ /dev/ttyUSB0  │ CP2102 USB to UART Bridge      │ 10C4:EA60│ Silicon Labs │ ESP32 / ESP8266   │
│ /dev/ttyACM0  │ Raspberry Pi Pico CDC          │ 2E8A:000A│ Raspberry Pi │ RP2040 / Pico     │
└───────────────┴────────────────────────────────┴─────────┴──────────────┴───────────────────┘
```

---

## 2. Hardware Diagnostics (`doctor`)

The diagnostic utility checks for hardware dependencies, Linux group permissions, and USB device presence:

```bash
flet flash --doctor
```

You can also run the standard `flet doctor`, which now includes the μFlet Hardware Suite status:

```bash
flet doctor
```

```
Flet 0.1.0 on Linux 6.8.0-31-generic (x86_64)
Python 3.12.2 (/usr/bin/python3)
μFlet Hardware Suite: Ready (pyserial, serial_asyncio, esptool)
  • Connected Microcontrollers / Ports: 2 detected
```

---

## 3. Production Build Packaging (`flet build`)

When packaging your Flet application into a standalone binary or mobile app with `flet build`, μFlet automates permission configuration and dependency injection.

### Automatic Dependency Bundling

If your `pyproject.toml` declares `tool.flet.hardware` or includes `flet[hardware]` in your dependencies:

```toml
[project]
name = "my-telemetry-app"
dependencies = [
    "flet[hardware]",
]

[tool.flet.hardware]
enabled = true
```

The build pipeline automatically bundles:
* `pyserial` and `pyserial-asyncio`
* `esptool`

### Cross-Platform USB Permissions

* **Android (`flet build apk`)**: Automatically injects `<uses-feature android:name="android.hardware.usb.host" android:required="false" />` into the Android application manifest.
* **macOS (`flet build macos`)**: Automatically adds `com.apple.security.device.usb` and `com.apple.security.device.serial` to the application's hardened runtime entitlements file so the app can communicate with serial devices when sandboxed.
