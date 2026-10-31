import asyncio
import contextlib
import ssl
from typing import Any, Optional, Union

from flet.hardware.transport import Transport, TransportError

__all__ = ["TcpTransport", "UdpTransport", "WebSocketTransport"]


class TcpTransport(Transport):
    """
    Raw TCP socket link, e.g. to an ESP32 running a WiFi telnet / serial bridge
    (`WiFiServer`), ESP-Link, ser2net or a Tasmota/ESPHome serial server.
    """

    scheme = "tcp"

    def __init__(
        self,
        host: str,
        port: int = 23,
        connect_timeout: float = 10.0,
        ssl_context: Union[ssl.SSLContext, bool, None] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.host = host
        self.port = int(port)
        self.connect_timeout = connect_timeout
        self.ssl_context = ssl_context
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    @property
    def description(self) -> str:
        return f"{'tls' if self.ssl_context else 'tcp'}://{self.host}:{self.port}"

    async def _open(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host, self.port, ssl=self.ssl_context or None
                ),
                self.connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise TransportError(f"Cannot connect to {self.description}: {e}") from e
        self._start_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while not self._closing:
                data = await self._reader.read(4096)
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

    async def flush(self) -> None:
        if self._writer is not None:
            await self._writer.drain()

    async def _close(self) -> None:
        if self._writer is not None:
            writer, self._writer, self._reader = self._writer, None, None
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), 2.0)


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, owner: "UdpTransport"):
        self.owner = owner

    def datagram_received(self, data: bytes, addr) -> None:
        self.owner.last_peer = addr
        self.owner._feed_data(data)

    def error_received(self, exc: Exception) -> None:
        self.owner._report_error(exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.owner._connection_lost(exc)


class UdpTransport(Transport):
    """
    UDP datagram link, e.g. to an ESP32 sending sensor telemetry over WiFi.

    Datagrams are sent to `host:port`. Incoming datagrams are accepted on
    `local_port` (an ephemeral port by default). With `host=None` the transport
    only listens, and replies go to the last peer that sent a datagram.
    """

    scheme = "udp"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        local_host: str = "0.0.0.0",
        local_port: int = 0,
        broadcast: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.host = host
        self.port = int(port) if port is not None else None
        self.local_host = local_host
        self.local_port = int(local_port)
        self.broadcast = broadcast
        self.last_peer: Optional[tuple] = None
        self._transport: Optional[asyncio.DatagramTransport] = None

    @property
    def description(self) -> str:
        if self.host:
            return f"udp://{self.host}:{self.port}"
        return f"udp://{self.local_host}:{self.local_port} (listen)"

    @property
    def local_address(self) -> Optional[tuple]:
        """The (host, port) this transport is bound to once open."""
        if self._transport is None:
            return None
        return self._transport.get_extra_info("sockname")

    async def _open(self) -> None:
        if self.host and self.port is None:
            raise TransportError("UDP transport requires a remote port.")
        loop = asyncio.get_running_loop()
        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _UdpProtocol(self),
                local_addr=(self.local_host, self.local_port),
                allow_broadcast=self.broadcast,
            )
        except OSError as e:
            raise TransportError(f"Cannot open {self.description}: {e}") from e

    async def _write(self, data: bytes) -> int:
        assert self._transport is not None
        if self.host:
            target = (self.host, self.port)
        elif self.last_peer:
            target = self.last_peer
        else:
            raise TransportError(
                "UDP transport has no remote host and no peer has sent data yet."
            )
        self._transport.sendto(data, target)
        return len(data)

    async def _close(self) -> None:
        if self._transport is not None:
            transport, self._transport = self._transport, None
            transport.close()


class WebSocketTransport(Transport):
    """
    WebSocket link (`ws://` / `wss://`), e.g. to an ESP32 running
    ESPAsyncWebServer or a MicroPython websocket REPL (WebREPL).

    Text frames are UTF-8 encoded into bytes. Requires the `websockets` package.
    """

    scheme = "ws"

    def __init__(
        self,
        url: str,
        binary: bool = False,
        subprotocols: Optional[list[str]] = None,
        headers: Optional[dict[str, str]] = None,
        connect_timeout: float = 10.0,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.url = url
        self.binary = binary
        """Send outgoing data as binary frames instead of text frames."""
        self.subprotocols = subprotocols
        self.headers = headers
        self.connect_timeout = connect_timeout
        self._ws: Any = None

    @property
    def description(self) -> str:
        return self.url

    async def _open(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError as e:
            raise TransportError(
                "WebSocket transport requires `websockets`. "
                "Install with `pip install 'flet[hardware]'`."
            ) from e

        kwargs: dict[str, Any] = {"open_timeout": self.connect_timeout}
        if self.subprotocols:
            kwargs["subprotocols"] = self.subprotocols
        if self.headers:
            kwargs["additional_headers"] = self.headers
        try:
            self._ws = await websockets.connect(self.url, **kwargs)
        except Exception as e:
            raise TransportError(f"Cannot connect to {self.url}: {e}") from e
        self._start_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for message in self._ws:
                if isinstance(message, str):
                    message = message.encode("utf-8")
                self._feed_data(message)
        except asyncio.CancelledError:
            return
        except Exception as e:
            self._connection_lost(e)
            return
        self._connection_lost()

    async def _write(self, data: bytes) -> int:
        if self.binary:
            await self._ws.send(data)
        else:
            await self._ws.send(data.decode("utf-8", errors="replace"))
        return len(data)

    async def _close(self) -> None:
        if self._ws is not None:
            ws, self._ws = self._ws, None
            with contextlib.suppress(Exception):
                await ws.close()
