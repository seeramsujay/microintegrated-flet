import asyncio
import contextlib
import inspect
from typing import Any, Callable, Optional, Union

__all__ = ["Transport", "TransportError"]


class TransportError(RuntimeError):
    """Raised when a transport cannot be opened or used."""


class Transport:
    """
    Base class for bidirectional byte-stream links to a device.

    Concrete transports (USB serial, Bluetooth, TCP, MQTT, ...) only implement
    `_open()`, `_close()` and `_write()`, and call `_feed_data()` whenever bytes
    arrive. Buffering, line framing, callbacks and the async read API are shared.
    """

    scheme: str = ""
    """URL scheme handled by this transport (e.g. `serial`, `tcp`, `ble`)."""

    def __init__(
        self,
        max_buffer: int = 1024 * 1024,
        on_data: Optional[Callable[[bytes], Any]] = None,
        on_line: Optional[Callable[[str], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_disconnect: Optional[Callable[[], Any]] = None,
    ):
        self.max_buffer = max_buffer
        """Maximum number of unread bytes kept in memory; oldest bytes are dropped."""

        self.is_open = False
        self._buffer = bytearray()
        self._line_buffer = bytearray()
        self._data_event: Optional[asyncio.Event] = None
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

        self.on_data = on_data
        """Called with each raw chunk of received bytes."""

        self.on_line = on_line
        """Called with each complete received line (including the newline)."""

        self.on_error = on_error
        """Called when a read or callback error occurs."""

        self.on_disconnect = on_disconnect
        """Called once the transport has been closed."""

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    async def _open(self) -> None:
        raise NotImplementedError

    async def _close(self) -> None:
        raise NotImplementedError

    async def _write(self, data: bytes) -> int:
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Human-readable description of the remote endpoint."""
        return self.scheme

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _event(self) -> asyncio.Event:
        if self._data_event is None:
            self._data_event = asyncio.Event()
        return self._data_event

    async def open(self) -> None:
        """Open the connection to the device."""
        if self.is_open:
            return
        self._event()
        self._closing = False
        await self._open()
        self.is_open = True

    async def close(self) -> None:
        """Close the connection and release all resources."""
        if not self.is_open or self._closing:
            return
        self._closing = True
        self.is_open = False

        current = asyncio.current_task()
        pending = [t for t in self._tasks if t is not current and not t.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

        with contextlib.suppress(Exception):
            await self._close()

        # Wake up any reader waiting for data so it can return.
        self._event().set()

        if self.on_disconnect:
            with contextlib.suppress(Exception):
                self._invoke(self.on_disconnect)
        self._closing = False

    def _start_task(self, coro) -> asyncio.Task:
        """Run a background coroutine owned by this transport."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _connection_lost(self, exc: Optional[BaseException] = None) -> None:
        """Called by subclasses when the remote side goes away."""
        if exc is not None and isinstance(exc, Exception):
            self._report_error(exc)
        if self.is_open and not self._closing:
            self._start_task(self.close())

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Incoming data
    # ------------------------------------------------------------------

    def _invoke(self, callback: Callable, *args) -> None:
        result = callback(*args)
        if inspect.isawaitable(result):
            self._start_task(result)

    def _report_error(self, exc: Exception) -> None:
        if self.on_error:
            with contextlib.suppress(Exception):
                self._invoke(self.on_error, exc)

    def _feed_data(self, chunk: Union[bytes, bytearray, memoryview]) -> None:
        """Store an incoming chunk and dispatch callbacks."""
        chunk = bytes(chunk)
        if not chunk:
            return

        self._buffer.extend(chunk)
        overflow = len(self._buffer) - self.max_buffer
        if overflow > 0:
            del self._buffer[:overflow]
        self._event().set()

        if self.on_data:
            try:
                self._invoke(self.on_data, chunk)
            except Exception as e:
                self._report_error(e)

        if self.on_line:
            self._line_buffer.extend(chunk)
            while b"\n" in self._line_buffer:
                idx = self._line_buffer.index(b"\n") + 1
                line = bytes(self._line_buffer[:idx]).decode("utf-8", errors="replace")
                del self._line_buffer[:idx]
                try:
                    self._invoke(self.on_line, line)
                except Exception as e:
                    self._report_error(e)
            overflow = len(self._line_buffer) - self.max_buffer
            if overflow > 0:
                del self._line_buffer[:overflow]

    def _on_incoming_bytes(self, chunk: bytes) -> None:
        """Alias for feeding incoming bytes directly (useful for tests and mocks)."""
        self._feed_data(chunk)

    async def _wait_for(self, predicate: Callable[[], bool], timeout: Optional[float]):
        """Wait until `predicate()` is true or the transport is closed."""

        async def _wait():
            event = self._event()
            while not predicate():
                if not self.is_open:
                    return
                event.clear()
                await event.wait()

        if timeout is None:
            await _wait()
        else:
            await asyncio.wait_for(_wait(), timeout)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    @property
    def in_waiting(self) -> int:
        """Number of received bytes not yet consumed by a read call."""
        return len(self._buffer)

    async def read(self, n: int = -1, timeout: Optional[float] = None) -> bytes:
        """
        Read up to `n` bytes (all buffered bytes when `n < 0`).

        Waits until at least one byte is available. Returns `b""` once the
        transport is closed and the buffer is drained.
        """
        if n == 0:
            return b""
        await self._wait_for(lambda: len(self._buffer) > 0, timeout)
        if n < 0 or len(self._buffer) <= n:
            data = bytes(self._buffer)
            self._buffer.clear()
            return data
        data = bytes(self._buffer[:n])
        del self._buffer[:n]
        return data

    async def read_until(
        self, expected: bytes = b"\n", timeout: Optional[float] = None
    ) -> bytes:
        """
        Read bytes up to and including `expected`.

        If the transport closes first, returns whatever is left in the buffer.
        """
        await self._wait_for(lambda: expected in self._buffer, timeout)
        if expected in self._buffer:
            idx = self._buffer.index(expected) + len(expected)
        else:
            idx = len(self._buffer)
        data = bytes(self._buffer[:idx])
        del self._buffer[:idx]
        return data

    async def read_line(self, timeout: Optional[float] = None) -> str:
        """Read a line (up to and including `\\n`) and decode it as UTF-8."""
        data = await self.read_until(b"\n", timeout=timeout)
        return data.decode("utf-8", errors="replace")

    def reset_input_buffer(self) -> None:
        """Discard all received but unread bytes."""
        self._buffer.clear()
        self._line_buffer.clear()

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    async def write(self, data: Union[bytes, bytearray, memoryview, str]) -> int:
        """Send bytes (strings are UTF-8 encoded) to the device."""
        if not self.is_open:
            raise TransportError(f"{self.description} is not open.")
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if not raw:
            return 0
        return await self._write(raw)

    async def write_line(self, line: str, newline: str = "\r\n") -> int:
        """Send a string followed by `newline`."""
        return await self.write((line + newline).encode("utf-8"))

    async def flush(self) -> None:
        """Wait until buffered outgoing data is sent (no-op by default)."""

    def __repr__(self) -> str:
        state = "open" if self.is_open else "closed"
        return f"<{self.__class__.__name__} {self.description} ({state})>"
