# μFlet & Flet Active Support Policy

Welcome to the official support documentation for **μFlet** and the Flet framework.

μFlet is an actively maintained, production-grade microcontroller and embedded hardware suite. We are committed to providing robust support, active issue triage, continuous driver validation, and responsive maintenance.

---

## 1. Getting Help & Support Channels

Depending on the nature of your inquiry, choose the most effective channel:

| Ingestion Channel | Purpose | Expected Response |
| :--- | :--- | :--- |
| [**GitHub Discussions**](https://github.com/flet-dev/flet/discussions) | Questions, architecture advice, custom board pinouts, community sharing | 1-2 business days |
| [**GitHub Issue Tracker**](https://github.com/flet-dev/flet/issues) | Verified bug reports, driver regressions, missing chip detection, feature requests | Triaged within 48 hours |
| [**Official Documentation**](https://flet.dev/docs/uflet) | Guides, API reference, flashing instructions, troubleshooting FAQs | Continuously updated |

---

## 2. Generating Diagnostic Logs (`doctor`)

When seeking support for hardware communication, serial disconnections, or flashing errors, **always include a diagnostic report**.

### Via Command-Line Interface:
```bash
flet flash --doctor
```

Or when diagnosing an installed CLI environment:
```bash
flet doctor
```

### Via Python:
```python
import json
import uflet as uf

report = uf.doctor(verbose=True)
print(json.dumps(report, indent=2))
```

The report captures your OS version, architecture, Python environment, driver availability (`pyserial`, `serial_asyncio`, `esptool`), user group permissions (`dialout`, `uucp`), and all enumerated serial and UF2 devices without leaking any private tokens or keys.

---

## 3. SLA & Maintenance Guidelines

### Bug Triage & Fix Lifecycle
1. **Initial Review**: Issues labeled `area/hardware` or `area/uflet` are reviewed by the core maintainers within **48 business hours**.
2. **Reproduction & Lab Testing**: Tested on physical hardware in our device lab (ESP32-S3, ESP32-C3, RP2040 Pico, Arduino UNO, STM32 BlackPill).
3. **Patch Release**: High-severity bugs and regressions are patched in immediate point releases.

### Supported Operating Systems
* **Linux**: Ubuntu 22.04+, Debian 12+, Fedora 39+, Arch Linux (x86_64, aarch64 / Raspberry Pi OS).
* **macOS**: macOS 12 (Monterey) through macOS 15 (Sequoia) on Apple Silicon (M1-M4) and Intel x86_64.
* **Windows**: Windows 10 & Windows 11 (x86_64, arm64).
* **Android**: Android 8.0+ (API 26+) with USB-OTG host hardware.
* **Web**: Chromium-based browsers (Chrome, Edge, Opera) with WebSerial enabled on secure HTTPS origins.

---

## 4. Hardware Board Certification Program

Are you a microcontroller manufacturer, open-source hardware team, or development board vendor? We offer a **Certified for μFlet** verification program:

* **Automated Recognition**: Your board's USB VID:PID and CDC identifiers are built directly into μFlet's heuristics.
* **End-to-End Testing**: Automated flashing and serial telemetry verification in CI workflows.
* **Documentation Inclusion**: Listed in the official [Hardware Compatibility Matrix](https://flet.dev/docs/uflet/compatibility-matrix).

To request certification for your board, open a GitHub issue with the tag `[Board Certification]`.

---

## 5. Security Disclosures

If you discover a security vulnerability in μFlet or Flet, please do not file a public issue. Email security reports directly to `security@flet.dev`. Security advisories are patched with highest priority.
