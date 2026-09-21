from dataclasses import field
from typing import Any, Callable, Optional, Union

from flet.controls.base_control import control, skip_field
from flet.controls.core.column import Column
from flet.controls.core.icon import Icon
from flet.controls.core.row import Row
from flet.controls.core.text import Text
from flet.controls.material.container import Container
from flet.controls.material.dropdown import Dropdown, DropdownOption
from flet.controls.material.icon_button import IconButton
from flet.controls.material.icons import Icons
from flet.hardware.serial import SerialPortInfo, list_serial_ports

__all__ = ["DeviceSelector"]


@control("Container")
class DeviceSelector(Container):
    """
    A specialized hardware dropdown that auto-populates and monitors connected serial ports.
    """

    selected_port: Optional[str] = None
    """Currently selected serial port path (e.g. '/dev/ttyUSB0', 'COM3')."""

    auto_refresh: bool = True
    """Whether to periodically check system ports for plug/unplug events."""

    refresh_interval: float = 2.0
    """Polling interval in seconds when auto_refresh is enabled."""

    vid_filter: Optional[list[int]] = None
    """Optional list of USB Vendor IDs (VID) to filter by."""

    pid_filter: Optional[list[int]] = None
    """Optional list of USB Product IDs (PID) to filter by."""

    chip_filter: Optional[Union[str, list[str]]] = None
    """Filter ports by chip or microcontroller type (e.g. 'esp32', 'rp2040')."""

    on_device_connected: Optional[Callable[[SerialPortInfo], Any]] = None
    """Callback fired when a new serial device is detected."""

    on_device_disconnected: Optional[Callable[[SerialPortInfo], Any]] = None
    """Callback fired when an active serial device is disconnected."""

    _ports_cache: list[SerialPortInfo] = field(
        default_factory=list, metadata={"skip": True}
    )
    _dropdown_ref: Optional[Dropdown] = field(default=None, metadata={"skip": True})
    _info_badge: Optional[Text] = field(default=None, metadata={"skip": True})
    _refresh_task: Any = skip_field()

    def __post_init__(self, *args):
        super().__post_init__(*args)
        self._build_ui()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_ui(self):
        """Assemble the visual hierarchy for the device selector."""
        self._dropdown_ref = Dropdown(
            hint_text="Select serial port / microcontroller...",
            expand=True,
            on_select=self._handle_selection_change,
            options=[],
        )
        self._info_badge = Text("", size=12, italic=True)

        refresh_btn = IconButton(
            icon=Icons.REFRESH,
            tooltip="Scan serial ports",
            on_click=lambda _: self.refresh(),
        )

        usb_icon = Icon(Icons.USB, tooltip="USB Serial Interface")

        header_row = Row(
            controls=[
                usb_icon,
                self._dropdown_ref,
                refresh_btn,
            ],
            alignment="start",
            vertical_alignment="center",
            spacing=10,
        )

        self.content = Column(
            controls=[
                header_row,
                self._info_badge,
            ],
            spacing=4,
        )

        # Initial port scan
        self.refresh(notify=False)

    @property
    def selected_device(self) -> Optional[SerialPortInfo]:
        """Return the SerialPortInfo of the currently selected port."""
        for p in self._ports_cache:
            if p.device == self.selected_port:
                return p
        return None

    @property
    def ports(self) -> list[SerialPortInfo]:
        """Return the list of currently detected serial ports matching filters."""
        return list(self._ports_cache)

    def _matches_filter(self, port: SerialPortInfo) -> bool:
        """Check if a port matches configured VID/PID and chip filters."""
        if self.vid_filter and port.vid not in self.vid_filter:
            return False
        if self.pid_filter and port.pid not in self.pid_filter:
            return False

        if self.chip_filter:
            chips = (
                [self.chip_filter]
                if isinstance(self.chip_filter, str)
                else self.chip_filter
            )
            matched = False
            for c in chips:
                c_lower = c.lower()
                if (
                    c_lower in ("esp32", "esp8266")
                    and port.is_esp32()
                    or c_lower in ("rp2040", "pico")
                    and port.is_rp2040()
                ):
                    matched = True
                    break
                else:
                    text = f"{port.description or ''} {port.product or ''} {port.manufacturer or ''}".lower()
                    if c_lower in text:
                        matched = True
                        break
            if not matched:
                return False

        return True

    def refresh(self, notify: bool = True) -> list[SerialPortInfo]:
        """Enumerate connected serial ports and update dropdown options."""
        all_ports = list_serial_ports()
        filtered_ports = [p for p in all_ports if self._matches_filter(p)]

        old_devices = {p.device: p for p in self._ports_cache}
        new_devices = {p.device: p for p in filtered_ports}

        # Check for newly connected or disconnected devices
        if notify:
            for dev, p in new_devices.items():
                if dev not in old_devices and self.on_device_connected:
                    self.on_device_connected(p)
            for dev, p in old_devices.items():
                if dev not in new_devices and self.on_device_disconnected:
                    self.on_device_disconnected(p)

        self._ports_cache = filtered_ports

        # Update dropdown options
        options = [
            DropdownOption(
                key=p.device,
                text=p.display_name(),
            )
            for p in filtered_ports
        ]

        if self._dropdown_ref:
            self._dropdown_ref.options = options
            # If current selection disappeared, update selection
            if self.selected_port not in new_devices:
                self.selected_port = (
                    filtered_ports[0].device if filtered_ports else None
                )
            self._dropdown_ref.value = self.selected_port

        self._update_badge()

        self._safe_update()

        return filtered_ports

    def _handle_selection_change(self, e):
        """Called when user changes the dropdown selection."""
        if self._dropdown_ref:
            self.selected_port = self._dropdown_ref.value
        self._update_badge()
        if self.on_change:
            self.on_change(e)
        self._safe_update()

    def _update_badge(self):
        """Update detail badge with chip and hardware info."""
        if not self._info_badge:
            return
        dev = self.selected_device
        if dev:
            parts = []
            if dev.is_esp32():
                parts.append("ESP32 Device")
            elif dev.is_rp2040():
                parts.append("Raspberry Pi Pico / RP2040")
            if dev.manufacturer:
                parts.append(f"Mfg: {dev.manufacturer}")
            if dev.hwid and dev.hwid != "n/a":
                parts.append(f"HWID: {dev.hwid}")
            self._info_badge.value = " | ".join(parts) if parts else dev.device
        else:
            self._info_badge.value = "No serial device connected."
