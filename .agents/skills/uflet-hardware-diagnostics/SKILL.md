---
name: uflet-hardware-diagnostics
description: Use when diagnosing microcontroller connection failures, Linux permissions (dialout/udev), serial port locks, or preparing diagnostic reports for active support.
---

# μFlet Hardware Diagnostics & Triage

Use this skill when investigating issues with serial communication, hardware enumeration, flashing failures, or assisting users with active support tickets.

## 1. Running Diagnostics

### Via CLI
Execute the built-in diagnostic tool from the project:
```bash
PYTHONPATH=src:../flet/src uv run --directory sdk/python/packages/flet-cli python3 -m flet_cli.cli flash --doctor
```
Or with standard `doctor`:
```bash
PYTHONPATH=src:../flet/src uv run --directory sdk/python/packages/flet-cli python3 -m flet_cli.cli doctor
```

### In Python
```python
import json
import uflet as uf

report = uf.doctor(verbose=True)
print(json.dumps(report, indent=2))
```

---

## 2. Common Failure Modes & Resolutions

### A. Linux Permission Denied (`/dev/ttyUSB*`, `/dev/ttyACM*`)
* **Symptom**: `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`
* **Root Cause**: Linux default udev permissions restrict serial character devices (`c 188`) to `root:dialout` with mode `0660`.
* **Fix**:
  1. Add user to `dialout` or `uucp`:
     ```bash
     sudo usermod -a -G dialout $USER
     ```
  2. For plug-and-play without relogging, create `/etc/udev/rules.d/99-uflet.rules`:
     ```text
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="303a", MODE:="0666", GROUP:="dialout"
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="2e8a", MODE:="0666", GROUP:="dialout"
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="10c4", MODE:="0666", GROUP:="dialout"
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a86", MODE:="0666", GROUP:="dialout"
     ```
  3. Reload rules: `sudo udevadm control --reload-rules && sudo udevadm trigger`

### B. ESP32 Bootloader Sync Timeout
* **Symptom**: `FatalError: Failed to connect to ESP32: No serial data received.`
* **Root Cause**: Board auto-reset circuit failed (DTR/RTS timing issue on CH340 or CP2102) or strapping pin GPIO0 wasn't pulled low.
* **Fix**:
  * Instruct user to hold the `BOOT` button, press `RESET`, release `BOOT`, then retry.
  * Reduce flashing baud rate to `115200`: `flet flash -c esp32 -f firmware.bin -b 115200`.

### C. RP2040 Volume Missing
* **Symptom**: `No mounted RPI-RP2 bootloader drive found.`
* **Root Cause**: The Pico is running application code rather than ROM bootloader.
* **Fix**:
  * Unplug Pico USB $\to$ Hold `BOOTSEL` $\to$ Plug USB back in $\to$ Release `BOOTSEL` after 2 seconds.
  * Verify volume mounting via `flet flash --list-drives`.

### D. Windows COM Port Contention
* **Symptom**: `SerialException: could not open port 'COMx': PermissionError(13, 'Access is denied.')`
* **Root Cause**: Another application has an exclusive lock on the Windows serial handle.
* **Fix**: Terminate conflicting processes (`python.exe`, Arduino IDE, Cura, PuTTY).
