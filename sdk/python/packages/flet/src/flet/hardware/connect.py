import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from flet.hardware.bluetooth import BleTransport, RfcommTransport
from flet.hardware.mqtt import MqttTransport
from flet.hardware.network import TcpTransport, UdpTransport, WebSocketTransport
from flet.hardware.serial import AsyncSerial
from flet.hardware.transport import Transport

__all__ = ["SUPPORTED_SCHEMES", "connect", "transport_from_url"]

SUPPORTED_SCHEMES = {
    "serial": "USB / UART serial port (also Bluetooth SPP ports like /dev/rfcomm0)",
    "tcp": "Raw TCP socket over WiFi / Ethernet",
    "telnet": "Raw TCP socket, default port 23",
    "tls": "TCP socket with TLS",
    "udp": "UDP datagrams over WiFi / Ethernet",
    "ws": "WebSocket",
    "wss": "Secure WebSocket",
    "mqtt": "MQTT broker (rx/tx topics)",
    "mqtts": "MQTT broker over TLS",
    "ble": "Bluetooth Low Energy UART (Nordic UART, HM-10, ...)",
    "rfcomm": "Bluetooth Classic SPP (HC-05, ESP32 BluetoothSerial)",
    "bt": "Alias for rfcomm",
}

_WINDOWS_PORT = re.compile(r"^COM\d+$", re.IGNORECASE)

# Short query-parameter aliases accepted in URLs.
_ALIASES = {
    "baud": "baudrate",
    "rx": "rx_topic",
    "tx": "tx_topic",
    "service": "service_uuid",
    "rx_char": "rx_char_uuid",
    "tx_char": "tx_char_uuid",
    "timeout": "connect_timeout",
}

# Parameters that are always kept as strings, even if they look numeric.
_STRING_PARAMS = {
    "rx_topic",
    "tx_topic",
    "client_id",
    "username",
    "password",
    "service_uuid",
    "rx_char_uuid",
    "tx_char_uuid",
    "port_name",
}


def _coerce(value: str) -> Any:
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value


def _query(query: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        key = _ALIASES.get(key, key)
        if key not in _STRING_PARAMS:
            value = _coerce(value)
        if key == "rx_topic" and key in params:
            existing = params[key]
            params[key] = (existing if isinstance(existing, list) else [existing]) + [
                value
            ]
        else:
            params[key] = value
    return params


def transport_from_url(url: str, **kwargs: Any) -> Transport:
    """
    Create an (unopened) transport from a connection URL.

    Examples:
        - `/dev/ttyUSB0`, `COM3`, `serial:///dev/ttyACM0?baudrate=9600`
        - `tcp://192.168.4.1:23`, `telnet://esp32.local`
        - `udp://192.168.1.50:4210?local_port=4210`
        - `ws://esp32.local/ws`
        - `mqtt://user:pass@broker.hivemq.com:1883?rx=dev1/out&tx=dev1/in`
        - `ble://AA:BB:CC:DD:EE:FF`, `ble://MyESP32`
        - `rfcomm://00:11:22:33:44:55/1`, `bt://HC-05-address`

    Query parameters (and `kwargs`, which take precedence) are passed to the
    transport constructor.
    """
    url = url.strip()
    if "://" not in url:
        if (
            url.startswith("/")
            or _WINDOWS_PORT.match(url)
            or url.lower() == "webserial"
        ):
            return AsyncSerial(port=url, **kwargs)
        raise ValueError(
            f"Cannot determine transport for '{url}'. Use a URL such as "
            "serial:///dev/ttyUSB0, tcp://host:port, mqtt://broker or ble://address."
        )

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    params = {**_query(parts.query), **kwargs}

    if scheme == "serial":
        port = unquote(parts.netloc + parts.path)
        if not port:
            raise ValueError("serial:// URL must include a port, e.g. serial://COM3")
        return AsyncSerial(port=port, **params)

    if scheme in ("tcp", "telnet", "tls"):
        if not parts.hostname:
            raise ValueError(f"{scheme}:// URL must include a host.")
        if scheme == "tls":
            params.setdefault("ssl_context", True)
        return TcpTransport(host=parts.hostname, port=parts.port or 23, **params)

    if scheme == "udp":
        return UdpTransport(host=parts.hostname, port=parts.port, **params)

    if scheme in ("ws", "wss"):
        return WebSocketTransport(url=url.split("?", 1)[0], **params)

    if scheme in ("mqtt", "mqtts"):
        if not parts.hostname:
            raise ValueError(f"{scheme}:// URL must include a broker host.")
        if parts.username:
            params.setdefault("username", unquote(parts.username))
        if parts.password:
            params.setdefault("password", unquote(parts.password))
        if scheme == "mqtts":
            params.setdefault("tls", True)
        return MqttTransport(host=parts.hostname, port=parts.port, **params)

    if scheme == "ble":
        device = unquote(parts.netloc + parts.path.rstrip("/"))
        if not device:
            raise ValueError("ble:// URL must include a device address or name.")
        return BleTransport(device=device, **params)

    if scheme in ("rfcomm", "bt"):
        address = unquote(parts.netloc)
        channel = parts.path.strip("/")
        if channel:
            params.setdefault("channel", int(channel))
        return RfcommTransport(address=address, **params)

    raise ValueError(
        f"Unsupported transport scheme '{scheme}'. "
        f"Supported: {', '.join(sorted(SUPPORTED_SCHEMES))}."
    )


async def connect(url: str, **kwargs: Any) -> Transport:
    """Create a transport from `url` (see `transport_from_url()`) and open it."""
    transport = transport_from_url(url, **kwargs)
    await transport.open()
    return transport
