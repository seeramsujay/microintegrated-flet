import socket
import threading
from unittest.mock import AsyncMock, patch

import pytest

from flet.hardware.bluetooth import BleDeviceInfo
from flet.hardware.serial import SerialPortInfo
from flet_cli.cli import get_parser


def _echo_server():
    """Start a one-shot TCP server that upper-cases what it receives."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        with conn:
            while data := conn.recv(100):
                conn.sendall(data.upper())
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def test_monitor_parser_arguments():
    options = get_parser().parse_args(
        ["monitor", "mqtt://broker?rx=a&tx=b", "--eol", "lf", "--hex", "-s", "01 02"]
    )
    assert options.command == "monitor"
    assert options.url == "mqtt://broker?rx=a&tx=b"
    assert options.eol == "lf"
    assert options.hex is True
    assert options.send == ["01 02"]


def test_monitor_send_over_tcp(capsys):
    port = _echo_server()
    options = get_parser().parse_args(
        [
            "monitor",
            f"tcp://127.0.0.1:{port}",
            "--eol",
            "lf",
            "-s",
            "hello",
            "--duration",
            "0.5",
        ]
    )
    options.handler(options)
    out = capsys.readouterr().out
    assert "Connected" in out
    assert "HELLO" in out


def test_monitor_list(capsys):
    options = get_parser().parse_args(["monitor", "--list"])
    ports = [SerialPortInfo(device="/dev/ttyUSB0", vid=0x10C4, pid=0xEA60)]
    with patch("flet_cli.commands.monitor.list_serial_ports", return_value=ports):
        options.handler(options)
    out = capsys.readouterr().out
    for scheme in ("serial://", "ble://", "mqtt://", "tcp://", "rfcomm://"):
        assert scheme in out
    assert "/dev/ttyUSB0" in out


def test_monitor_scan_ble(capsys):
    options = get_parser().parse_args(["monitor", "--scan-ble", "1"])
    devices = [BleDeviceInfo(address="AA:BB:CC:DD:EE:FF", name="ESP32-UART", rssi=-50)]
    with patch(
        "flet_cli.commands.monitor.scan_ble_devices",
        AsyncMock(return_value=devices),
    ) as scan:
        options.handler(options)
    scan.assert_awaited_once_with(timeout=1.0, uart_only=True)
    assert "ble://AA:BB:CC:DD:EE:FF" in capsys.readouterr().out


def test_monitor_no_device(capsys):
    options = get_parser().parse_args(["monitor"])
    with (
        patch("flet_cli.commands.monitor.list_serial_ports", return_value=[]),
        pytest.raises(SystemExit),
    ):
        options.handler(options)
    assert "no serial port detected" in capsys.readouterr().out


def test_monitor_bad_url(capsys):
    options = get_parser().parse_args(["monitor", "gopher://x"])
    with pytest.raises(SystemExit):
        options.handler(options)
    assert "Unsupported transport" in capsys.readouterr().out
