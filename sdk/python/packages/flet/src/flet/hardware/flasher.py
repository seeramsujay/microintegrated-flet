import asyncio
import os
import re
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

__all__ = [
    "ESP32Flasher",
    "FirmwareFlasher",
    "FlashProgressUpdate",
    "RP2040Flasher",
    "detect_uf2_drives",
    "flash_firmware",
]


@dataclass
class FlashProgressUpdate:
    """
    Status and metrics update emitted during a microcontroller flashing session.
    """

    status: str
    """Phase name: 'idle', 'connecting', 'erasing', 'writing', 'verifying', 'complete', 'error'."""

    percent: float = 0.0
    """Completion progress in the range 0.0 to 1.0."""

    message: str = ""
    """Human-readable progress or log message."""

    bytes_written: int = 0
    """Total bytes uploaded so far."""

    total_bytes: int = 0
    """Total size in bytes of the firmware binary."""

    speed_kbps: float = 0.0
    """Current transfer rate in kilobytes per second."""

    erased_sectors: int = 0
    """Count of flash sectors successfully erased."""

    total_sectors: int = 0
    """Total flash sectors to be erased."""

    chip_name: Optional[str] = None
    """Detected microcontroller chip variant."""

    elapsed_time: float = 0.0
    """Total elapsed flashing duration in seconds."""


# ---------------------------------------------------------------------------
# RP2040 / Raspberry Pi Pico UF2 Bootloader Flasher
# ---------------------------------------------------------------------------

UF2_MAGIC_START0 = 0x0A324655  # "UF2\n"
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30


def detect_uf2_drives() -> list[Path]:
    """
    Auto-detect mounted RP2040 native UF2 bootloader volumes ('RPI-RP2')
    across Linux, macOS, and Windows.
    """
    drives: list[Path] = []

    # 1. Linux mounts
    if sys.platform.startswith("linux"):
        candidate_dirs = [
            Path("/media"),
            Path("/run/media"),
            Path(f"/media/{os.environ.get('USER', '')}"),
            Path(f"/run/media/{os.environ.get('USER', '')}"),
        ]
        for base in candidate_dirs:
            if base.is_dir():
                for entry in base.glob("**/RPI-RP2*"):
                    if entry.is_dir():
                        drives.append(entry)

        # Check /proc/mounts
        proc_mounts = Path("/proc/mounts")
        if proc_mounts.exists():
            try:
                for line in proc_mounts.read_text().splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        mount_point = Path(parts[1])
                        if (
                            mount_point.name == "RPI-RP2"
                            or (mount_point / "INFO_UF2.TXT").exists()
                        ):
                            if mount_point not in drives:
                                drives.append(mount_point)
            except Exception:
                pass

    # 2. macOS Volumes
    elif sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            for vol in volumes.iterdir():
                if vol.name == "RPI-RP2" or (vol / "INFO_UF2.TXT").exists():
                    drives.append(vol)

    # 3. Windows Drive Letters
    elif sys.platform == "win32":
        import string

        for letter in string.ascii_uppercase:
            drive_root = Path(f"{letter}:\\")
            if drive_root.exists():
                info_file = drive_root / "INFO_UF2.TXT"
                if info_file.exists():
                    drives.append(drive_root)

    return list(dict.fromkeys(drives))


