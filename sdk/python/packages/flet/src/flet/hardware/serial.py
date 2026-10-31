import asyncio
import contextlib
import enum
import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Optional

from flet.hardware.transport import Transport, TransportError

__all__ = [
    "AsyncSerial",
    "Parity",
    "SerialPortInfo",
    "StopBits",
    "create_serial_connection",
    "list_serial_ports",
]


class Parity(str, enum.Enum):
    NONE = "N"
    EVEN = "E"
    ODD = "O"
    MARK = "M"
    SPACE = "S"


class StopBits(enum.Enum):
    ONE = 1
    ONE_POINT_FIVE = 1.5
    TWO = 2


# Known USB VID/PIDs for microcontroller development boards
ESP32_VID_PIDS = {
    (0x10C4, 0xEA60),  # CP2102 / CP2104 (Silicon Labs)
    (0x1A86, 0x7523),  # CH340 / CH341 (WCH)
    (0x1A86, 0x55D4),  # CH9102 (WCH)
    (0x0403, 0x6001),  # FT232R (FTDI)
    (0x0403, 0x6010),  # FT2232H (Dual UART/JTAG)
    (0x303A, 0x1001),  # ESP32-S2 / ESP32-S3 USB-CDC
    (0x303A, 0x1002),  # ESP32-C3 USB-Serial/JTAG
    (0x303A, 0x0002),  # ESP32-C3 CDC
}

RP2040_VID_PIDS = {
    (0x2E8A, 0x000A),  # Raspberry Pi Pico CDC serial
    (0x2E8A, 0x0003),  # Raspberry Pi Pico Bootloader (UF2)
    (0x2E8A, 0x0005),  # Raspberry Pi Pico MicroPython/CircuitPython
    (0x2E8A, 0x0009),  # Raspberry Pi Debug Probe
}


@dataclass
class SerialPortInfo:
    """Detailed metadata for an enumerated serial / UART port."""

    device: str
    name: Optional[str] = None
    description: Optional[str] = None
    hwid: Optional[str] = None
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    interface: Optional[str] = None

    def is_esp32(self) -> bool:
        """Heuristic check for ESP32 / ESP8266 development boards."""
        if self.vid and self.pid and (self.vid, self.pid) in ESP32_VID_PIDS:
            return True
        desc = (self.description or "").lower()
        prod = (self.product or "").lower()
        return (
            "esp32" in desc
            or "esp8266" in desc
            or "cp210" in desc
            or "ch340" in desc
            or "esp32" in prod
        )

    def is_rp2040(self) -> bool:
        """Heuristic check for Raspberry Pi Pico / RP2040 microcontrollers."""
        if self.vid and self.pid and (self.vid, self.pid) in RP2040_VID_PIDS:
            return True
        desc = (self.description or "").lower()
        prod = (self.product or "").lower()
        mfg = (self.manufacturer or "").lower()
        return (
            "rp2040" in desc
            or "pico" in desc
            or "raspberry pi" in mfg
            or "rp2040" in prod
        )

    def is_microcontroller(self) -> bool:
        """Return True if this device appears to be an MCU or dev board."""
        return self.is_esp32() or self.is_rp2040()

    def display_name(self) -> str:
        """User-friendly display string for dropdowns and terminal listings."""
        parts = [self.device]
        extra = []
        if self.is_esp32() and "esp" not in (self.description or "").lower():
            extra.append("ESP32")
        elif (
            self.is_rp2040()
            and "rp2040" not in (self.description or "").lower()
            and "pico" not in (self.description or "").lower()
        ):
            extra.append("Raspberry Pi Pico / RP2040")
        if self.description and self.description != "n/a":
            extra.append(self.description)
        if self.vid is not None and self.pid is not None:
            extra.append(f"[{self.vid:04X}:{self.pid:04X}]")
        if extra:
            parts.append(f"({' - '.join(extra)})")
        return " ".join(parts)


def _is_legacy_placeholder(port: Any) -> bool:
    """Linux 8250 `/dev/ttyS*` placeholders with no hardware behind them."""
    if getattr(port, "subsystem", None) == "serial-base":
        return True
    return port.device.startswith("/dev/ttyS") and (port.hwid or "n/a") == "n/a"


