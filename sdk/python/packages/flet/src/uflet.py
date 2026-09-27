"""
μFlet (uflet) - The Official Microcontroller & Embedded Hardware Toolkit for Flet.

Provides non-blocking serial communication, high-performance firmware flashing
engines for ESP32 and RP2040 microcontrollers, and hardware-reactive UI controls.

Usage:
    import uflet as uf

    # Discover devices
    ports = uf.list_serial_ports()

    # Async serial stream
    async with uf.AsyncSerial(port="/dev/ttyUSB0", baudrate=115200) as ser:
        await ser.write_line("PING")
        response = await ser.read_line()

    # Flash firmware
    await uf.flash_firmware(
        firmware="firmware.bin",
        port="/dev/ttyUSB0",
        chip="esp32s3",
    )
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from flet.hardware.flasher import (
    ESP32Flasher,
    FirmwareFlasher,
    FlashProgressUpdate,
    RP2040Flasher,
    detect_uf2_drives,
    flash_firmware,
)
from flet.hardware.serial import (
    AsyncSerial,
    Parity,
    SerialPortInfo,
    StopBits,
    create_serial_connection,
    list_serial_ports,
)

# Controls are imported lazily or directly when needed
from flet.controls.hardware.device_selector import DeviceSelector
from flet.controls.hardware.flash_progress import FlashProgress
from flet.controls.hardware.serial_console import SerialConsole
from flet.controls.services.usb_serial import (
    UsbSerial,
    UsbSerialDataEvent,
    UsbSerialDeviceEvent,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # Hardware Communication
    "AsyncSerial",
    "SerialPortInfo",
    "Parity",
    "StopBits",
    "list_serial_ports",
    "create_serial_connection",
    # Firmware Flashing
    "ESP32Flasher",
    "RP2040Flasher",
    "FirmwareFlasher",
    "FlashProgressUpdate",
    "detect_uf2_drives",
    "flash_firmware",
    # UI Controls
    "DeviceSelector",
    "SerialConsole",
    "FlashProgress",
    # Mobile Service
    "UsbSerial",
    "UsbSerialDataEvent",
    "UsbSerialDeviceEvent",
    # Diagnostics & Support
    "doctor",
]


def doctor(verbose: bool = False) -> Dict[str, Any]:
    """
    Run the μFlet Hardware Diagnostics & Health Check.

    Inspects operating system configuration, USB permissions, installed
    serial/flashing drivers, and enumerates connected microcontrollers.

    Returns:
        A dictionary containing environment details, hardware availability,
        and diagnostic status.
    """
    import os
    import platform
    import sys

    status: Dict[str, Any] = {
        "product": "μFlet",
        "version": __version__,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "executable": sys.executable,
        },
        "dependencies": {},
        "permissions": {},
        "devices": {
            "serial_ports": [],
            "uf2_drives": [],
        },
        "healthy": True,
        "warnings": [],
    }

    # 1. Dependency checks
    try:
        import serial

        status["dependencies"]["pyserial"] = getattr(serial, "__version__", "installed")
    except ImportError:
        status["dependencies"]["pyserial"] = None
        status["warnings"].append(
            "Missing 'pyserial'. Install with `pip install flet[hardware]`"
        )
        status["healthy"] = False

    try:
        import serial_asyncio

        status["dependencies"]["serial_asyncio"] = getattr(
            serial_asyncio, "__version__", "installed"
        )
    except ImportError:
        status["dependencies"]["serial_asyncio"] = None
        status["warnings"].append(
            "Missing 'pyserial-asyncio'. Install with `pip install flet[hardware]`"
        )
        status["healthy"] = False

    try:
        import esptool

        status["dependencies"]["esptool"] = getattr(esptool, "__version__", "installed")
    except ImportError:
        status["dependencies"]["esptool"] = None
        status["warnings"].append(
            "Missing 'esptool'. ESP32 flashing will require CLI fallback."
        )

    # 2. Permission checks (Linux specific)
    if platform.system() == "Linux":
        try:
            import grp

            user_groups = [
                g.gr_name for g in grp.getgrall() if os.getlogin() in g.gr_mem
            ]
            status["permissions"]["user_groups"] = user_groups
            if "dialout" not in user_groups and "uucp" not in user_groups:
                status["warnings"].append(
                    "User may lack serial port permissions. Add user to dialout group: `sudo usermod -a -G dialout $USER`"
                )
        except Exception:
            status["permissions"]["user_groups"] = "unknown"

    # 3. Hardware scan
    try:
        ports = list_serial_ports()
        status["devices"]["serial_ports"] = [
            {
                "device": p.device,
                "description": p.description,
                "manufacturer": p.manufacturer,
                "vid": f"0x{p.vid:04X}" if p.vid else None,
                "pid": f"0x{p.pid:04X}" if p.pid else None,
                "is_esp32": p.is_esp32(),
                "is_rp2040": p.is_rp2040(),
            }
            for p in ports
        ]
    except Exception as e:
        status["devices"]["serial_ports_error"] = str(e)

    try:
        drives = detect_uf2_drives()
        status["devices"]["uf2_drives"] = [str(d) for d in drives]
    except Exception as e:
        status["devices"]["uf2_drives_error"] = str(e)

    return status