class RP2040Flasher:
    """
    Embedded flasher for the Raspberry Pi Pico / RP2040 UF2 mass storage bootloader.
    """

    def __init__(self, mount_path: Optional[Union[str, Path]] = None):
        self.mount_path = Path(mount_path) if mount_path else None

    def find_drive(self) -> Optional[Path]:
        """Locate the mounted RP2040 UF2 bootloader drive."""
        if self.mount_path and self.mount_path.exists():
            return self.mount_path
        detected = detect_uf2_drives()
        return detected[0] if detected else None

    def read_info(self, drive_path: Optional[Path] = None) -> dict[str, str]:
        """Read microcontroller metadata from INFO_UF2.TXT on the bootloader volume."""
        drive = drive_path or self.find_drive()
        if not drive:
            return {}
        info_file = drive / "INFO_UF2.TXT"
        if not info_file.exists():
            return {}
        info = {}
        for line in info_file.read_text(errors="replace").splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                info[key.strip()] = val.strip()
        return info

    def validate_uf2(self, firmware_path: Path) -> bool:
        """Verify that the binary conforms to the UF2 file format specifications."""
        if not firmware_path.exists() or firmware_path.stat().st_size < 512:
            return False
        with open(firmware_path, "rb") as f:
            header = f.read(512)
            if len(header) < 512:
                return False
            magic_start0, magic_start1 = struct.unpack("<II", header[0:8])
            magic_end = struct.unpack("<I", header[508:512])[0]
            return (
                magic_start0 == UF2_MAGIC_START0
                and magic_start1 == UF2_MAGIC_START1
                and magic_end == UF2_MAGIC_END
            )

    async def flash(
        self,
        firmware_path: Union[str, Path],
        drive_path: Optional[Union[str, Path]] = None,
        mount_path: Optional[Union[str, Path]] = None,
        progress_callback: Optional[Callable[[FlashProgressUpdate], None]] = None,
    ) -> bool:
        """
        Deploy firmware `.uf2` directly to the RP2040 mass-storage bootloader.
        """
        firmware_file = Path(firmware_path)
        if not firmware_file.exists():
            raise FileNotFoundError(f"Firmware binary not found: {firmware_file}")

        if not self.validate_uf2(firmware_file):
            raise ValueError(
                f"File {firmware_file.name} is not a valid UF2 firmware binary."
            )

        target_dir = drive_path or mount_path
        dest_drive = Path(target_dir) if target_dir else self.find_drive()
        if not dest_drive or not dest_drive.exists():
            raise RuntimeError(
                "RP2040 bootloader drive ('RPI-RP2') not detected. "
                "Hold the BOOTSEL button while plugging in the Pico."
            )

        total_bytes = firmware_file.stat().st_size
        bytes_written = 0
        start_time = time.time()

        dest_file = dest_drive / firmware_file.name

        def _notify(status: str, percent: float, msg: str, speed: float = 0.0):
            if progress_callback:
                elapsed = time.time() - start_time
                progress_callback(
                    FlashProgressUpdate(
                        status=status,
                        percent=percent,
                        message=msg,
                        bytes_written=bytes_written,
                        total_bytes=total_bytes,
                        speed_kbps=speed,
                        chip_name="RP2040",
                        elapsed_time=elapsed,
                    )
                )

        _notify("connecting", 0.0, f"Found RP2040 drive at {dest_drive}")
        await asyncio.sleep(0.05)

        _notify("writing", 0.0, "Writing UF2 firmware blocks...")

        # Copy in 64KB chunks and yield to event loop for smooth UI rendering
        chunk_size = 64 * 1024
        with open(firmware_file, "rb") as src, open(dest_file, "wb") as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
                dst.flush()
                bytes_written += len(chunk)
                elapsed = max(time.time() - start_time, 0.001)
                speed = (bytes_written / 1024) / elapsed
                percent = min(bytes_written / total_bytes, 1.0)
                _notify(
                    "writing",
                    percent,
                    f"Writing UF2 blocks ({int(percent * 100)}%)...",
                    speed=speed,
                )
                await asyncio.sleep(0.01)

            # Ensure sync to disk
            try:
                os.fsync(dst.fileno())
            except Exception:
                pass

        _notify(
            "complete",
            1.0,
            "Firmware successfully written! RP2040 is rebooting...",
            speed=(total_bytes / 1024) / max(time.time() - start_time, 0.001),
        )
        return True


# ---------------------------------------------------------------------------
# ESP32 Series Firmware Flasher (esptool wrapper & ROM bootloader routines)
# ---------------------------------------------------------------------------


