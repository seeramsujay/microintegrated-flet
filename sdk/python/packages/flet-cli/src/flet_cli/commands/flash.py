import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from flet.hardware.flasher import (
    FlashProgressUpdate,
    detect_uf2_drives,
    flash_firmware,
)
from flet.hardware.serial import list_serial_ports
from flet_cli.commands.base import BaseCommand

console = Console(log_path=False)


class Command(BaseCommand):
    """
    Flash firmware binaries (.bin or .uf2) to microcontrollers (ESP32 family, RP2040 Pico).
    """

    name = "flash"
    description = "Deploy firmware binaries directly to connected microcontrollers."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-f",
            "--firmware",
            dest="firmware",
            type=str,
            help="Path to the firmware binary (.bin for ESP32, .uf2 for RP2040 / Pico).",
        )
        parser.add_argument(
            "-p",
            "--port",
            dest="port",
            type=str,
            help="Serial port (e.g. /dev/ttyUSB0, COM3) or mounted bootloader drive directory.",
        )
        parser.add_argument(
            "-c",
            "--chip",
            dest="chip",
            type=str,
            default="auto",
            choices=[
                "auto",
                "esp32",
                "esp32s2",
                "esp32s3",
                "esp32c3",
                "esp32c6",
                "esp8266",
                "rp2040",
            ],
            help="Target microcontroller family (default: auto-detected from binary and device).",
        )
        parser.add_argument(
            "-b",
            "--baud",
            dest="baud",
            type=int,
            default=460800,
            help="Baud rate for flashing serial bootloaders (default: 460800).",
        )
        parser.add_argument(
            "--offset",
            dest="offset",
            type=lambda x: int(x, 0),
            default=None,
            help="Flash memory offset in hex (e.g. 0x1000 or 0x0).",
        )
        parser.add_argument(
            "--erase",
            "--erase-all",
            dest="erase",
            action="store_true",
            default=False,
            help="Erase all flash memory sectors prior to programming.",
        )
        parser.add_argument(
            "-l",
            "--list-ports",
            dest="list_ports",
            action="store_true",
            default=False,
            help="List all connected serial ports and microcontrollers, then exit.",
        )
        parser.add_argument(
            "--list-drives",
            dest="list_drives",
            action="store_true",
            default=False,
            help="List all mounted RP2040 / Pico UF2 bootloader drives, then exit.",
        )

    def handle(self, options: argparse.Namespace) -> None:
        # Handle port listing
        if options.list_ports:
            self._print_ports_table()
            return

        # Handle drive listing
        if options.list_drives:
            self._print_drives_table()
            return

        if not options.firmware:
            console.print(
                "[bold red]Error:[/bold red] Firmware file must be specified with --firmware or -f. "
                "Run [bold cyan]flet flash --help[/bold cyan] for usage instructions."
            )
            sys.exit(1)

        firmware_path = Path(options.firmware).resolve()
        if not firmware_path.exists():
            console.print(
                f"[bold red]Error:[/bold red] Firmware file not found: {firmware_path}"
            )
            sys.exit(1)

        # Run async flashing
        try:
            asyncio.run(self._run_flash(options, firmware_path))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Flashing aborted by user.[/bold yellow]")
            sys.exit(130)
        except Exception as exc:
            console.print(f"\n[bold red]Flashing failed:[/bold red] {exc}")
            if options.verbose:
                console.print_exception()
            sys.exit(1)

    def _print_ports_table(self) -> None:
        ports = list_serial_ports()
        table = Table(
            title="Connected Serial Ports & Microcontrollers",
            show_lines=True,
            header_style="bold cyan",
        )
        table.add_column("Device / Port", style="bold green")
        table.add_column("Description")
        table.add_column("VID:PID", justify="center")
        table.add_column("Manufacturer")
        table.add_column("Chip Detection", style="magenta")

        for p in ports:
            vid_pid = f"{p.vid:04X}:{p.pid:04X}" if p.vid and p.pid else "N/A"
            chip = (
                "ESP32 / ESP8266"
                if p.is_esp32()
                else ("RP2040 / Pico" if p.is_rp2040() else "Generic")
            )
            table.add_row(
                p.device,
                p.description or p.name or "N/A",
                vid_pid,
                p.manufacturer or "N/A",
                chip,
            )

        if not ports:
            console.print("[yellow]No serial devices detected.[/yellow]")
        else:
            console.print(table)

    def _print_drives_table(self) -> None:
        drives = detect_uf2_drives()
        table = Table(
            title="Mounted RP2040 UF2 Bootloader Drives",
            show_lines=True,
            header_style="bold magenta",
        )
        table.add_column("Mount Path", style="bold green")
        table.add_column("Volume Label")
        table.add_column("Board Model")

        for d in drives:
            info_file = d / "INFO_UF2.TXT"
            model = "Raspberry Pi RP2040"
            if info_file.exists():
                for line in info_file.read_text(errors="replace").splitlines():
                    if "Model:" in line:
                        model = line.split(":", 1)[1].strip()
            table.add_row(str(d), d.name, model)

        if not drives:
            console.print("[yellow]No mounted UF2 bootloader drives found.[/yellow]")
        else:
            console.print(table)

    async def _run_flash(
        self, options: argparse.Namespace, firmware_path: Path
    ) -> None:
        chip = options.chip
        port = options.port
        file_size_kb = firmware_path.stat().st_size / 1024.0

        # Auto-detect chip if requested
        if chip == "auto":
            if firmware_path.suffix.lower() == ".uf2":
                chip = "rp2040"
            else:
                chip = "esp32"

        # Auto-detect port/drive if not provided
        if not port:
            if chip == "rp2040":
                detected_drives = detect_uf2_drives()
                if not detected_drives:
                    console.print(
                        "[bold red]Error:[/bold red] No RP2040 UF2 drive found. "
                        "Hold the BOOTSEL button while plugging in the Pico, or specify drive with --port."
                    )
                    sys.exit(1)
                port = str(detected_drives[0])
            else:
                detected_ports = [p for p in list_serial_ports() if p.is_esp32()]
                if not detected_ports:
                    detected_ports = list_serial_ports()
                if not detected_ports:
                    console.print(
                        "[bold red]Error:[/bold red] No serial port detected. "
                        "Plug in your microcontroller or specify port with --port."
                    )
                    sys.exit(1)
                port = detected_ports[0].device

        panel_content = (
            f"[bold]Target Chip:[/bold] [magenta]{chip.upper()}[/magenta]\n"
            f"[bold]Firmware:[/bold] [cyan]{firmware_path.name}[/cyan] ({file_size_kb:.1f} KB)\n"
            f"[bold]Port / Mount:[/bold] [green]{port}[/green]\n"
            f"[bold]Baud Rate:[/bold] {options.baud}\n"
            f"[bold]Erase Flash:[/bold] {'Yes' if options.erase else 'No'}"
        )
        console.print(
            Panel(panel_content, title="Flet Microcontroller Flasher", expand=False)
        )

        # Setup Rich progress UI
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("• [cyan]{task.fields[speed]}[/cyan]"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id: TaskID = progress.add_task(
                f"Connecting to {chip.upper()}...",
                total=100,
                speed="0 kB/s",
            )

            def _on_progress(update: FlashProgressUpdate) -> None:
                speed_str = (
                    f"{update.speed_kbps:.1f} kB/s" if update.speed_kbps > 0 else "--"
                )
                pct = int(update.percent * 100)

                if update.status == "connecting":
                    desc = f"Connecting to {chip.upper()} on {port}..."
                elif update.status == "erasing":
                    desc = "Erasing flash sectors..."
                elif update.status == "writing":
                    desc = f"Writing firmware ({pct}%)..."
                elif update.status == "complete":
                    desc = "[bold green]Flashing complete![/bold green]"
                elif update.status == "error":
                    desc = "[bold red]Flashing failed![/bold red]"
                else:
                    desc = update.message or "Flashing..."

                progress.update(
                    task_id,
                    completed=pct,
                    description=desc,
                    speed=speed_str,
                )

            await flash_firmware(
                firmware_path=firmware_path,
                chip=chip,
                port=port,
                baudrate=options.baud,
                offset=options.offset,
                erase_first=options.erase,
                progress_callback=_on_progress,
            )

        console.print(
            f"\n[bold green]Success![/bold green] Firmware flashed to {chip.upper()} on {port}."
        )
