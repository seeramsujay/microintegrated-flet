import base64
from dataclasses import dataclass
from typing import Any, Optional, Union

from flet.controls.base_control import control
from flet.controls.control_event import Event, EventHandler
from flet.controls.services.service import Service

__all__ = ["UsbSerial", "UsbSerialDataEvent", "UsbSerialDeviceEvent"]


@dataclass(kw_only=True)
class UsbSerialDataEvent(Event["UsbSerial"]):
    """Event fired when raw serial data is received from USB Host."""

    raw_data: bytes = b""
    """Received raw data bytes."""


@dataclass(kw_only=True)
class UsbSerialDeviceEvent(Event["UsbSerial"]):
    """Event fired when a USB device is attached or detached."""

    device_name: str = ""
    vendor_id: Optional[int] = None
    product_id: Optional[int] = None


@control("UsbSerial")
class UsbSerial(Service):
    """
    Service providing USB Host / OTG serial communication on mobile and embedded clients.
    """

    on_data: Optional[EventHandler[UsbSerialDataEvent]] = None
    """Called when serial data is received from the connected USB device."""

    on_device_attached: Optional[EventHandler[UsbSerialDeviceEvent]] = None
    """Called when a USB serial device is plugged into the device."""

    on_device_detached: Optional[EventHandler[UsbSerialDeviceEvent]] = None
    """Called when a USB serial device is disconnected."""

    async def list_ports(self) -> list[dict[str, Any]]:
        """
        List available USB serial devices detected by the client operating system.
        """
        result = await self._invoke_method("list_ports")
        return result or []

    async def open_port(
        self,
        port_name: Optional[str] = None,
        baud_rate: int = 115200,
        data_bits: int = 8,
        stop_bits: Union[int, float] = 1,
        parity: str = "none",
    ) -> bool:
        """
        Open connection to a USB serial device.
        """
        args = {
            "port_name": port_name,
            "baud_rate": baud_rate,
            "data_bits": data_bits,
            "stop_bits": stop_bits,
            "parity": parity,
        }
        return bool(await self._invoke_method("open_port", args))

    async def close_port(self) -> bool:
        """
        Close active USB serial connection.
        """
        return bool(await self._invoke_method("close_port"))

    async def write_data(self, data: Union[bytes, bytearray, str]) -> int:
        """
        Transmit data over the USB serial interface.
        """
        if isinstance(data, str):
            raw_bytes = data.encode("utf-8")
        else:
            raw_bytes = bytes(data)

        # Base64 encode for json transport across platform bridge
        b64_str = base64.b64encode(raw_bytes).decode("ascii")
        result = await self._invoke_method("write_data", {"data": b64_str})
        return int(result) if result is not None else len(raw_bytes)

    async def set_dtr(self, active: bool) -> None:
        """Set Data Terminal Ready (DTR) pin state."""
        await self._invoke_method("set_dtr", {"active": active})

    async def set_rts(self, active: bool) -> None:
        """Set Request To Send (RTS) pin state."""
        await self._invoke_method("set_rts", {"active": active})
