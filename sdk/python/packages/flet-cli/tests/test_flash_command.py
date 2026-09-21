import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from flet.hardware.serial import SerialPortInfo
from flet_cli.cli import get_parser


def test_flash_command_parser_arguments():
    """Verify flash subcommand arguments parsing."""
    parser = get_parser()
    options = parser.parse_args(
        [
            "flash",
            "--firmware",
            "firmware.bin",
            "--port",
            "/dev/ttyUSB0",
            "--chip",
            "esp32s3",
            "--baud",
            "921600",
            "--offset",
            "0x0",
            "--erase",
        ]
    )

    assert options.command == "flash"
    assert options.firmware == "firmware.bin"
    assert options.port == "/dev/ttyUSB0"
    assert options.chip == "esp32s3"
    assert options.baud == 921600
    assert options.offset == 0
    assert options.erase is True


def test_flash_list_ports_empty(capsys):
    """Test `flet flash -l` when no serial ports are connected."""
    parser = get_parser()
    options = parser.parse_args(["flash", "-l"])

    with patch("flet_cli.commands.flash.list_serial_ports", return_value=[]):
        options.handler(options)

    captured = capsys.readouterr()
    assert "No serial devices detected" in captured.out


def test_flash_list_ports_with_devices(capsys):
    """Test `flet flash -l` displays discovered serial devices in formatted output."""
    parser = get_parser()
    options = parser.parse_args(["flash", "-l"])

    mock_ports = [
        SerialPortInfo(
            device="/dev/ttyUSB0",
            vid=0x10C4,
            pid=0xEA60,
            description="CP2102 USB to UART Bridge",
            manufacturer="Silicon Labs",
        ),
        SerialPortInfo(
            device="/dev/ttyACM0",
            vid=0x2E8A,
            pid=0x000A,
            description="Raspberry Pi Pico",
            manufacturer="Raspberry Pi",
        ),
    ]

    with patch("flet_cli.commands.flash.list_serial_ports", return_value=mock_ports):
        options.handler(options)

    captured = capsys.readouterr()
    assert "/dev/ttyUSB0" in captured.out
    assert "/dev/ttyACM0" in captured.out


def test_flash_list_drives(capsys, tmp_path):
    """Test `flet flash --list-drives` output."""
    parser = get_parser()
    options = parser.parse_args(["flash", "--list-drives"])

    mock_drives = [tmp_path / "RPI-RP2"]
    with patch("flet_cli.commands.flash.detect_uf2_drives", return_value=mock_drives):
        with patch(
            "flet.hardware.flasher.RP2040Flasher.read_info",
            return_value={"Board-ID": "RPI-RP2"},
        ):
            options.handler(options)

    captured = capsys.readouterr()
    assert "RPI-RP2" in captured.out


def test_flash_missing_firmware_flag(capsys):
    """Test error message when neither --firmware nor list flags are specified."""
    parser = get_parser()
    options = parser.parse_args(["flash"])

    with pytest.raises(SystemExit) as exc:
        options.handler(options)

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Firmware file must be specified" in captured.out


def test_flash_execute_rp2040(tmp_path):
    """Test invoking RP2040 flashing routine via CLI handler."""
    firmware_uf2 = tmp_path / "app.uf2"
    firmware_uf2.write_bytes(b"dummy")

    parser = get_parser()
    options = parser.parse_args(["flash", "-f", str(firmware_uf2), "-p", str(tmp_path)])

    with patch(
        "flet.hardware.flasher.RP2040Flasher.flash", new_callable=AsyncMock
    ) as mock_flash:
        mock_flash.return_value = True
        options.handler(options)
        mock_flash.assert_called_once()