def list_serial_ports(include_legacy: bool = False) -> list[SerialPortInfo]:
    """
    Enumerate available serial ports across all supported platforms.

    Args:
        include_legacy: Also return Linux `/dev/ttyS*` placeholder ports that have
            no hardware attached (hidden by default).
    """
    ports: list[SerialPortInfo] = []

    # 1. Try Pyodide / WebSerial environment
    if sys.platform == "emscripten":
        try:
            import js  # type: ignore

            if hasattr(js, "navigator") and hasattr(js.navigator, "serial"):
                return [
                    SerialPortInfo(
                        device="WebSerial",
                        name="WebSerial Device",
                        description="Browser WebSerial Port",
                    )
                ]
        except Exception:
            pass

    # 2. Try pyserial if installed
    try:
        from serial.tools import list_ports as serial_tools_ports  # type: ignore

        for p in serial_tools_ports.comports():
            if not include_legacy and _is_legacy_placeholder(p):
                continue
            info = SerialPortInfo(
                device=p.device,
                name=p.name,
                description=p.description,
                hwid=p.hwid,
                vid=p.vid,
                pid=p.pid,
                serial_number=p.serial_number,
                location=p.location,
                manufacturer=p.manufacturer,
                product=p.product,
                interface=p.interface,
            )
            ports.append(info)
        return ports
    except ImportError:
        pass

    # 3. Fallback discovery on POSIX systems (Linux / macOS)
    system = platform.system()
    if system in ("Linux", "Darwin"):
        dev_dir = "/dev"
        if os.path.exists(dev_dir):
            for entry in os.listdir(dev_dir):
                if entry.startswith(
                    (
                        "ttyUSB",
                        "ttyACM",
                        "cu.usbserial",
                        "cu.usbmodem",
                        "cu.SLAB_USBtoUART",
                        "cu.wchusbserial",
                    )
                ):
                    full_path = os.path.join(dev_dir, entry)
                    ports.append(
                        SerialPortInfo(
                            device=full_path,
                            name=entry,
                            description=f"Serial Device ({entry})",
                        )
                    )

    return ports


