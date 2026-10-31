"""
μFlet (uflet) - The Official Microcontroller & Embedded Hardware Toolkit for Flet.

Provides non-blocking device communication over USB serial, Bluetooth (LE and
Classic SPP), WiFi (TCP / UDP / WebSocket) and MQTT, firmware flashing engines
for ESP32 and RP2040 microcontrollers, and hardware-reactive UI controls.

Usage:
    import uflet as uf

    # Discover devices
    ports = uf.list_serial_ports()

    # Async serial stream
    async with uf.AsyncSerial(port="/dev/ttyUSB0", baudrate=115200) as ser:
        await ser.write_line("PING")
        response = await ser.read_line()

    # Any transport, by URL
    async with await uf.connect("mqtt://broker.local?rx=dev/out&tx=dev/in") as link:
        await link.write_line("PING")
        print(await link.read_line())

    # Flash firmware
    await uf.flash_firmware(
        firmware="firmware.bin",
        port="/dev/ttyUSB0",
        chip="esp32s3",
    )
"""

from typing import Any, Dict

# Controls are imported directly so `uf.SerialConsole(...)` works without `ft.`
from flet.controls.hardware.device_selector import DeviceSelector
from flet.controls.hardware.flash_progress import FlashProgress
from flet.controls.hardware.serial_console import SerialConsole
from flet.controls.services.usb_serial import (
    UsbSerial,
    UsbSerialDataEvent,
    UsbSerialDeviceEvent,
)
from flet.hardware.bluetooth import (
    BleDeviceInfo,
    BleTransport,
    RfcommTransport,
    is_rfcomm_supported,
    scan_ble_devices,
)
from flet.hardware.connect import SUPPORTED_SCHEMES, connect, transport_from_url
from flet.hardware.flasher import (
    ESP32Flasher,
    FirmwareFlasher,
    FlashProgressUpdate,
    RP2040Flasher,
    detect_uf2_drives,
    flash_firmware,
)
from flet.hardware.mqtt import MqttTransport
from flet.hardware.network import TcpTransport, UdpTransport, WebSocketTransport
from flet.hardware.serial import (
    AsyncSerial,
    Parity,
    SerialPortInfo,
    StopBits,
    create_serial_connection,
    list_serial_ports,
)
from flet.hardware.transport import Transport, TransportError
from flet.hardware.usb_host import UsbHostTransport

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
    # Transports (USB, Bluetooth, WiFi, MQTT)
    "Transport",
    "TransportError",
    "TcpTransport",
    "UdpTransport",
    "WebSocketTransport",
    "MqttTransport",
    "BleTransport",
    "BleDeviceInfo",
    "RfcommTransport",
    "UsbHostTransport",
    "SUPPORTED_SCHEMES",
    "connect",
    "transport_from_url",
    "scan_ble_devices",
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
    import importlib
    import importlib.metadata
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

    # 1. Dependency checks: (module, pip name, purpose, required)
    deps = [
        ("serial", "pyserial", "USB / UART serial I/O", True),
        ("serial_asyncio", "pyserial-asyncio", "USB / UART serial I/O", True),
        ("esptool", "esptool", "ESP32 flashing", False),
        ("bleak", "bleak", "Bluetooth LE", False),
        ("aiomqtt", "aiomqtt", "MQTT", False),
        ("websockets", "websockets", "WebSocket", False),
    ]
    for module_name, pip_name, purpose, required in deps:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", None)
            if version is None:
                try:
                    version = importlib.metadata.version(pip_name)
                except importlib.metadata.PackageNotFoundError:
                    version = "installed"
            status["dependencies"][module_name] = version
        except ImportError:
            status["dependencies"][module_name] = None
            status["warnings"].append(
                f"Missing '{pip_name}' ({purpose}). "
                "Install with `pip install 'flet[hardware]'`"
            )
            if required:
                status["healthy"] = False

    status["transports"] = {
        "serial": status["dependencies"]["serial"] is not None,
        "ble": status["dependencies"]["bleak"] is not None,
        "rfcomm": is_rfcomm_supported(),
        "tcp": True,
        "udp": True,
        "websocket": status["dependencies"]["websockets"] is not None,
        "mqtt": status["dependencies"]["aiomqtt"] is not None,
    }

    # 2. Permission checks (Linux specific)
    if platform.system() == "Linux":
        try:
            import grp

            user_groups = sorted({grp.getgrgid(gid).gr_name for gid in os.getgroups()})
            status["permissions"]["user_groups"] = user_groups
            if "dialout" not in user_groups and "uucp" not in user_groups:
                status["warnings"].append(
                    "User may lack serial port permissions. Add user to dialout "
                    "group: `sudo usermod -a -G dialout $USER` (then log in again)"
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
