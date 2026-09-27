---
title: "flet flash"
---

# `flet flash`

Flash compiled firmware binaries (`.bin` or `.uf2`) directly to microcontrollers from the command line.

```bash
flet flash -f <firmware_path> [options]
```

## Options

| Flag | Description |
| :--- | :--- |
| `-f, --firmware <path>` | Path to the binary firmware file (`.bin` for ESP32, `.uf2` for RP2040). *(Required)* |
| `-p, --port <port>` | Serial device port path (e.g. `/dev/ttyUSB0`, `COM3`) or mounted bootloader directory. |
| `-c, --chip <chip>` | Target microcontroller (`esp32`, `esp32s2`, `esp32s3`, `esp32c3`, `esp32c6`, `esp8266`, `rp2040`, `auto`). |
| `-b, --baud <baud>` | Serial baud rate for flashing (default: `460800`). |
| `--offset <offset>` | Flash memory address in hex (e.g. `0x0`, `0x1000`). |
| `--erase` | Erase all flash memory sectors prior to programming. |
| `-l, --list-ports` | List all discovered serial ports and microcontrollers, then exit. |
| `--list-drives` | List all mounted RP2040 / Pico UF2 bootloader drives, then exit. |
| `-d, --doctor` | Run μFlet hardware health check and diagnostics report. |

## Examples

Flash an ESP32-S3 binary at 921600 baud with a complete flash erase:

```bash
flet flash -c esp32s3 -f build/firmware.bin -p /dev/ttyACM0 -b 921600 --erase
```

Flash a Raspberry Pi Pico (RP2040) using automatic drive detection:

```bash
flet flash -f build/pico_app.uf2
```

Inspect connected hardware ports:

```bash
flet flash -l
```

Run hardware health checks:

```bash
flet flash --doctor
```

For more details, see the [μFlet CLI & Diagnostics Documentation](../uflet/cli-and-diagnostics.md).
