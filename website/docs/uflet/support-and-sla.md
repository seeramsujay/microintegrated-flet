---
title: "Support & Troubleshooting"
slug: /uflet/support-and-sla
description: "Active support policy, troubleshooting common hardware issues, diagnostics, and board certification program."
---

# Support & Troubleshooting Guide

μFlet is backed by an active support program. We are committed to ensuring developers and hardware teams can reliably interface with microcontrollers on every major platform.

---

## 1. Active Support Policy & Channels

We provide multiple tiers of support depending on project requirements:

### Community & Open Source Support
* **GitHub Discussions**: Post questions, share custom board pinouts, and discuss telemetry protocols in [Flet Discussions](https://github.com/flet-dev/flet/discussions).
* **GitHub Issues**: File verified bugs, regression reports, and missing chip support on the [Flet Issue Tracker](https://github.com/flet-dev/flet/issues).
* **Response Guidelines**:
  * Triage of bug reports with diagnostic logs: **Within 48 business hours**.
  * Critical security and driver fix releases: **Priority patch releases**.

### Hardware Vendor & Board Certification Program
Hardware manufacturers, silicon vendors, and maker board companies can submit their boards for official **Certified for μFlet** verification:
* Automated integration test suite verification against your board's USB VID/PID.
* Inclusion in the automatic [`DeviceSelector`][flet.controls.hardware.device_selector.DeviceSelector] detection database.
* To apply, open a [Board Certification Issue](https://github.com/flet-dev/flet/issues/new?template=hardware_board_request.yml) on GitHub.

---

## 2. Common Troubleshooting Scenarios

### Scenario A: `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'` (Linux)

**Cause**: Non-root users do not have read/write access to serial devices by default.

**Resolution**: Add your user account to the `dialout` (Ubuntu/Debian) or `uucp` (Arch Linux) group:
```bash
sudo usermod -a -G dialout $USER
```
After executing, log out completely from your desktop session and log back in, or run `newgrp dialout`.

To verify your membership:
```bash
groups
```

---

### Scenario B: ESP32 Fails to Connect / Timed Out Waiting for Packet Header

**Cause**: The ESP32 is not entering serial bootloader mode automatically, or the USB cable is a charge-only cable without data lines.

**Resolution**:
1. Verify the cable has data lines by running `flet flash -l`. If no port appears when plugging in, replace the cable.
2. Manually enter bootloader mode:
   * Press and hold the **BOOT / 0** button on your ESP32 board.
   * Press and release the **EN / RST** button once.
   * Release the **BOOT / 0** button.
   * Run `flet flash` again.
3. Lower the flashing baud rate to `115200` baud:
   ```bash
   flet flash -c esp32 -f firmware.bin -b 115200
   ```

---

### Scenario C: RP2040 Pico Drive Not Found (`RPI-RP2`)

**Cause**: The Raspberry Pi Pico must be booted into USB mass storage bootloader mode before flashing.

**Resolution**:
1. Unplug the Pico from USB.
2. Press and hold the white **BOOTSEL** button on the Pico.
3. Plug the USB cable back into the computer while continuing to hold **BOOTSEL** for 2 seconds, then release.
4. Verify the volume mounted:
   ```bash
   flet flash --list-drives
   ```
5. On headless Linux systems without an auto-mounter, mount `/dev/sdX` manually:
   ```bash
   sudo mkdir -p /media/pico
   sudo mount /dev/sdb1 /media/pico
   flet flash -f firmware.uf2 -p /media/pico
   ```

---

### Scenario D: `serial.serialutil.SerialException: could not open port 'COM3': PermissionError(13, 'Access is denied.')` (Windows)

**Cause**: Another application (such as the Arduino IDE Serial Monitor, PuTTY, Cura, or a previous Python process) has exclusive access to the COM port.

**Resolution**:
1. Close all open serial monitors, terminal emulators, and slicers.
2. If the port remains locked, disconnect and reconnect the USB cable, or check Task Manager for lingering Python or CLI processes.

---

## 3. Generating a Diagnostic Report for Support Tickets

When submitting a support ticket or opening a bug report, always attach the output of the μFlet diagnostic tool:

```bash
flet flash --doctor
```

You can also export the report as JSON in Python:

```python
import json
import uflet as uf

report = uf.doctor(verbose=True)
print(json.dumps(report, indent=2))
```

Paste this information directly into your GitHub issue to allow maintainers to immediately assess driver versions, USB endpoints, and OS permission status.