class ESP32Flasher:
    """
    Embedded flasher for ESP32 family (ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP8266).
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 460800,
        chip: str = "auto",
        offset: int = 0x1000,
        force_cli: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.chip = chip
        self.offset = offset
        self.force_cli = force_cli

    async def detect_chip(self) -> str:
        """Query the connected device over serial to identify the exact ESP chip model."""
        if not self.port:
            raise ValueError("Serial port must be specified to detect chip.")

        try:
            import esptool  # type: ignore

            loop = asyncio.get_running_loop()

            def _detect():
                esp = esptool.cmds.detect_chip(
                    [f"--port={self.port}", f"--baud={self.baudrate}"]
                )
                return esp.CHIP_NAME

            return await loop.run_in_executor(None, _detect)
        except Exception:
            # Fallback label
            return "ESP32"

    async def erase_flash(
        self,
        progress_callback: Optional[Callable[[FlashProgressUpdate], None]] = None,
    ) -> bool:
        """Erase the microcontroller's SPI flash memory sectors."""
        start_time = time.time()

        def _notify(status: str, percent: float, msg: str):
            if progress_callback:
                progress_callback(
                    FlashProgressUpdate(
                        status=status,
                        percent=percent,
                        message=msg,
                        chip_name=self.chip,
                        elapsed_time=time.time() - start_time,
                    )
                )

        _notify("connecting", 0.0, f"Connecting to ESP32 on {self.port}...")
        await asyncio.sleep(0.05)

        _notify("erasing", 0.3, "Erasing flash memory...")

        if not self.force_cli:
            try:
                import esptool  # type: ignore

                loop = asyncio.get_running_loop()
                cmd_args = [
                    "--port",
                    str(self.port),
                    "--baud",
                    str(self.baudrate),
                    "erase_flash",
                ]
                if self.chip != "auto":
                    cmd_args.extend(["--chip", self.chip])

                def _erase():
                    esptool.main(cmd_args)

                await loop.run_in_executor(None, _erase)
                _notify("complete", 1.0, "Flash memory erased successfully.")
                return True
            except ImportError:
                pass

        # Fallback to esptool CLI executable if available
        return await self._run_cli(["erase_flash"], progress_callback, start_time)

    async def flash(
        self,
        firmware_path: Union[str, Path],
        port: Optional[str] = None,
        chip: Optional[str] = None,
        offset: Optional[int] = None,
        erase_first: bool = False,
        progress_callback: Optional[Callable[[FlashProgressUpdate], None]] = None,
    ) -> bool:
        if port is not None:
            self.port = port
        if chip is not None:
            self.chip = chip
        """
        Write a `.bin` image to the ESP32 microcontroller at the specified flash offset.
        """
        firmware_file = Path(firmware_path)
        if not firmware_file.exists():
            raise FileNotFoundError(f"Firmware file not found: {firmware_file}")

        flash_offset = offset if offset is not None else self.offset
        total_bytes = firmware_file.stat().st_size
        start_time = time.time()

        def _notify(
            status: str, percent: float, msg: str, speed: float = 0.0, erased: int = 0
        ):
            if progress_callback:
                progress_callback(
                    FlashProgressUpdate(
                        status=status,
                        percent=percent,
                        message=msg,
                        bytes_written=int(total_bytes * percent),
                        total_bytes=total_bytes,
                        speed_kbps=speed,
                        erased_sectors=erased,
                        chip_name=self.chip,
                        elapsed_time=time.time() - start_time,
                    )
                )

        _notify(
            "connecting", 0.0, f"Connecting to {self.chip.upper()} on {self.port}..."
        )

        if erase_first:
            await self.erase_flash(progress_callback)

        _notify("erasing", 0.05, "Preparing flash sectors...")
        await asyncio.sleep(0.05)

        # Attempt in-process esptool call
        if not self.force_cli:
            try:
                import esptool  # type: ignore

                loop = asyncio.get_running_loop()

                cmd_args = [
                    "--port",
                    str(self.port),
                    "--baud",
                    str(self.baudrate),
                ]
                if self.chip != "auto":
                    cmd_args.extend(["--chip", self.chip])

                cmd_args.extend(
                    [
                        "write_flash",
                        "-z",
                        hex(flash_offset),
                        str(firmware_file),
                    ]
                )

                # Simulated granular progress pump while esptool runs
                done_event = asyncio.Event()

                async def _progress_monitor():
                    step = 0
                    while not done_event.is_set():
                        await asyncio.sleep(0.25)
                        step += 1
                        pct = min(0.05 + (step * 0.05), 0.95)
                        elapsed = max(time.time() - start_time, 0.001)
                        speed = (total_bytes * pct / 1024) / elapsed
                        _notify(
                            "writing",
                            pct,
                            f"Writing firmware at {hex(flash_offset)} ({int(pct * 100)}%)...",
                            speed=speed,
                        )

                monitor_task = asyncio.create_task(_progress_monitor())
                try:
                    await loop.run_in_executor(None, esptool.main, cmd_args)
                finally:
                    done_event.set()
                    monitor_task.cancel()

                elapsed = max(time.time() - start_time, 0.001)
                _notify(
                    "complete",
                    1.0,
                    f"Flash verified and written successfully ({total_bytes} bytes)!",
                    speed=(total_bytes / 1024) / elapsed,
                )
                return True
            except ImportError:
                pass

        # Fallback to esptool CLI
        cli_args = [
            "write_flash",
            "-z",
            hex(flash_offset),
            str(firmware_file),
        ]
        return await self._run_cli(cli_args, progress_callback, start_time, total_bytes)

    async def _run_cli(
        self,
        subcmd: list[str],
        progress_callback: Optional[Callable[[FlashProgressUpdate], None]],
        start_time: float,
        total_bytes: int = 0,
    ) -> bool:
        """Fallback to executing esptool subprocess and parsing progress."""
        cmd = [
            sys.executable,
            "-m",
            "esptool",
            "--port",
            str(self.port),
            "--baud",
            str(self.baudrate),
        ]
        if self.chip != "auto":
            cmd.extend(["--chip", self.chip])
        cmd.extend(subcmd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        pct_pattern = re.compile(r"\((\d+)\s*%\)")

        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            match = pct_pattern.search(text)
            if match and progress_callback:
                pct = int(match.group(1)) / 100.0
                elapsed = max(time.time() - start_time, 0.001)
                speed = (total_bytes * pct / 1024) / elapsed
                progress_callback(
                    FlashProgressUpdate(
                        status="writing",
                        percent=pct,
                        message=text,
                        bytes_written=int(total_bytes * pct),
                        total_bytes=total_bytes,
                        speed_kbps=speed,
                        chip_name=self.chip,
                        elapsed_time=elapsed,
                    )
                )

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"esptool failed with return code {proc.returncode}")

        if progress_callback:
            progress_callback(
                FlashProgressUpdate(
                    status="complete",
                    percent=1.0,
                    message="Firmware flashed successfully.",
                    bytes_written=total_bytes,
                    total_bytes=total_bytes,
                    chip_name=self.chip,
                    elapsed_time=time.time() - start_time,
                )
            )
        return True


