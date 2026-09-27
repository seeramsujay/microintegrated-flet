---
name: uflet-development-and-testing
description: Use when developing, testing, or debugging μFlet microcontroller communication (AsyncSerial), firmware flashing (ESP32/RP2040), or hardware UI controls.
---

# μFlet Development & Testing

Use this skill when developing, refactoring, or testing μFlet (`uflet` / `flet.hardware`) modules, firmware flashing routines, or hardware UI controls.

## 1. Directory Structure

All μFlet code is organized across three primary directories:

* **Hardware Core**: `sdk/python/packages/flet/src/flet/hardware/`
  * `serial.py`: `AsyncSerial`, `list_serial_ports()`, `SerialPortInfo`, `create_serial_connection()`.
  * `flasher.py`: `ESP32Flasher`, `RP2040Flasher`, `detect_uf2_drives()`, `flash_firmware()`.
* **Hardware UI Controls**: `sdk/python/packages/flet/src/flet/controls/hardware/`
  * `device_selector.py`: `DeviceSelector(Container)` dropdown with port scanning and chip filtering.
  * `serial_console.py`: `SerialConsole(Container)` ANSI terminal with auto-scroll and send bar.
  * `flash_progress.py`: `FlashProgress(Container)` multi-phase firmware flashing dashboard.
* **Top-Level Module**: `sdk/python/packages/flet/src/uflet.py` (exports all APIs, `__version__`, `doctor()`).
* **Client Service**:
  * Flutter: `packages/flet/lib/src/services/usb_serial.dart`
  * Android Host: `client/android/app/src/main/AndroidManifest.xml`
  * Python: `sdk/python/packages/flet/src/flet/controls/services/usb_serial.py`
* **CLI & Packaging**:
  * `sdk/python/packages/flet-cli/src/flet_cli/commands/flash.py`
  * `sdk/python/packages/flet-cli/src/flet_cli/commands/build_base.py`

---

## 2. Running Test Suites

### SDK Hardware Tests
Run from the repository root:

```bash
PYTHONPATH=src /home/suzaykid/.local/bin/uv run --directory sdk/python/packages/flet pytest tests/test_hardware.py -v
```

### CLI Flash & Doctor Tests
Run from the repository root:

```bash
PYTHONPATH=src:../flet/src /home/suzaykid/.local/bin/uv run --directory sdk/python/packages/flet-cli pytest tests/test_flash_command.py -v
```

---

## 3. Key Development Rules & Gotchas

### Flet Composite Controls Attachment Rule
In Flet, composite controls inherit from `Container`. Accessing `self.page` when the control is not yet mounted to a live page will raise `RuntimeError("Control must be added to the page first.")`.
* **Always** wrap direct UI updates in composite control helper methods with `contextlib.suppress(RuntimeError)` or check:
  ```python
  import contextlib

  with contextlib.suppress(RuntimeError):
      self.update()
  ```

### Dropdown Event Handler
The Flet `Dropdown` control uses `on_select`, NOT `on_change`. Ensure any event handler registration uses:
```python
self._dropdown = ft.Dropdown(on_select=self._on_dropdown_select, ...)
```

### TextStyle & Colors in TextSpan
`TextSpan` does NOT accept a direct `color=...` parameter in modern Flet. Colors and weights must be applied via `style=TextStyle(...)`:
```python
ft.TextSpan(text=segment, style=ft.TextStyle(color=fg_color, weight=weight))
```

### Mocking Microcontroller Hardware in Tests
When writing tests for hardware, never attempt to open physical `/dev/tty*` or `COM*` ports directly:
* Use `unittest.mock.patch` on `serial_asyncio.open_serial_connection` or `serial.Serial`.
* For RP2040 tests, create a temporary directory containing `INFO_UF2.TXT` and write a 512-byte valid UF2 binary using magic headers `0x0A324655`, `0x9E5D5157`, `0x0AB16F30`.
* For ESP32 tests, mock `esptool.cmds.detect_chip` or `asyncio.create_subprocess_exec`.