class AsyncSerial(Transport):
    """
    Asynchronous serial port interface supporting Desktop OS streams,
    Browser/Pyodide WebSerial API, and Bluetooth Classic SPP ports exposed by
    the OS (`/dev/rfcomm0`, `/dev/cu.<device>`, `COMx`).
    """

    scheme = "serial"

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        bytesize: int = 8,
        parity: Parity = Parity.NONE,
        stopbits: StopBits = StopBits.ONE,
        timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        xonxoff: bool = False,
        rtscts: bool = False,
        dsrdtr: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.port = port
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = Parity(parity)
        self.stopbits = StopBits(stopbits)
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.dsrdtr = dsrdtr

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._serial_sync: Any = None
        self._web_reader: Any = None

    @property
    def description(self) -> str:
        return f"serial://{self.port}@{self.baudrate}"

    @property
    def serial(self) -> Any:
        """The underlying `serial.Serial` object (or WebSerial port), if any."""
        if self._writer is not None:
            return getattr(self._writer.transport, "serial", None)
        return self._serial_sync

    async def _open(self) -> None:
        # WebSerial / Pyodide mode
        if sys.platform == "emscripten" or self.port.lower() == "webserial":
            await self._open_webserial()
            return

        # Native Desktop mode
        try:
            import serial_asyncio  # type: ignore
        except ImportError:
            serial_asyncio = None

        if serial_asyncio is not None:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity.value,
                stopbits=self.stopbits.value,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
                xonxoff=self.xonxoff,
                rtscts=self.rtscts,
                dsrdtr=self.dsrdtr,
            )
            self._start_task(self._read_loop_asyncio())
            return

        # Fallback to threaded sync pyserial
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise TransportError(
                "pyserial or pyserial-asyncio is required for desktop serial "
                "communication. Install with `pip install 'flet[hardware]'` or "
                "`pip install pyserial pyserial-asyncio`."
            ) from e

        self._serial_sync = await asyncio.to_thread(
            serial.Serial,
            port=self.port,
            baudrate=self.baudrate,
            bytesize=self.bytesize,
            parity=self.parity.value,
            stopbits=self.stopbits.value,
            timeout=0.1,
            write_timeout=self.write_timeout,
            xonxoff=self.xonxoff,
            rtscts=self.rtscts,
            dsrdtr=self.dsrdtr,
        )
        self._start_task(self._read_loop_threaded())

    async def _open_webserial(self) -> None:
        """Initialize connection using browser WebSerial API."""
        try:
            import js  # type: ignore
            from pyodide.ffi import to_js  # type: ignore

            options = to_js(
                {"baudRate": self.baudrate}, dict_converter=js.Object.fromEntries
            )
            port_obj = await js.navigator.serial.requestPort()
            await port_obj.open(options)
            self._serial_sync = port_obj
            self._start_task(self._read_loop_webserial())
        except Exception as e:
            raise TransportError(f"Failed to open WebSerial port: {e}") from e

    async def _read_loop_asyncio(self) -> None:
        """Background coroutine reading from serial_asyncio StreamReader."""
        assert self._reader is not None
        try:
            while not self._closing:
                data = await self._reader.read(1024)
                if not data:
                    break
                self._feed_data(data)
        except asyncio.CancelledError:
            return
        except Exception as e:
            self._connection_lost(e)
            return
        self._connection_lost()

    async def _read_loop_threaded(self) -> None:
        """Background coroutine reading from standard pyserial in worker thread."""
        ser = self._serial_sync
        assert ser is not None
        try:
            while not self._closing:
                data = await asyncio.to_thread(ser.read, 1024)
                if data:
                    self._feed_data(data)
        except asyncio.CancelledError:
            return
        except Exception as e:
            self._connection_lost(e)

    async def _read_loop_webserial(self) -> None:
        """Background coroutine reading from WebSerial readable stream."""
        assert self._serial_sync is not None
        try:
            self._web_reader = self._serial_sync.readable.getReader()
            while not self._closing:
                res = await self._web_reader.read()
                if res.done:
                    break
                self._feed_data(bytes(res.value.to_py()))
        except asyncio.CancelledError:
            return
        except Exception as e:
            self._connection_lost(e)
            return
        self._connection_lost()

    async def _write(self, data: bytes) -> int:
        if self._writer is not None:
            self._writer.write(data)
            await self._writer.drain()
            return len(data)

        if self._serial_sync is not None and hasattr(self._serial_sync, "writable"):
            # WebSerial write
            from pyodide.ffi import to_js  # type: ignore

            writer = self._serial_sync.writable.getWriter()
            try:
                await writer.write(to_js(data))
            finally:
                writer.releaseLock()
            return len(data)

        if self._serial_sync is not None:
            # Pyserial threaded write
            return await asyncio.to_thread(self._serial_sync.write, data)

        raise TransportError("Serial port is not open.")

    async def flush(self) -> None:
        """Flush write buffers."""
        if self._writer is not None:
            await self._writer.drain()
        elif self._serial_sync is not None and hasattr(self._serial_sync, "flush"):
            await asyncio.to_thread(self._serial_sync.flush)

    async def set_dtr(self, active: bool = True) -> None:
        """Set Data Terminal Ready (DTR) line."""
        ser = self.serial
        if ser is None:
            return
        if hasattr(ser, "setSignals"):  # WebSerial
            await ser.setSignals(to_js_signals(dataTerminalReady=active))
        elif hasattr(ser, "dtr"):
            ser.dtr = active

    async def set_rts(self, active: bool = True) -> None:
        """Set Request To Send (RTS) line."""
        ser = self.serial
        if ser is None:
            return
        if hasattr(ser, "setSignals"):  # WebSerial
            await ser.setSignals(to_js_signals(requestToSend=active))
        elif hasattr(ser, "rts"):
            ser.rts = active

    async def reset_device(self, delay: float = 0.1) -> None:
        """Pulse DTR/RTS to reset a typical ESP32 / Arduino board into run mode."""
        await self.set_dtr(False)
        await self.set_rts(True)
        await asyncio.sleep(delay)
        await self.set_rts(False)

    async def _close(self) -> None:
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

        if self._serial_sync is not None:
            ser = self._serial_sync
            self._serial_sync = None
            if hasattr(ser, "readable"):
                # WebSerial: release the stream lock before closing the port.
                if self._web_reader is not None:
                    with contextlib.suppress(Exception):
                        await self._web_reader.cancel()
                    with contextlib.suppress(Exception):
                        self._web_reader.releaseLock()
                    self._web_reader = None
                with contextlib.suppress(Exception):
                    await ser.close()
            else:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(ser.close)


def to_js_signals(**signals: bool) -> Any:
    """Convert keyword signals into a JS object for WebSerial `setSignals()`."""
    import js  # type: ignore
    from pyodide.ffi import to_js  # type: ignore

    return to_js(signals, dict_converter=js.Object.fromEntries)


async def create_serial_connection(
    port: str,
    baudrate: int = 115200,
    **kwargs: Any,
) -> AsyncSerial:
    """Convenience helper to create and open an AsyncSerial instance."""
    ser = AsyncSerial(port=port, baudrate=baudrate, **kwargs)
    await ser.open()
    return ser
