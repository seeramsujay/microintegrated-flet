import asyncio
import enum
import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

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


def list_serial_ports() -> list[SerialPortInfo]:
    """
    Enumerate available serial ports across all supported platforms.
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


class AsyncSerial:
    """
    Asynchronous serial port interface supporting Desktop OS streams,
    Browser/Pyodide WebSerial API, and Mobile USB-Host bridges.
    """

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
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.dsrdtr = dsrdtr

        self.is_open = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._serial_sync: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._read_task: Optional[asyncio.Task] = None
        self._buffer = bytearray()
        self._read_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Callbacks
        self.on_data: Optional[Callable[[bytes], Any]] = None
        self.on_line: Optional[Callable[[str], Any]] = None
        self.on_error: Optional[Callable[[Exception], Any]] = None
        self.on_disconnect: Optional[Callable[[], Any]] = None

    async def open(self) -> None:
        """Open asynchronous serial connection."""
        if self.is_open:
            return

        self._loop = asyncio.get_running_loop()

        # WebSerial / Pyodide mode
        if sys.platform == "emscripten" or self.port == "WebSerial":
            await self._open_webserial()
            self.is_open = True
            return

        # Native Desktop mode
        try:
            import serial_asyncio  # type: ignore

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
            self.is_open = True
            self._read_task = asyncio.create_task(self._read_loop_asyncio())
            return
        except ImportError:
            pass

        # Fallback to threaded sync pyserial
        try:
            import serial  # type: ignore

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
            self.is_open = True
            self._read_task = asyncio.create_task(self._read_loop_threaded())
            return
        except ImportError as e:
            raise RuntimeError(
                "pyserial or serial-asyncio is required for desktop serial communication. "
                "Install with `pip install flet[hardware]` or `pip install pyserial pyserial-asyncio`."
            ) from e

    async def _open_webserial(self) -> None:
        """Initialize connection using browser WebSerial API."""
        try:
            import js  # type: ignore
            from pyodide.ffi import to_js  # type: ignore

            options = to_js({"baudRate": self.baudrate})
            port_obj = await js.navigator.serial.requestPort()
            await port_obj.open(options)
            self._serial_sync = port_obj
            self._read_task = asyncio.create_task(self._read_loop_webserial())
        except Exception as e:
            raise RuntimeError(f"Failed to open WebSerial port: {e}") from e

    async def _read_loop_asyncio(self) -> None:
        """Background coroutine reading from serial_asyncio StreamReader."""
        assert self._reader is not None
        while self.is_open:
            try:
                data = await self._reader.read(1024)
                if not data:
                    if self._reader.at_eof():
                        break
                    await asyncio.sleep(0.01)
                    continue
                self._feed_data(data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
                break
        await self.close()

    async def _read_loop_threaded(self) -> None:
        """Background coroutine reading from standard pyserial in worker thread."""
        assert self._serial_sync is not None
        while self.is_open:
            try:
                data = await asyncio.to_thread(self._serial_sync.read, 1024)
                if data:
                    self._feed_data(data)
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
                break
        await self.close()

    async def _read_loop_webserial(self) -> None:
        """Background coroutine reading from WebSerial readable stream."""
        assert self._serial_sync is not None
        try:
            reader = self._serial_sync.readable.getReader()
            while self.is_open:
                res = await reader.read()
                if res.done:
                    break
                chunk = bytes(res.value)
                self._feed_data(chunk)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.on_error:
                self.on_error(e)
        finally:
            await self.close()

    def _feed_data(self, chunk: bytes) -> None:
        """Process incoming raw byte chunks and trigger handlers."""
        self._buffer.extend(chunk)
        self._read_queue.put_nowait(chunk)

        if self.on_data:
            try:
                self.on_data(chunk)
            except Exception as e:
                if self.on_error:
                    self.on_error(e)

        # Check for completed lines
        if self.on_line:
            while b"\n" in self._buffer:
                idx = self._buffer.index(b"\n")
                line_bytes = bytes(self._buffer[: idx + 1])
                del self._buffer[: idx + 1]
                try:
                    line_str = line_bytes.decode("utf-8", errors="replace")
                    self.on_line(line_str)
                except Exception as e:
                    if self.on_error:
                        self.on_error(e)

    def _on_incoming_bytes(self, chunk: bytes) -> None:
        """Alias for feeding incoming bytes directly (useful for tests and mocks)."""
        self._feed_data(chunk)

    async def read(self, n: int = -1) -> bytes:
        """Read up to n bytes asynchronously from the incoming stream."""
        if n == 0:
            return b""

        while len(self._buffer) == 0:
            if not self.is_open and self._read_queue.empty():
                return b""
            chunk = await self._read_queue.get()
            # Chunk was already added to _buffer in _feed_data

        if n < 0 or len(self._buffer) <= n:
            data = bytes(self._buffer)
            self._buffer.clear()
            return data

        data = bytes(self._buffer[:n])
        del self._buffer[:n]
        return data

    async def read_line(self) -> str:
        """Read a line (up to \n) asynchronously."""
        while b"\n" not in self._buffer:
            if not self.is_open and self._read_queue.empty():
                line = bytes(self._buffer).decode("utf-8", errors="replace")
                self._buffer.clear()
                return line
            await self._read_queue.get()

        idx = self._buffer.index(b"\n")
        line_bytes = bytes(self._buffer[: idx + 1])
        del self._buffer[: idx + 1]
        return line_bytes.decode("utf-8", errors="replace")

    async def read_until(self, expected: bytes = b"\n") -> bytes:
        """Read bytes until the expected sequence is found."""
        while expected not in self._buffer:
            if not self.is_open and self._read_queue.empty():
                data = bytes(self._buffer)
                self._buffer.clear()
                return data
            await self._read_queue.get()

        idx = self._buffer.index(expected) + len(expected)
        data = bytes(self._buffer[:idx])
        del self._buffer[:idx]
        return data

    async def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """Write bytes asynchronously to the serial port."""
        if not self.is_open:
            raise RuntimeError("Serial port is not open.")

        raw_data = bytes(data)

        if self._writer is not None:
            self._writer.write(raw_data)
            await self._writer.drain()
            return len(raw_data)

        if self._serial_sync is not None and hasattr(self._serial_sync, "write"):
            # Pyserial threaded write
            return await asyncio.to_thread(self._serial_sync.write, raw_data)

        if self._serial_sync is not None and hasattr(self._serial_sync, "writable"):
            # WebSerial write
            from pyodide.ffi import to_js  # type: ignore

            writer = self._serial_sync.writable.getWriter()
            js_arr = to_js(raw_data)
            await writer.write(js_arr)
            writer.releaseLock()
            return len(raw_data)

        return 0

    async def write_line(self, line: str, newline: str = "\r\n") -> int:
        """Helper to write a string line with newline appended."""
        return await self.write((line + newline).encode("utf-8"))

    async def flush(self) -> None:
        """Flush write buffers."""
        if self._writer is not None:
            await self._writer.drain()
        elif self._serial_sync is not None and hasattr(self._serial_sync, "flush"):
            await asyncio.to_thread(self._serial_sync.flush)

    async def set_dtr(self, active: bool = True) -> None:
        """Set Data Terminal Ready (DTR) line."""
        if self._serial_sync is not None and hasattr(self._serial_sync, "dtr"):
            self._serial_sync.dtr = active

    async def set_rts(self, active: bool = True) -> None:
        """Set Request To Send (RTS) line."""
        if self._serial_sync is not None and hasattr(self._serial_sync, "rts"):
            self._serial_sync.rts = active

    async def close(self) -> None:
        """Close serial connection and release all resources."""
        if not self.is_open:
            return
        self.is_open = False

        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass

        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        if self._serial_sync is not None:
            try:
                if hasattr(self._serial_sync, "close"):
                    await asyncio.to_thread(self._serial_sync.close)
            except Exception:
                pass
            self._serial_sync = None

        if self.on_disconnect:
            try:
                self.on_disconnect()
            except Exception:
                pass

    async def __aenter__(self) -> "AsyncSerial":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


async def create_serial_connection(
    port: str,
    baudrate: int = 115200,
    **kwargs: Any,
) -> AsyncSerial:
    """Convenience helper to create and open an AsyncSerial instance."""
    ser = AsyncSerial(port=port, baudrate=baudrate, **kwargs)
    await ser.open()
    return ser
