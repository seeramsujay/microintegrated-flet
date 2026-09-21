import asyncio
import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import flet as ft
from flet.controls.hardware.device_selector import DeviceSelector
from flet.controls.hardware.flash_progress import FlashProgress
from flet.controls.hardware.serial_console import (
    SerialConsole,
    parse_ansi_to_spans,
)
from flet.controls.services.usb_serial import UsbSerial, UsbSerialDataEvent
from flet.hardware.flasher import (
    ESP32Flasher,
    FlashProgressUpdate,
    RP2040Flasher,
    detect_uf2_drives,
    flash_firmware,
)
from flet.hardware.serial import (
    AsyncSerial,
    SerialPortInfo,
    create_serial_connection,
    list_serial_ports,
)


def test_serial_port_info_identification():
    """Verify microcontroller identification by VID/PID and description."""
    # ESP32 CP2102
    p_esp = SerialPortInfo(
        device="/dev/ttyUSB0",
        vid=0x10C4,
        pid=0xEA60,
        description="CP2102 USB to UART Bridge Controller",
        manufacturer="Silicon Labs",
    )
    assert p_esp.is_esp32() is True
    assert p_esp.is_rp2040() is False
    assert p_esp.is_microcontroller() is True
    assert "ESP32" in p_esp.display_name()

    # RP2040 Pico
    p_pico = SerialPortInfo(
        device="/dev/ttyACM0",
        vid=0x2E8A,
        pid=0x000A,
        description="Raspberry Pi Pico CDC",
        manufacturer="Raspberry Pi",
    )
    assert p_pico.is_rp2040() is True
    assert p_pico.is_esp32() is False
    assert p_pico.is_microcontroller() is True
    assert "Raspberry Pi Pico" in p_pico.display_name()

    # Generic device
    p_gen = SerialPortInfo(
        device="/dev/ttyS0",
        description="Standard Serial Port",
    )
    assert p_gen.is_microcontroller() is False
    assert "/dev/ttyS0" in p_gen.display_name()


@pytest.mark.asyncio
async def test_async_serial_buffer_and_reading():
    """Test AsyncSerial stream reading, line parsing, and buffer handling."""
    ser = AsyncSerial(port="/dev/ttyUSB0", baudrate=115200)

    # Simulate incoming chunks
    ser._on_incoming_bytes(b"HELLO MICRO\n")
    line = await ser.read_line()
    assert line == "HELLO MICRO\n"

    # Simulate partial chunks
    ser._on_incoming_bytes(b"CMD:")
    ser._on_incoming_bytes(b"PING\r\nNEXT")
    line2 = await ser.read_line()
    assert line2 == "CMD:PING\r\n"

    # Read until delimiter
    delim_data = await ser.read_until(b"T")
    assert delim_data == b"NEXT"

    # Test callback invocation
    received = []
    ser.on_data = lambda chunk: received.append(chunk)
    ser._on_incoming_bytes(b"CALLBACK_DATA")
    assert received == [b"CALLBACK_DATA"]


def test_ansi_color_parser():
    """Test ANSI escape sequence parsing into TextSpans."""
    # Plain text
    spans = parse_ansi_to_spans("Plain text")
    assert len(spans) == 1
    assert spans[0].text == "Plain text"

    # Red text followed by reset: \033[31mError\033[0m
    spans = parse_ansi_to_spans("\x1b[31mError\x1b[0m normal")
    assert len(spans) == 2
    assert spans[0].text == "Error"
    assert spans[0].style is not None
    assert spans[0].style.color == "#EF5350"
    assert spans[1].text == " normal"

    # Multi-color text
    spans = parse_ansi_to_spans("\x1b[32mOK\x1b[33mWARN\x1b[0m")
    assert len(spans) == 2
    assert spans[0].text == "OK"
    assert spans[0].style is not None
    assert spans[0].style.color == "#66BB6A"
    assert spans[1].text == "WARN"
    assert spans[1].style is not None
    assert spans[1].style.color == "#FFEE58"


def test_serial_console_buffer_and_pruning():
    """Test SerialConsole lines buffering, ANSI formatting, and buffer max limit."""
    console = SerialConsole(max_lines=5)

    # Append lines
    for i in range(10):
        console.append(f"Line {i}\n")

    # Should retain only the last 5 lines
    assert len(console._lines) == 5
    content = console.get_content()
    assert "Line 9" in content
    assert "Line 0" not in content

    # Clear console
    console.clear()
    assert len(console._lines) == 0


def test_device_selector_filtering():
    """Test DeviceSelector port filtering by VID and chip type."""
    mock_ports = [
        SerialPortInfo(
            device="/dev/ttyUSB0", vid=0x10C4, pid=0xEA60, description="ESP32"
        ),
        SerialPortInfo(
            device="/dev/ttyACM0", vid=0x2E8A, pid=0x000A, description="Pico"
        ),
        SerialPortInfo(device="/dev/ttyS0", vid=None, pid=None, description="Serial"),
    ]

    with patch(
        "flet.controls.hardware.device_selector.list_serial_ports",
        return_value=mock_ports,
    ):
        # Selector with ESP32 chip filter
        selector_esp = DeviceSelector(chip_filter="esp32")
        assert len(selector_esp.ports) == 1
        assert selector_esp.ports[0].device == "/dev/ttyUSB0"

        # Selector with VID filter
        selector_vid = DeviceSelector(vid_filter=[0x2E8A])
        assert len(selector_vid.ports) == 1
        assert selector_vid.ports[0].device == "/dev/ttyACM0"

        # All ports
        selector_all = DeviceSelector()
        assert len(selector_all.ports) == 3


