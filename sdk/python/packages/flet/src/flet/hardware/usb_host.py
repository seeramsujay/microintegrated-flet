from typing import TYPE_CHECKING, Any, Optional

from flet.hardware.transport import Transport, TransportError

if TYPE_CHECKING:
    from flet.controls.services.usb_serial import UsbSerial

__all__ = ["UsbHostTransport"]


class UsbHostTransport(Transport):
    """
    USB Host / OTG serial link on a mobile client (Android), driven through the
    [`UsbSerial`][flet.UsbSerial] service.

    The service must be part of the page (e.g. `page.services.append(usb)`) before
    the transport is opened.
    """

    scheme = "usb"

    def __init__(
        self,
        service: "UsbSerial",
        port_name: Optional[str] = None,
        baudrate: int = 115200,
        data_bits: int = 8,
        stop_bits: float = 1,
        parity: str = "none",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.service = service
        self.port_name = port_name
        self.baudrate = int(baudrate)
        self.data_bits = data_bits
        self.stop_bits = stop_bits
        self.parity = parity
        self._prev_on_data: Any = None
        self._prev_on_detached: Any = None

    @property
    def description(self) -> str:
        return f"usb://{self.port_name or 'auto'}@{self.baudrate}"

    async def _open(self) -> None:
        self._prev_on_data = self.service.on_data
        self._prev_on_detached = self.service.on_device_detached

        def _on_data(e):
            self._feed_data(e.raw_data)
            if self._prev_on_data:
                return self._prev_on_data(e)

        def _on_detached(e):
            if not self.port_name or e.device_name == self.port_name:
                self._connection_lost()
            if self._prev_on_detached:
                return self._prev_on_detached(e)

        self.service.on_data = _on_data
        self.service.on_device_detached = _on_detached

        ok = await self.service.open_port(
            port_name=self.port_name,
            baud_rate=self.baudrate,
            data_bits=self.data_bits,
            stop_bits=self.stop_bits,
            parity=self.parity,
        )
        if not ok:
            self._restore_handlers()
            raise TransportError(
                f"Cannot open {self.description}. Check that a USB serial device is "
                "attached and that USB permission was granted."
            )

    def _restore_handlers(self) -> None:
        self.service.on_data = self._prev_on_data
        self.service.on_device_detached = self._prev_on_detached

    async def _write(self, data: bytes) -> int:
        return await self.service.write_data(data)

    async def set_dtr(self, active: bool = True) -> None:
        await self.service.set_dtr(active)

    async def set_rts(self, active: bool = True) -> None:
        await self.service.set_rts(active)

    async def _close(self) -> None:
        self._restore_handlers()
        try:
            await self.service.close_port()
        except Exception as e:
            raise TransportError(str(e)) from e
