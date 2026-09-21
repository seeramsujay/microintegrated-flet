from dataclasses import field
from typing import Optional

from flet.controls.base_control import control
from flet.controls.border import Border, BorderSide
from flet.controls.border_radius import BorderRadius
from flet.controls.colors import Colors
from flet.controls.core.column import Column
from flet.controls.core.icon import Icon
from flet.controls.core.row import Row
from flet.controls.core.text import Text
from flet.controls.material.container import Container
from flet.controls.material.icons import Icons
from flet.controls.material.progress_bar import ProgressBar
from flet.controls.material.progress_ring import ProgressRing
from flet.controls.padding import Padding
from flet.controls.types import FontWeight
from flet.hardware.flasher import FlashProgressUpdate

__all__ = ["FlashProgress"]


@control("Container")
class FlashProgress(Container):
    """
    A dedicated status indicator control displaying flashing stages, write speeds,
    erased sectors, and upload percentages during firmware deployment workflows.
    """

    status: str = "idle"
    """Current stage ('idle', 'connecting', 'erasing', 'writing', 'verifying', 'complete', 'error')."""

    percent: float = 0.0
    """Progress value from 0.0 to 1.0."""

    _title_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _message_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _progress_bar: Optional[ProgressBar] = field(default=None, metadata={"skip": True})
    _icon_container: Optional[Container] = field(default=None, metadata={"skip": True})
    _speed_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _sectors_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _bytes_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _elapsed_label: Optional[Text] = field(default=None, metadata={"skip": True})

    def __post_init__(self, *args):
        super().__post_init__(*args)
        self._build_ui()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_ui(self):
        self._title_label = Text(
            "Ready to Flash",
            size=14,
            weight=FontWeight.BOLD,
            color=Colors.ON_SURFACE,
        )
        self._message_label = Text(
            "Select firmware binary and target port to begin.",
            size=12,
            color=Colors.GREY_400,
        )
        self._icon_container = Container(
            content=Icon(Icons.MEMORY, color=Colors.PRIMARY, size=24),
            width=28,
            height=28,
            alignment="center",
        )

        header_row = Row(
            controls=[
                self._icon_container,
                Column(
                    controls=[
                        self._title_label,
                        self._message_label,
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            vertical_alignment="center",
            spacing=10,
        )

        self._progress_bar = ProgressBar(
            value=0.0,
            height=8,
            border_radius=BorderRadius.all(4),
            color=Colors.PRIMARY,
            bgcolor="#2A2A2A",
        )

        self._speed_label = Text("Speed: 0.0 kB/s", size=11, color=Colors.GREY_400)
        self._sectors_label = Text("Sectors: 0 / 0", size=11, color=Colors.GREY_400)
        self._bytes_label = Text("0 B / 0 B (0%)", size=11, color=Colors.GREY_400)
        self._elapsed_label = Text("Time: 00:00", size=11, color=Colors.GREY_400)

        metrics_row = Row(
            controls=[
                self._speed_label,
                self._sectors_label,
                self._bytes_label,
                self._elapsed_label,
            ],
            alignment="spaceBetween",
        )

        self.padding = Padding.all(12)
        self.border = Border(
            top=BorderSide(1, "#333333"),
            bottom=BorderSide(1, "#333333"),
            left=BorderSide(1, "#333333"),
            right=BorderSide(1, "#333333"),
        )
        self.border_radius = BorderRadius.all(8)
        self.bgcolor = "#1A1A1A"

        self.content = Column(
            controls=[
                header_row,
                self._progress_bar,
                metrics_row,
            ],
            spacing=10,
        )

    def _format_bytes(self, n: int) -> str:
        if n >= 1024 * 1024:
            return f"{n / (1024 * 1024):.2f} MB"
        elif n >= 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n} B"

    def _format_time(self, seconds: float) -> str:
        s = int(seconds)
        m = s // 60
        sec = s % 60
        return f"{m:02d}:{sec:02d}"

    def update_from_event(self, event: FlashProgressUpdate):
        """Update indicators directly from a FlashProgressUpdate event object."""
        self.status = event.status
        self.percent = event.percent

        stage_titles = {
            "idle": "Ready to Flash",
            "connecting": f"Connecting to {event.chip_name or 'Microcontroller'}...",
            "erasing": "Erasing Flash Memory...",
            "writing": f"Flashing Firmware ({int(event.percent * 100)}%)...",
            "verifying": "Verifying Flash Sectors...",
            "complete": "Flashing Complete!",
            "error": "Flashing Failed",
        }

        if self._title_label:
            self._title_label.value = stage_titles.get(
                event.status, event.status.capitalize()
            )
            if event.status == "complete":
                self._title_label.color = Colors.GREEN_400
            elif event.status == "error":
                self._title_label.color = Colors.RED_400
            else:
                self._title_label.color = Colors.ON_SURFACE

        if self._message_label:
            self._message_label.value = event.message

        if self._progress_bar:
            self._progress_bar.value = event.percent
            if event.status == "complete":
                self._progress_bar.color = Colors.GREEN_400
            elif event.status == "error":
                self._progress_bar.color = Colors.RED_400
            else:
                self._progress_bar.color = Colors.PRIMARY

        if self._icon_container:
            if event.status in ("connecting", "erasing", "writing", "verifying"):
                self._icon_container.content = ProgressRing(
                    width=20, height=20, stroke_width=2
                )
            elif event.status == "complete":
                self._icon_container.content = Icon(
                    Icons.CHECK_CIRCLE, color=Colors.GREEN_400, size=24
                )
            elif event.status == "error":
                self._icon_container.content = Icon(
                    Icons.ERROR, color=Colors.RED_400, size=24
                )
            else:
                self._icon_container.content = Icon(
                    Icons.MEMORY, color=Colors.PRIMARY, size=24
                )

        if self._speed_label:
            self._speed_label.value = f"Speed: {event.speed_kbps:.1f} kB/s"

        if self._sectors_label:
            if event.total_sectors > 0:
                self._sectors_label.value = (
                    f"Sectors: {event.erased_sectors} / {event.total_sectors}"
                )
            else:
                self._sectors_label.value = f"Chip: {event.chip_name or 'N/A'}"

        if self._bytes_label:
            pct_int = int(event.percent * 100)
            written = self._format_bytes(event.bytes_written)
            total = self._format_bytes(event.total_bytes)
            self._bytes_label.value = f"{written} / {total} ({pct_int}%)"

        if self._elapsed_label:
            self._elapsed_label.value = f"Time: {self._format_time(event.elapsed_time)}"

        self._safe_update()

    def reset(self):
        """Reset progress back to idle state."""
        self.update_from_event(
            FlashProgressUpdate(status="idle", percent=0.0, message="Ready.")
        )
