---
title: "Overview"
slug: /uflet
description: "μFlet is the official microcontroller communication, telemetry, and firmware deployment toolkit for Flet."
---

# μFlet: Microcontroller & Hardware Toolkit

**μFlet** (pronounced *micro-Flet*, module name `uflet`) is the official hardware and microcontroller engineering toolkit for the Flet ecosystem. It brings native hardware streaming, embedded firmware flashing, and reactive hardware UI controls to Python developers across Desktop, Web, and Mobile.

```
       ┌────────────────────────────────────────────────────────┐
       │             Python Application (`flet`, `uflet`)       │
       └────────────────────────────────────────────────────────┘
                    │                              │
        Hardware UI Controls               Hardware Core Tier
        (DeviceSelector, SerialConsole,    (AsyncSerial, ESP32Flasher,
         FlashProgress)                     RP2040Flasher)
                    │                              │
         ┌──────────┴──────────┐        ┌──────────┴──────────┐
         │ Desktop / WebClient │        │ Native OS / Web-API │
         └─────────────────────┘        └─────────────────────┘
                    │                              │
         ┌────────────────────────────────────────────────────┐
         │             Target Microcontrollers                │
         │  ESP32 / S2 / S3 / C3 / C6  •  RP2040 Pico  •  MCU │
         └────────────────────────────────────────────────────┘
```

## Why μFlet?

Traditional microcontroller tooling requires stitching together heterogeneous command-line tools (`esptool`, `picotool`, `minicom`, `screen`), third-party GUI serial monitors, and platform-specific drivers. Developing desktop or mobile companion dashboards for embedded devices typically required learning C++ (Qt) or Dart/Flutter from scratch.

μFlet eliminates this friction:

* **Pure Python Simplicity**: Write both your embedded communication logic, firmware flashers, and cross-platform UI in Python using familiar async/await idioms.
* **Unified Transport Architecture**: The same [`AsyncSerial`][flet.hardware.serial.AsyncSerial] API communicates with microcontrollers via native OS serial ports on Desktop (Linux, macOS, Windows), the W3C WebSerial API in WebAssembly browsers (Chrome, Edge, Opera), and Android USB-Host / OTG channels.
* **Dual Firmware Flashing Engine**: Embedded upload utilities directly in Python and CLI:
  * **ESP32 Family**: High-speed programming for ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6, and ESP8266 with automatic chip detection, stub bootloader execution, and sector erase.
  * **RP2040 (Raspberry Pi Pico)**: Automatic volume discovery for USB mass-storage bootloaders (`RPI-RP2`), UF2 magic header validation, and chunked write deployment with filesystem sync.
* **Drop-in Hardware UI Controls**: Pre-built widgets engineered specifically for hardware workflows:
  * [`DeviceSelector`][flet.controls.hardware.device_selector.DeviceSelector]: Dropdown with auto-refresh scanning and microcontroller vendor/chip filtering.
  * [`SerialConsole`][flet.controls.hardware.serial_console.SerialConsole]: Dark-themed high-throughput terminal container with ANSI escape sequence color rendering, auto-scrolling, buffer truncation, and hex transmission.
  * [`FlashProgress`][flet.controls.hardware.flash_progress.FlashProgress]: Real-time progress bar with live transfer speeds (kB/s), sector erase indicators, and status badges.
* **Production Packaging & Tooling**: Subcommand `flet flash` for CLI-based deployment, `uflet doctor` for automated hardware health diagnostics, and `flet build` auto-bundling for USB host permissions on Android and serial entitlements on macOS.

---

## Architecture at a Glance

| Layer | Component | Platform Support | Purpose |
| :--- | :--- | :--- | :--- |
| **UI Tier** | `DeviceSelector`, `SerialConsole`, `FlashProgress` | Desktop, Web, Mobile | Real-time hardware control widgets |
| **Transport Tier** | `AsyncSerial`, `list_serial_ports()` | Linux, macOS, Windows, WebSerial, Android OTG | Non-blocking streaming, framing, baud negotiation |
| **Deployment Tier** | `ESP32Flasher`, `RP2040Flasher`, `flash_firmware()` | Desktop, CLI | In-process firmware flashing and verification |
| **Client Channel Tier**| `UsbSerial` Service, Android USB-Host | Android (OTG) | MethodChannel and EventChannel bridge |
| **CLI & Diagnostics** | `flet flash`, `flet doctor`, `uflet doctor` | All platforms | Hardware health checks, flash automation |

---

## Supported Silicon & Development Boards

* **Espressif Systems**:
  * ESP32 (Original Dual-Core)
  * ESP32-S2, ESP32-S3 (Dual-Core LX7 + AI instructions)
  * ESP32-C3, ESP32-C6 (RISC-V architecture)
  * ESP8266 (NodeMCU, Wemos D1 Mini)
* **Raspberry Pi**:
  * Raspberry Pi Pico / Pico H / Pico W / Pico 2 (RP2040 / RP2350)
  * Adafruit Feather RP2040, SparkFun Pro Micro RP2040, Waveshare RP2040
* **Arduino & Generic USB-CDC**:
  * Arduino Uno, Mega 2560, Nano (via CH340, CP2102, FTDI FT232R)
  * STM32 BlackPill / BluePill (USB CDC ACM & DFU)
  * BBC micro:bit v1 & v2

---

## Active Support & Maintenance

μFlet is maintained as a tier-1 product within the Flet repository with active support:
* **Continuous Integration**: Hardware abstraction test suites verified on every commit.
* **Diagnostic Reporting**: Built-in `flet flash --doctor` command to inspect local driver permissions and USB buses.
* **Board Certification**: Hardware vendors and makers can submit board definitions for automated detection and testing.
* **Direct Assistance**: Dedicated support via [GitHub Discussions](https://github.com/flet-dev/flet/discussions) and issue trackers.

:::tip[Ready to start?]
Proceed to the [Getting Started Guide](getting-started.md) to set up your environment and flash your first board in under 5 minutes.
:::
