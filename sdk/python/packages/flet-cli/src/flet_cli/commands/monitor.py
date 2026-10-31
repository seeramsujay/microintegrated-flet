import argparse
import asyncio
import sys
import threading
import time
from typing import Optional

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from flet.hardware.bluetooth import scan_ble_devices
from flet.hardware.connect import SUPPORTED_SCHEMES, transport_from_url
from flet.hardware.serial import list_serial_ports
from flet.hardware.transport import Transport, TransportError
from flet_cli.commands.base import BaseCommand

console = Console(log_path=False, highlight=False)

LINE_ENDINGS = {"crlf": "\r\n", "lf": "\n", "cr": "\r", "none": ""}


class Command(BaseCommand):
    """
    Open an interactive terminal to a device over any μFlet transport.
    """

    name = "monitor"
    description = (
        "Talk to a device over USB serial, Bluetooth (LE / Classic SPP), "
        "WiFi (TCP / UDP / WebSocket) or MQTT."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "url",
            nargs="?",
            help=(
                "Device URL, e.g. /dev/ttyUSB0, COM3, tcp://192.168.4.1:23, "
                "udp://host:4210, ws://esp32.local/ws, "
                "mqtt://broker?rx=dev/out&tx=dev/in, ble://AA:BB:CC:DD:EE:FF, "
                "rfcomm://00:11:22:33:44:55/1. Defaults to the first detected "
                "microcontroller serial port."
            ),
        )
        parser.add_argument(
            "-b",
            "--baud",
            dest="baud",
            type=int,
            default=None,
            help="Baud rate for serial ports (default: 115200).",
        )
        parser.add_argument(
            "--eol",
            dest="eol",
            choices=list(LINE_ENDINGS),
            default="crlf",
            help="Line ending appended to each sent line.",
        )
        parser.add_argument(
            "--hex",
            dest="hex",
            action="store_true",
            default=False,
            help="Show received data as hex and parse input as hex bytes.",
        )
        parser.add_argument(
            "-t",
            "--timestamps",
            dest="timestamps",
            action="store_true",
            default=False,
            help="Prefix each received line with a timestamp.",
        )
        parser.add_argument(
            "-s",
            "--send",
            dest="send",
            action="append",
            default=None,
            help="Send this line on connect (repeatable), print replies and exit.",
        )
        parser.add_argument(
            "--duration",
            dest="duration",
            type=float,
            default=None,
            help="Exit after this many seconds (default: 2 with --send).",
        )
        parser.add_argument(
            "--list",
            dest="list",
            action="store_true",
            default=False,
            help="List supported transports and serial ports, then exit.",
        )
        parser.add_argument(
            "--scan-ble",
            dest="scan_ble",
            nargs="?",
            type=float,
            const=5.0,
            default=None,
            metavar="SECONDS",
            help="Scan for Bluetooth LE devices, then exit.",
        )
        parser.add_argument(
            "--all-ble",
            dest="all_ble",
            action="store_true",
            default=False,
            help="With --scan-ble, also list devices without a known UART service.",
        )

    def handle(self, options: argparse.Namespace) -> None:
        if options.list:
            self._print_list()
            return

        try:
            if options.scan_ble is not None:
                asyncio.run(self._scan_ble(options.scan_ble, not options.all_ble))
                return
            asyncio.run(self._run(options))
        except KeyboardInterrupt:
            console.print("\n[dim]Disconnected.[/dim]")
        except (TransportError, ValueError) as e:
            console.print(f"[bold red]Error:[/bold red] {escape(str(e))}")
            sys.exit(1)

    def _print_list(self) -> None:
        table = Table(title="Supported transports", header_style="bold cyan")
        table.add_column("Scheme", style="bold green")
        table.add_column("Description")
        for scheme, desc in SUPPORTED_SCHEMES.items():
            table.add_row(f"{scheme}://", desc)
        console.print(table)

        ports = list_serial_ports()
        if ports:
            console.print("\n[bold]Serial ports:[/bold]")
            for p in ports:
                console.print(f"  {escape(p.display_name())}")
        else:
            console.print("\n[yellow]No serial ports detected.[/yellow]")

    async def _scan_ble(self, timeout: float, uart_only: bool) -> None:
        with console.status(f"Scanning for Bluetooth LE devices ({timeout:g}s)..."):
            devices = await scan_ble_devices(timeout=timeout, uart_only=uart_only)
        if not devices:
            hint = "" if not uart_only else " Try --all-ble to list every device."
            console.print(f"[yellow]No Bluetooth LE devices found.{hint}[/yellow]")
            return
        table = Table(title="Bluetooth LE devices", header_style="bold cyan")
        table.add_column("Address / URL", style="bold green")
        table.add_column("Name")
        table.add_column("RSSI", justify="right")
        table.add_column("UART profile", style="magenta")
        for d in devices:
            table.add_row(
                f"ble://{d.address}",
                escape(d.name or "-"),
                str(d.rssi) if d.rssi is not None else "-",
                d.uart_profile or "-",
            )
        console.print(table)

    def _resolve_url(self, url: Optional[str]) -> str:
        if url:
            return url
        ports = list_serial_ports()
        mcu = [p for p in ports if p.is_microcontroller()] or ports
        if not mcu:
            raise ValueError(
                "No device URL given and no serial port detected. "
                "Run `flet monitor --list` for examples."
            )
        return mcu[0].device

    async def _run(self, options: argparse.Namespace) -> None:
        url = self._resolve_url(options.url)
        kwargs = {}
        if options.baud is not None:
            kwargs["baudrate"] = options.baud
        transport = transport_from_url(url, **kwargs)
        if kwargs and not hasattr(transport, "baudrate"):
            raise ValueError("--baud only applies to serial transports.")

        self._attach_output(transport, options)
        with console.status(f"Connecting to {escape(transport.description)}..."):
            await transport.open()
        console.print(
            f"[bold green]Connected[/bold green] to {escape(transport.description)}"
            + ("" if options.send else " [dim](Ctrl+C to exit)[/dim]")
        )

        eol = LINE_ENDINGS[options.eol]
        try:
            if options.send:
                for line in options.send:
                    await transport.write(self._encode(line, eol, options.hex))
                await self._wait(transport, options.duration or 2.0)
            else:
                await self._interactive(transport, eol, options)
        finally:
            await transport.close()

    def _attach_output(self, transport: Transport, options: argparse.Namespace):
        def _write(text: str):
            sys.stdout.write(text)
            sys.stdout.flush()

        if options.hex:
            transport.on_data = lambda chunk: _write(
                " ".join(f"{b:02X}" for b in chunk) + "\n"
            )
        elif options.timestamps:
            transport.on_line = lambda line: _write(
                time.strftime("[%H:%M:%S] ") + line.rstrip("\r\n") + "\n"
            )
        else:
            transport.on_data = lambda chunk: _write(
                chunk.decode("utf-8", errors="replace")
            )
        transport.on_error = lambda e: console.print(
            f"[red]Transport error:[/red] {escape(str(e))}"
        )

    @staticmethod
    def _encode(line: str, eol: str, hex_mode: bool) -> bytes:
        if hex_mode:
            return bytes.fromhex("".join(line.split()))
        return (line + eol).encode("utf-8")

    @staticmethod
    async def _wait(transport: Transport, duration: Optional[float]) -> None:
        deadline = None if duration is None else time.monotonic() + duration
        while transport.is_open:
            if deadline is not None and time.monotonic() >= deadline:
                return
            await asyncio.sleep(0.05)

    async def _interactive(
        self, transport: Transport, eol: str, options: argparse.Namespace
    ) -> None:
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[Optional[str]] = asyncio.Queue()

        # A daemon thread, so a blocked stdin read never delays exit.
        def _stdin_reader():
            for line in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, line.rstrip("\r\n"))
            loop.call_soon_threadsafe(lines.put_nowait, None)

        threading.Thread(target=_stdin_reader, daemon=True).start()

        async def _sender():
            while True:
                line = await lines.get()
                if line is None:
                    return
                try:
                    await transport.write(self._encode(line, eol, options.hex))
                except ValueError:
                    console.print(f"[red]Invalid hex:[/red] {escape(line)}")

        sender = asyncio.ensure_future(_sender())
        waiter = asyncio.ensure_future(self._wait(transport, options.duration))
        try:
            await asyncio.wait({sender, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sender.cancel()
            waiter.cancel()
        if not transport.is_open:
            console.print("\n[yellow]Device disconnected.[/yellow]")
