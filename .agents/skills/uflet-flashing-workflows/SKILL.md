---
name: uflet-flashing-workflows
description: Use when creating, updating, or debugging firmware flashing workflows for ESP32 and RP2040 devices in Python or via the flet flash CLI.
---

# μFlet Firmware Flashing Workflows

Use this skill when implementing automated firmware deployment pipelines, adding support for new microcontrollers, or debugging flashing issues.

## 1. High-Level Dispatch Architecture

The [`flash_firmware()`][flet.hardware.flasher.flash_firmware] entry point automatically determines target technology:

```python
import uflet as uf

success = await uf.flash_firmware(
    firmware="app.bin",      # Binary file path
    port="/dev/ttyUSB0",     # Target port (or auto-detected)
    chip="esp32s3",          # Target chip (auto, esp32, rp2040, etc.)
    baudrate=921600,         # Upload speed
    flash_offset=0x0,        # Offset (None for auto)
    erase_first=False,       # Erase sectors before write
    progress_callback=cb,    # Callable receiving FlashProgressUpdate
)
```

### Heuristic Selection:
1. If `firmware` ends with `.uf2` or `chip == "rp2040"`, routes to `RP2040Flasher`.
2. If `firmware` ends with `.bin` or `chip` matches `esp*`, routes to `ESP32Flasher`.
3. If chip is not specified, inspects the binary:
   * First 4 bytes `0x0A324655` $\to$ RP2040 UF2 flasher.
   * First byte `0xE9` (ESP ROM magic) $\to$ ESP32 flasher.

---

## 2. ESP32 Flashing Deep-Dive

### Offsets by Chip
* **ESP32 Classic**: Application code starts at `0x1000` (or `0x10000` when partitioning table is separate; monolithic images typically `0x1000` or `0x0`).
* **ESP32-S2 / S3 / C3 / C6 / ESP8266**: Offset is `0x0`.

### Dual Flashing Strategy
1. **In-Process API (`esptool.cmds`)**:
   Runs inside `asyncio.to_thread` to prevent blocking the event loop. Captures stdout/stderr via custom StringIO redirectors to extract sector write percentages.
2. **Subprocess Fallback**:
   Executes `python -m esptool --chip <chip> --port <port> --baud <baud> write_flash <offset> <file>` using `asyncio.create_subprocess_exec` and asynchronously reads stdout lines.

---

## 3. RP2040 UF2 Deployment Deep-Dive

### Block Format
* A UF2 file consists of 512-byte blocks.
* Blocks start with `0x0A324655` (`magicStart0`) and `0x9E5D5157` (`magicStart1`), and end with `0x0AB16F30` (`magicEnd`).
* Block writes must be sequential and flushed to disk with `os.fsync(fd)` before closing the file descriptor.

### Drive Auto-Detection
Mounted volumes labeled `RPI-RP2` are scanned via `detect_uf2_drives()`:
* **Linux**: `/media/$USER/RPI-RP2`, `/run/media/$USER/RPI-RP2`, or `/proc/mounts`.
* **macOS**: `/Volumes/RPI-RP2`.
* **Windows**: Mounted drive letters with `INFO_UF2.TXT`.
