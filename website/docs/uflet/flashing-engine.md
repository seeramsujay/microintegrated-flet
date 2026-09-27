---
title: "Firmware Flashing Engine"
slug: /uflet/flashing-engine
description: "High-performance in-process flashing utilities for ESP32 and RP2040 microcontrollers with progress tracking."
---

# Firmware Flashing Engine

Deploying compiled C++, Rust, or MicroPython firmware to physical silicon is a core part of embedded development. μFlet embeds a high-performance flashing engine supporting two major microcontroller families:

1. **Espressif ESP32 Family**: ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6, and ESP8266.
2. **Raspberry Pi RP2040**: Raspberry Pi Pico, Pico W, and compatible boards via USB mass-storage bootloader (UF2 format).

---

## 1. Unified Dispatch: `flash_firmware()`

The highest-level flashing interface is [`flash_firmware()`]. It automatically inspects the target file extension and firmware header magic numbers to dispatch to the correct engine:

```python
import asyncio
import uflet as uf

async def deploy():
    def on_progress(p: uf.FlashProgressUpdate):
        print(f"Status: {p.status:<10} | Progress: {p.percent*100:5.1f}% | Speed: {p.speed_kbps:6.1f} kB/s")

    success = await uf.flash_firmware(
        firmware="binaries/firmware.bin",
        port="/dev/ttyUSB0",
        chip="esp32s3",
        baudrate=921600,
        progress_callback=on_progress,
    )
    if success:
        print("Firmware deployed successfully!")

asyncio.run(deploy())
```

---

## 2. ESP32 Flashing Engine (`ESP32Flasher`)

The [`ESP32Flasher`] communicates with Espressif's ROM bootloader using the serial protocol.

### Dual-Mode Execution

* **In-Process Mode (`esptool.cmds`)**: When `esptool` is installed, μFlet calls internal commands (`detect_chip`, `erase_flash`, `write_flash`) in a background executor thread, yielding fine-grained transfer callbacks.
* **CLI Fallback Mode**: If `esptool` is installed in a separate virtual environment or global path, μFlet launches `python -m esptool` as an asynchronous subprocess and streams stdout to parse live sector write events.

```python
flasher = uf.ESP32Flasher(
    port="/dev/ttyUSB0",
    chip="esp32s3",
    baudrate=921600,
)

# Detect connected chip model automatically
chip_model = await flasher.detect_chip()
print(f"Detected target chip: {chip_model}")

# Erase and flash
await flasher.flash(
    firmware_path="build/app.bin",
    flash_offset=0x0,  # 0x0 for S3/C3, 0x1000 for classic ESP32
    erase_first=True,
    progress_callback=lambda p: print(f"{p.status}: {p.percent*100:.1f}%"),
)
```

### Memory Offset Conventions

| Chip Family | Default Application Offset | Notes |
| :--- | :--- | :--- |
| **ESP32** (Classic) | `0x1000` | Bootloader is at `0x1000`. Combined binaries use `0x1000` or `0x0`. |
| **ESP32-S2** | `0x0` | Native USB or UART. |
| **ESP32-S3** | `0x0` | USB CDC / JTAG bootloader. |
| **ESP32-C3** | `0x0` | RISC-V core. |
| **ESP32-C6** | `0x0` | RISC-V Wi-Fi 6 + Thread. |
| **ESP8266** | `0x0` | NodeMCU / Wemos. |

---

## 3. RP2040 Pico Flashing Engine (`RP2040Flasher`)

The Raspberry Pi RP2040 features a ROM-based USB bootloader that exposes a virtual FAT filesystem labeled `RPI-RP2`.

### Volume Auto-Detection

When a user boots a Pico while holding the **BOOTSEL** button, μFlet automatically detects the mounted drive across all major operating systems:

* **Linux**: `/media/$USER/RPI-RP2`, `/run/media/$USER/RPI-RP2`, or `/proc/mounts`.
* **macOS**: `/Volumes/RPI-RP2`.
* **Windows**: Mounted drive letters (e.g. `E:\`, `F:\`) containing `INFO_UF2.TXT`.

```python
import uflet as uf

drives = uf.detect_uf2_drives()
for d in drives:
    print(f"Found Pico Drive: {d}")
```

### UF2 Format Validation

Before copying, [`RP2040Flasher`] verifies that the input binary contains valid Microsoft UF2 512-byte blocks:

* First magic number: `0x0A324655` (`UF2_MAGIC_START0`)
* Second magic number: `0x9E5D5157` (`UF2_MAGIC_START1`)
* Final magic number: `0x0AB16F30` (`UF2_MAGIC_END`)

```python
flasher = uf.RP2040Flasher()
if not flasher.validate_uf2("firmware.uf2"):
    raise ValueError("Not a valid UF2 binary!")

await flasher.flash(
    firmware_path="firmware.uf2",
    progress_callback=lambda p: print(f"Copying UF2: {p.percent*100:.0f}%"),
)
```

The write is flushed to disk via `os.fsync`. Once the final block is committed, the RP2040 bootloader automatically unmounts the volume and executes the new program.

---

## 4. Progress Tracking Model (`FlashProgressUpdate`)

All flashing routines emit [`FlashProgressUpdate`] events containing rich telemetry:

```python
@dataclass
class FlashProgressUpdate:
    status: str          # "idle", "connecting", "erasing", "writing", "verifying", "complete", "error"
    percent: float       # 0.0 to 1.0
    message: str         # Human-readable status line
    speed_kbps: float    # Transfer throughput in kB/s
    bytes_written: int   # Cumulative bytes transferred
    total_bytes: int     # Total payload size in bytes
    erased_sectors: int  # Sectors formatted so far
    total_sectors: int   # Total sectors to format
    chip_name: str       # Detected target chip string
    elapsed_time: float  # Elapsed seconds since start
```

These events plug directly into the [`FlashProgress` UI control](controls.md#flashprogress) for real-time visualization.
