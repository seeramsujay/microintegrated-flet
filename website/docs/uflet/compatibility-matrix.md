---
title: "Compatibility Matrix"
slug: /uflet/compatibility-matrix
description: "Tested microcontrollers, development boards, USB bridge ICs, and host OS platform compatibility."
---

# Hardware Compatibility Matrix

μFlet is engineered and tested against a broad spectrum of commercial microcontrollers, open-source boards, and USB-to-UART bridge silicon.

---

## 1. Supported Microcontrollers

| Chip / Family | Manufacturer | Core Architecture | Serial Telemetry | Firmware Flashing | Auto Chip Detection |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **ESP32** (Classic) | Espressif Systems | Dual Tensilica Xtensa LX6 | Yes | Yes (0x1000) | Yes |
| **ESP32-S2** | Espressif Systems | Single Xtensa LX7 | Yes | Yes (0x0) | Yes |
| **ESP32-S3** | Espressif Systems | Dual Xtensa LX7 + Vector | Yes | Yes (0x0) | Yes |
| **ESP32-C3** | Espressif Systems | 32-bit RISC-V @ 160MHz | Yes | Yes (0x0) | Yes |
| **ESP32-C6** | Espressif Systems | 32-bit RISC-V + Zigbee/Thread | Yes | Yes (0x0) | Yes |
| **ESP8266** | Espressif Systems | Tensilica L106 | Yes | Yes (0x0) | Yes |
| **RP2040** (Pico / Pico W) | Raspberry Pi | Dual ARM Cortex-M0+ | Yes | Yes (UF2 mass-storage) | Yes |
| **RP2350** (Pico 2) | Raspberry Pi | Dual ARM Cortex-M33 / RISC-V | Yes | Yes (UF2 mass-storage) | Yes |
| **ATmega328P** (Arduino Uno) | Microchip / Atmel | 8-bit AVR | Yes | Via External Tool | Yes |
| **ATmega2560** (Mega) | Microchip / Atmel | 8-bit AVR | Yes | Via External Tool | Yes |
| **SAMD21 / SAMD51** | Microchip / Atmel | ARM Cortex-M0+ / M4F | Yes | Yes (UF2 mass-storage) | Yes |
| **STM32F4 / F1** (BlackPill) | STMicroelectronics| ARM Cortex-M4 / M3 | Yes | DFU / Serial | Yes |
| **nRF52840** (micro:bit v2) | Nordic Semiconductor | ARM Cortex-M4F | Yes | Yes (DAPLink / UF2) | Yes |

---

## 2. USB-to-UART Bridge Silicon

When microcontrollers don't expose native USB, companion boards use USB bridge ICs. μFlet includes automatic VID/PID heuristics for all major bridges:

| IC Model | Manufacturer | USB VID : PID | Default Linux Driver | Tested Maximum Baud |
| :--- | :--- | :--- | :--- | :--- |
| **CP2102 / CP2104** | Silicon Labs | `10C4:EA60` | `cp210x` | 921,600 baud |
| **CH340G / CH340C** | WCH | `1A86:7523` | `ch341` | 460,800 baud |
| **CH343 / CH9102** | WCH | `1A86:55D4` | `ch343` / CDC-ACM | 1,500,000 baud |
| **FT232RL / FT231X** | FTDI | `0403:6001`, `0403:6015` | `ftdi_sio` | 921,600 baud |
| **PL2303** | Prolific | `067B:2303` | `pl2303` | 115,200 baud |
| **Native CDC-ACM** | Espressif / RPi | `303A:1001`, `2E8A:000A` | `cdc_acm` | Virtual USB High-Speed |

---

## 3. Host Platform Support

| Operating System | Architecture | Serial Streaming | Firmware Flashing | Special Notes |
| :--- | :--- | :---: | :---: | :--- |
| **Linux** (Ubuntu, Debian, Fedora, Arch) | `x86_64`, `aarch64` (Raspberry Pi OS) | Yes | Yes | Requires user in `dialout` or `uucp` group. |
| **macOS** (macOS 12 Monterey - macOS 15 Sequoia) | Apple Silicon (M1-M4), Intel | Yes | Yes | Hardened runtime requires serial entitlements. |
| **Windows** (Windows 10, Windows 11) | `x86_64`, `arm64` | Yes | Yes | Modern CP210x / CH340 drivers auto-install via Windows Update. |
| **Android** (API 26+) | `arm64-v8a`, `armeabi-v7a` | Yes (USB-OTG) | Roadmap | Requires USB OTG adapter and host support. |
| **Web Browsers** (Chrome, Edge, Opera) | Any (Desktop & ChromeOS) | Yes (WebSerial) | Web-USB | Requires Chromium-based browser on HTTPS origin. |
| **iOS / iPadOS** | `arm64` | In Progress | No | Limited by Apple Lightning/USB-C MFi external accessory restrictions. |
