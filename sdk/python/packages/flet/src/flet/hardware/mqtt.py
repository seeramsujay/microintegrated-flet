import asyncio
import contextlib
import ssl
from typing import Any, Callable, Optional, Union

from flet.hardware.transport import Transport, TransportError

__all__ = ["MqttTransport"]


class MqttTransport(Transport):
    """
    MQTT link through a broker (Mosquitto, HiveMQ, EMQX, AWS IoT, ...).

    The device publishes to `rx_topic` (what this side receives) and subscribes
    to `tx_topic` (what this side sends). Each MQTT message payload is fed into
    the transport as a chunk, so `read_line()`, `on_line` etc. work as with a
    serial port. Use `on_message` to get the topic of each message as well.

    Requires the `aiomqtt` package.
    """

    scheme = "mqtt"

    def __init__(
        self,
        host: str,
        port: Optional[int] = None,
        rx_topic: Union[str, list[str], None] = None,
        tx_topic: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        tls: Union[bool, ssl.SSLContext] = False,
        qos: int = 0,
        retain: bool = False,
        keepalive: int = 60,
        reconnect: bool = True,
        reconnect_interval: float = 3.0,
        append_newline: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.host = host
        self.tls = tls
        self.port = int(port) if port is not None else (8883 if tls else 1883)
        if isinstance(rx_topic, str):
            rx_topic = [rx_topic]
        self.rx_topics: list[str] = list(rx_topic or [])
        self.tx_topic = tx_topic
        self.username = username
        self.password = password
        self.client_id = client_id
        self.qos = qos
        self.retain = retain
        self.keepalive = keepalive
        self.reconnect = reconnect
        self.reconnect_interval = reconnect_interval
        self.append_newline = append_newline
        """Terminate each received payload with `\\n` so line readers see messages."""

        self.on_message: Optional[Callable[[str, bytes], Any]] = None
        """Called with `(topic, payload)` for every received message."""

        self._client: Any = None

    @property
    def description(self) -> str:
        scheme = "mqtts" if self.tls else "mqtt"
        return f"{scheme}://{self.host}:{self.port}"

    def _make_client(self):
        try:
            import aiomqtt  # type: ignore
        except ImportError as e:
            raise TransportError(
                "MQTT transport requires `aiomqtt`. "
                "Install with `pip install 'flet[hardware]'`."
            ) from e

        kwargs: dict[str, Any] = {
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "keepalive": self.keepalive,
        }
        if self.client_id:
            kwargs["identifier"] = self.client_id
        if isinstance(self.tls, ssl.SSLContext):
            kwargs["tls_context"] = self.tls
        elif self.tls:
            kwargs["tls_context"] = ssl.create_default_context()
        return aiomqtt.Client(self.host, **kwargs)

    async def _connect(self) -> None:
        client = self._make_client()
        await client.__aenter__()
        for topic in self.rx_topics:
            await client.subscribe(topic, qos=self.qos)
        self._client = client

    async def _open(self) -> None:
        if not self.rx_topics and not self.tx_topic:
            raise TransportError("MQTT transport needs an rx_topic and/or tx_topic.")
        try:
            await self._connect()
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(f"Cannot connect to {self.description}: {e}") from e
        self._start_task(self._read_loop())

    async def _read_loop(self) -> None:
        while not self._closing:
            try:
                async for message in self._client.messages:
                    payload = message.payload
                    if isinstance(payload, str):
                        payload = payload.encode("utf-8")
                    elif payload is None:
                        payload = b""
                    elif not isinstance(payload, (bytes, bytearray)):
                        payload = str(payload).encode("utf-8")
                    if self.on_message:
                        try:
                            self._invoke(self.on_message, str(message.topic), payload)
                        except Exception as e:
                            self._report_error(e)
                    if self.append_newline and not payload.endswith(b"\n"):
                        payload = payload + b"\n"
                    self._feed_data(payload)
            except asyncio.CancelledError:
                return
            except Exception as e:
                if not self.reconnect or self._closing:
                    self._connection_lost(e)
                    return
                self._report_error(e)
                if not await self._reconnect():
                    return
                continue
            # Message iterator ended: the broker connection went away.
            if not self.reconnect or not await self._reconnect():
                self._connection_lost()
                return

    async def _reconnect(self) -> bool:
        """Re-establish the broker connection; returns False when closing."""
        old, self._client = self._client, None
        if old is not None:
            with contextlib.suppress(Exception):
                await old.__aexit__(None, None, None)
        while not self._closing:
            await asyncio.sleep(self.reconnect_interval)
            try:
                await self._connect()
                return True
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._report_error(e)
        return False

    async def publish(
        self,
        topic: str,
        payload: Union[bytes, str],
        qos: Optional[int] = None,
        retain: Optional[bool] = None,
    ) -> None:
        """Publish a message to an arbitrary topic."""
        if not self.is_open or self._client is None:
            raise TransportError(f"{self.description} is not connected.")
        await self._client.publish(
            topic,
            payload=payload,
            qos=self.qos if qos is None else qos,
            retain=self.retain if retain is None else retain,
        )

    async def _write(self, data: bytes) -> int:
        if not self.tx_topic:
            raise TransportError("MQTT transport has no tx_topic to publish to.")
        await self.publish(self.tx_topic, data)
        return len(data)

    async def _close(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            with contextlib.suppress(Exception):
                await client.__aexit__(None, None, None)
