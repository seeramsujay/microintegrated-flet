import asyncio
import contextlib
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Optional

from flet.hardware.transport import Transport, TransportError

__all__ = [
    "BLE_UART_PROFILES",
    "BleDeviceInfo",
    "BleTransport",
    "RfcommTransport",
    "is_rfcomm_supported",
    "scan_ble_devices",
]

# Well-known "BLE serial" GATT profiles as (service, notify/RX char, write/TX char).
BLE_UART_PROFILES: dict[str, tuple[str, str, str]] = {
    # Nordic UART Service - ESP32 BLE UART examples, MicroPython `ble_uart`,
    # CircuitPython `UARTService`, Adafruit Bluefruit, nRF Toolbox.
    "nus": (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    ),
    # HM-10 / HM-11 / HC-08 / AT-09 / JDY-08 modules (single characteristic).
    "hm10": (
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe1-0000-1000-8000-00805f9b34fb",
        "0000ffe1-0000-1000-8000-00805f9b34fb",
    ),
    # Microchip / ISSC transparent UART (RN4870/71, BM70/71).
    "microchip": (
        "49535343-fe7d-4ae5-8fa9-9fafd205e455",
        "49535343-1e4d-4bd9-ba61-23c647249616",
        "49535343-8841-43f4-a8d4-ecbe34729bb3",
    ),
}

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_UUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-([0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$")


def _is_address(value: str) -> bool:
    # MAC on Linux/Windows; CoreBluetooth UUID on macOS.
    return bool(_MAC_RE.match(value) or _UUID_RE.match(value))


def _import_bleak():
    try:
        import bleak  # type: ignore
    except ImportError as e:
        raise TransportError(
            "Bluetooth LE requires `bleak`. "
            "Install with `pip install 'flet[hardware]'`."
        ) from e
    return bleak


@dataclass
class BleDeviceInfo:
    """A Bluetooth LE device found by `scan_ble_devices()`."""

    address: str
    name: Optional[str] = None
    rssi: Optional[int] = None
    service_uuids: list[str] = field(default_factory=list)

    @property
    def uart_profile(self) -> Optional[str]:
        """Name of the advertised BLE UART profile, if any (`nus`, `hm10`, ...)."""
        uuids = {u.lower() for u in self.service_uuids}
        for name, (service, _, _) in BLE_UART_PROFILES.items():
            if service in uuids:
                return name
        return None

    def display_name(self) -> str:
        parts = [self.name or "(unnamed)", self.address]
        if self.rssi is not None:
            parts.append(f"{self.rssi} dBm")
        if self.uart_profile:
            parts.append(f"UART:{self.uart_profile}")
        return " | ".join(parts)


async def scan_ble_devices(
    timeout: float = 5.0, uart_only: bool = False
) -> list[BleDeviceInfo]:
    """
    Scan for nearby Bluetooth LE devices.

    Args:
        timeout: Scan duration in seconds.
        uart_only: Only return devices advertising a known BLE UART service.
    """
    bleak = _import_bleak()
    found = await bleak.BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = []
    for device, adv in found.values():
        info = BleDeviceInfo(
            address=device.address,
            name=adv.local_name or device.name,
            rssi=adv.rssi,
            service_uuids=list(adv.service_uuids or []),
        )
        if uart_only and not info.uart_profile:
            continue
        devices.append(info)
    devices.sort(key=lambda d: d.rssi if d.rssi is not None else -999, reverse=True)
    return devices


class BleTransport(Transport):
    """
    Bluetooth Low Energy "serial" link - the protocol used by phone apps such as
    "Serial Bluetooth Terminal", nRF Toolbox/UART and LightBlue.

    `device` is a MAC address (Linux/Windows), a CoreBluetooth UUID (macOS) or an
    advertised device name. The UART characteristics are auto-detected (Nordic
    UART, HM-10, Microchip, then any notify + write characteristic pair) unless
    given explicitly. Requires the `bleak` package.
    """

    scheme = "ble"

    def __init__(
        self,
        device: str,
        service_uuid: Optional[str] = None,
        rx_char_uuid: Optional[str] = None,
        tx_char_uuid: Optional[str] = None,
        scan_timeout: float = 10.0,
        write_with_response: Optional[bool] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.device = device
        self.service_uuid = service_uuid.lower() if service_uuid else None
        self.rx_char_uuid = rx_char_uuid.lower() if rx_char_uuid else None
        """Characteristic the device notifies on (data received by this side)."""
        self.tx_char_uuid = tx_char_uuid.lower() if tx_char_uuid else None
        """Characteristic this side writes to (data sent to the device)."""
        self.scan_timeout = scan_timeout
        self.write_with_response = write_with_response
        self._client: Any = None
        self._rx_char: Any = None
        self._tx_char: Any = None
        self._write_lock = asyncio.Lock()

    @property
    def description(self) -> str:
        return f"ble://{self.device}"

    @property
    def mtu(self) -> int:
        """Maximum payload size of a single write."""
        char = self._tx_char
        size = getattr(char, "max_write_without_response_size", 0) if char else 0
        if not size and self._client is not None:
            size = getattr(self._client, "mtu_size", 23) - 3
        return max(int(size or 20), 20)

    async def _open(self) -> None:
        bleak = _import_bleak()

        target: Any = self.device
        if not _is_address(self.device):
            target = await bleak.BleakScanner.find_device_by_name(
                self.device, timeout=self.scan_timeout
            )
            if target is None:
                raise TransportError(f"BLE device named '{self.device}' not found.")

        self._client = bleak.BleakClient(
            target,
            disconnected_callback=lambda _client: self._connection_lost(),
            timeout=self.scan_timeout,
        )
        try:
            await self._client.connect()
        except Exception as e:
            self._client = None
            raise TransportError(f"Cannot connect to {self.description}: {e}") from e

        try:
            self._rx_char, self._tx_char = self._resolve_characteristics()
            if self._rx_char is not None:
                await self._client.start_notify(self._rx_char, self._on_notify)
        except Exception:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            self._client = None
            raise

    def _resolve_characteristics(self):
        services = list(self._client.services)

        def find_char(uuid: Optional[str], service_uuid: Optional[str] = None):
            for service in services:
                if service_uuid and service.uuid.lower() != service_uuid:
                    continue
                for char in service.characteristics:
                    if char.uuid.lower() == uuid:
                        return char
            return None

        if self.rx_char_uuid or self.tx_char_uuid:
            rx = find_char(self.rx_char_uuid, self.service_uuid)
            tx = find_char(self.tx_char_uuid, self.service_uuid)
            if self.rx_char_uuid and rx is None:
                raise TransportError(f"Characteristic {self.rx_char_uuid} not found.")
            if self.tx_char_uuid and tx is None:
                raise TransportError(f"Characteristic {self.tx_char_uuid} not found.")
            return rx, tx

        for service_uuid, rx_uuid, tx_uuid in BLE_UART_PROFILES.values():
            if self.service_uuid and service_uuid != self.service_uuid:
                continue
            rx = find_char(rx_uuid, service_uuid)
            tx = find_char(tx_uuid, service_uuid)
            if rx is not None and tx is not None:
                return rx, tx

        # Generic fallback: first notify/indicate + first writable characteristic.
        rx = tx = None
        for service in services:
            if self.service_uuid and service.uuid.lower() != self.service_uuid:
                continue
            for char in service.characteristics:
                props = set(char.properties)
                if rx is None and props & {"notify", "indicate"}:
                    rx = char
                if tx is None and props & {"write", "write-without-response"}:
                    tx = char
        if rx is None and tx is None:
            raise TransportError(
                f"No UART-like characteristics found on {self.description}. "
                "Pass rx_char_uuid / tx_char_uuid explicitly."
            )
        return rx, tx

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        self._feed_data(data)

    async def _write(self, data: bytes) -> int:
        if self._tx_char is None:
            raise TransportError(f"{self.description} has no writable characteristic.")
        response = self.write_with_response
        if response is None:
            response = "write-without-response" not in self._tx_char.properties
        chunk = self.mtu
        async with self._write_lock:
            for i in range(0, len(data), chunk):
                await self._client.write_gatt_char(
                    self._tx_char, data[i : i + chunk], response=response
                )
        return len(data)

    async def _close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            if self._rx_char is not None:
                with contextlib.suppress(Exception):
                    await client.stop_notify(self._rx_char)
            with contextlib.suppress(Exception):
                await client.disconnect()
        self._rx_char = self._tx_char = None


def is_rfcomm_supported() -> bool:
    """Whether this Python build can open Bluetooth Classic RFCOMM sockets."""
    return hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


class RfcommTransport(Transport):
    """
    Bluetooth Classic Serial Port Profile (SPP) link over an RFCOMM socket -
    HC-05/HC-06 modules, ESP32 `BluetoothSerial`, and other "Bluetooth terminal"
    devices. The device must already be paired with this computer.

    Supported natively on Linux and Windows. On macOS (or as an alternative),
    open the OS-provided serial port with `AsyncSerial` instead:
    `/dev/rfcomm0` (after `rfcomm bind`), `/dev/cu.<device-name>` or `COMx`.
    """

    scheme = "rfcomm"

    def __init__(
        self,
        address: str,
        channel: int = 1,
        connect_timeout: float = 15.0,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.address = address.replace("-", ":").upper()
        self.channel = int(channel)
        self.connect_timeout = connect_timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    @property
    def description(self) -> str:
        return f"rfcomm://{self.address}/{self.channel}"

    async def _open(self) -> None:
        if not is_rfcomm_supported():
            raise TransportError(
                "Bluetooth RFCOMM sockets are not supported by this Python build "
                "(macOS has none). Pair the device and open its serial port with "
                "AsyncSerial instead, e.g. serial:///dev/cu.<device-name>."
            )
        sock = socket.socket(
            socket.AF_BLUETOOTH,  # type: ignore[attr-defined]
            socket.SOCK_STREAM,
            socket.BTPROTO_RFCOMM,  # type: ignore[attr-defined]
        )
        try:
            sock.settimeout(self.connect_timeout)
            await asyncio.to_thread(sock.connect, (self.address, self.channel))
            sock.setblocking(False)
            self._reader, self._writer = await asyncio.open_connection(sock=sock)
        except Exception as e:
            sock.close()
            raise TransportError(f"Cannot connect to {self.description}: {e}") from e
        self._start_task(self._read_loop())

    async def _read_loop(self) -> None:
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

    async def _write(self, data: bytes) -> int:
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()
        return len(data)

    async def _close(self) -> None:
        if self._writer is not None:
            writer, self._writer, self._reader = self._writer, None, None
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), 2.0)