# ---------------------------------------------------------------------------
# Unified High-Level Flashing Interface
# ---------------------------------------------------------------------------


class FirmwareFlasher:
    """
    Unified flasher router that automatically adapts to the target hardware
    (ESP32 family or RP2040 / Raspberry Pi Pico).
    """

    def __init__(
        self,
        chip: str = "auto",
        port: Optional[str] = None,
        baudrate: int = 460800,
        offset: Optional[int] = None,
    ):
        self.chip = chip.lower()
        self.port = port
        self.baudrate = baudrate
        self.offset = offset

    async def flash(
        self,
        firmware_path: Union[str, Path],
        erase_first: bool = False,
        progress_callback: Optional[Callable[[FlashProgressUpdate], None]] = None,
    ) -> bool:
        firmware_file = Path(firmware_path)
        if not firmware_file.exists():
            raise FileNotFoundError(f"Firmware binary does not exist: {firmware_file}")

        # Determine target architecture
        is_rp2040 = (
            self.chip == "rp2040"
            or firmware_file.suffix.lower() == ".uf2"
            or "pico" in firmware_file.name.lower()
        )

        if is_rp2040:
            flasher = RP2040Flasher(mount_path=self.port)
            return await flasher.flash(
                firmware_file, progress_callback=progress_callback
            )
        else:
            default_offset = 0x0 if self.chip in ("esp32c3", "esp32s3") else 0x1000
            target_offset = self.offset if self.offset is not None else default_offset
            esp_flasher = ESP32Flasher(
                port=self.port,
                baudrate=self.baudrate,
                chip=self.chip,
                offset=target_offset,
            )
            return await esp_flasher.flash(
                firmware_file,
                offset=target_offset,
                erase_first=erase_first,
                progress_callback=progress_callback,
            )


async def flash_firmware(
    firmware_path: Union[str, Path],
    chip: str = "auto",
    port: Optional[str] = None,
    baudrate: int = 460800,
    offset: Optional[int] = None,
    erase_first: bool = False,
    progress_callback: Optional[Callable[[FlashProgressUpdate], None]] = None,
) -> bool:
    """
    Flash microcontroller firmware with real-time non-blocking progress updates.
    """
    flasher = FirmwareFlasher(
        chip=chip,
        port=port,
        baudrate=baudrate,
        offset=offset,
    )
    return await flasher.flash(
        firmware_path=firmware_path,
        erase_first=erase_first,
        progress_callback=progress_callback,
    )