def test_flash_progress_events():
    """Test FlashProgress reacting to progress update events."""
    prog = FlashProgress()
    assert prog.status == "idle"

    # Emit writing update
    update = FlashProgressUpdate(
        status="writing",
        percent=0.75,
        speed_kbps=128.5,
        bytes_written=76800,
        total_bytes=102400,
        chip_name="ESP32-S3",
        elapsed_time=2.5,
        message="Writing at 0x1000...",
    )
    prog.update_from_event(update)

    assert prog.status == "writing"
    assert prog.percent == 0.75
    assert prog._progress_bar is not None
    assert prog._progress_bar.value == 0.75
    assert prog._speed_label is not None
    assert "128.5" in prog._speed_label.value
    assert prog._title_label is not None
    assert "ESP32-S3" in prog._title_label.value or "75%" in prog._title_label.value

    # Reset
    prog.reset()
    assert prog.status == "idle"
    assert prog.percent == 0.0


@pytest.mark.asyncio
async def test_rp2040_flasher_uf2_validation():
    """Test RP2040 UF2 file validation and flashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        drive_path = tmp_path / "RPI-RP2"
        drive_path.mkdir()

        (drive_path / "INFO_UF2.TXT").write_text(
            "UF2 Bootloader v3.0\r\nModel: Raspberry Pi RP2040\r\nBoard-ID: RPI-RP2\r\n"
        )

        # Create valid UF2 dummy binary (512-byte block)
        uf2_magic_start0 = 0x0A324655
        uf2_magic_start1 = 0x9E5D5157
        uf2_magic_end = 0x0AB16F30
        flags = 0
        target_addr = 0x10000000
        payload_size = 256
        block_no = 0
        num_blocks = 1
        family_id = 0xE48BFF56

        header = struct.pack(
            "<IIIIIIII",
            uf2_magic_start0,
            uf2_magic_start1,
            flags,
            target_addr,
            payload_size,
            block_no,
            num_blocks,
            family_id,
        )
        data = b"\x00" * 476
        footer = struct.pack("<I", uf2_magic_end)
        valid_uf2_block = header + data + footer
        assert len(valid_uf2_block) == 512

        uf2_file = tmp_path / "firmware.uf2"
        uf2_file.write_bytes(valid_uf2_block)

        flasher = RP2040Flasher()
        progress_events = []

        await flasher.flash(
            firmware_path=uf2_file,
            mount_path=drive_path,
            progress_callback=lambda p: progress_events.append(p),
        )

        assert any(p.status == "complete" for p in progress_events)


@pytest.mark.asyncio
async def test_esp32_flasher_cli_mode():
    """Test ESP32Flasher invoking esptool with simulated output."""
    flasher = ESP32Flasher(force_cli=True)

    dummy_output = (
        b"Connecting....\n"
        b"Chip is ESP32-D0WD-V3 (revision v3.0)\n"
        b"Features: WiFi, BT, Dual Core\n"
        b"MAC: aa:bb:cc:dd:ee:ff\n"
        b"Writing at 0x00001000... (50 %)\n"
        b"Writing at 0x00002000... (100 %)\n"
        b"Hash of data verified.\n"
        b"Leaving... Hard resetting via RTS pin...\n"
    )

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout.readline = AsyncMock(
        side_effect=[line + b"\n" for line in dummy_output.splitlines()] + [b""]
    )
    mock_process.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with tempfile.NamedTemporaryFile(suffix=".bin") as tmp_bin:
            events = []
            await flasher.flash(
                firmware_path=tmp_bin.name,
                port="/dev/ttyUSB0",
                chip="esp32",
                progress_callback=lambda p: events.append(p),
            )

            assert any(e.status == "writing" for e in events)
            assert any(e.status == "complete" for e in events)


@pytest.mark.asyncio
async def test_firmware_flasher_router():
    """Test high-level flash_firmware routing based on extension."""
    with tempfile.NamedTemporaryFile(suffix=".uf2") as uf2_file:
        with patch.object(RP2040Flasher, "flash", new_callable=AsyncMock) as mock_rp:
            await flash_firmware(
                firmware_path=uf2_file.name,
                port="/media/user/RPI-RP2",
            )
            mock_rp.assert_called_once()

    with tempfile.NamedTemporaryFile(suffix=".bin") as bin_file:
        with patch.object(ESP32Flasher, "flash", new_callable=AsyncMock) as mock_esp:
            await flash_firmware(
                firmware_path=bin_file.name,
                port="/dev/ttyUSB0",
                chip="esp32",
            )
            mock_esp.assert_called_once()
