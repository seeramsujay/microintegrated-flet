import argparse
import platform
import sys

from rich.console import Console

import flet.version
from flet_cli.commands.base import BaseCommand

# Rich console setup for styled output
console = Console(log_path=False)


class Command(BaseCommand):
    """
    Get information about the system and environment setup.
    """

    def handle(self, options: argparse.Namespace) -> None:
        """Handle the 'doctor' command."""
        verbose = options.verbose

        os_name = platform.system()
        if os_name == "Darwin":
            os_name = "macOS"
            os_version = platform.mac_ver()[0]
        else:
            os_version = platform.release()

        arch = platform.machine()
        console.print(
            f"Flet {flet.version.flet_version} on {os_name} {os_version} ({arch})"
            if arch
            else f"Flet {flet.version.flet_version} on {os_name} {os_version}"
        )

        console.print(f"Python {platform.python_version()} ({sys.executable})")

        # TODO: output Flutter version, if installed
        # μFlet Microcontroller & Hardware Health Check
        try:
            import uflet

            hw_report = uflet.doctor(verbose=verbose)
            deps = hw_report.get("dependencies", {})
            installed_deps = [k for k, v in deps.items() if v]
            if len(installed_deps) == len(deps):
                console.print(
                    "μFlet Hardware Suite: [green]Ready[/green] (pyserial, pyserial-asyncio, esptool)"
                )
            else:
                missing = [k for k, v in deps.items() if not v]
                console.print(
                    f"μFlet Hardware Suite: [yellow]Optional dependencies missing: {', '.join(missing)}[/yellow]"
                )
            ports = hw_report.get("devices", {}).get("serial_ports", [])
            if ports:
                console.print(
                    f"  • Connected Microcontrollers / Ports: {len(ports)} detected"
                )
        except Exception:
            pass
