import asyncio
import contextlib
import inspect
import re
from dataclasses import field
from typing import Any, Callable, Optional, Union

from flet.controls.base_control import control, skip_field
from flet.controls.border import Border, BorderSide
from flet.controls.border_radius import BorderRadius
from flet.controls.colors import Colors
from flet.controls.core.column import Column
from flet.controls.core.list_view import ListView
from flet.controls.core.row import Row
from flet.controls.core.text import Text
from flet.controls.core.text_span import TextSpan
from flet.controls.material.checkbox import Checkbox
from flet.controls.material.container import Container
from flet.controls.material.dropdown import Dropdown, DropdownOption
from flet.controls.material.icon_button import IconButton
from flet.controls.material.icons import Icons
from flet.controls.material.textfield import TextField
from flet.controls.padding import Padding
from flet.controls.text_style import TextStyle
from flet.controls.types import FontWeight

__all__ = ["SerialConsole"]

# ANSI SGR color mapping
ANSI_COLOR_MAP = {
    30: "#000000",  # Black
    31: "#EF5350",  # Red
    32: "#66BB6A",  # Green
    33: "#FFEE58",  # Yellow
    34: "#42A5F5",  # Blue
    35: "#AB47BC",  # Magenta
    36: "#26C6DA",  # Cyan
    37: "#ECEFF1",  # White
    90: "#78909C",  # Bright Black / Grey
    91: "#FF7043",  # Bright Red
    92: "#81C784",  # Bright Green
    93: "#FFF59D",  # Bright Yellow
    94: "#64B5F6",  # Bright Blue
    95: "#BA68C8",  # Bright Magenta
    96: "#4DD0E1",  # Bright Cyan
    97: "#FFFFFF",  # Bright White
}

ANSI_REGEX = re.compile(r"\x1b\[([0-9;]*)m")


def parse_ansi_to_spans(text: str) -> list[TextSpan]:
    """Parse string with ANSI escape codes into list of Flet TextSpan elements."""
    spans: list[TextSpan] = []
    current_color: Optional[str] = None
    current_bold: Optional[FontWeight] = None

    last_idx = 0
    for match in ANSI_REGEX.finditer(text):
        start, end = match.span()
        chunk = text[last_idx:start]
        if chunk:
            spans.append(
                TextSpan(
                    text=chunk,
                    style=TextStyle(
                        color=current_color or "#CCCCCC",
                        weight=current_bold or FontWeight.NORMAL,
                    ),
                )
            )
        last_idx = end

        # Parse codes in sequence
        codes_str = match.group(1)
        if not codes_str or codes_str == "0":
            current_color = None
            current_bold = None
        else:
            for code_part in codes_str.split(";"):
                if not code_part:
                    continue
                try:
                    c = int(code_part)
                    if c == 0:
                        current_color = None
                        current_bold = None
                    elif c == 1:
                        current_bold = FontWeight.BOLD
                    elif c in ANSI_COLOR_MAP:
                        current_color = ANSI_COLOR_MAP[c]
                except ValueError:
                    pass

    trailing = text[last_idx:]
    if trailing:
        spans.append(
            TextSpan(
                text=trailing,
                style=TextStyle(
                    color=current_color or "#CCCCCC",
                    weight=current_bold or FontWeight.NORMAL,
                ),
            )
        )

    return spans if spans else [TextSpan(text=text, style=TextStyle(color="#CCCCCC"))]


@control("Container")
class SerialConsole(Container):
    """
    An auto-scrolling terminal console control with ANSI color rendering,
    buffer truncation limits, and integrated data-entry controls.
    """

    max_lines: int = 500
    """Maximum number of buffered terminal lines before pruning oldest lines."""

    auto_scroll: bool = True
    """Whether the console automatically scrolls to the newest line."""

    font_family: str = "monospace"
    """Font family used for the terminal display."""

    font_size: int = 12
    """Font size of terminal lines."""

    title: str = "SERIAL CONSOLE"
    """Caption shown in the console toolbar."""

    on_send: Optional[Callable[[str], Any]] = None
    """Callback fired when the user submits data through the entry bar."""

    _lines: list[Text] = field(default_factory=list, metadata={"skip": True})
    _list_view: Optional[ListView] = field(default=None, metadata={"skip": True})
    _input_field: Optional[TextField] = field(default=None, metadata={"skip": True})
    _line_ending_dropdown: Optional[Dropdown] = field(
        default=None, metadata={"skip": True}
    )
    _hex_mode_checkbox: Optional[Checkbox] = field(
        default=None, metadata={"skip": True}
    )
    _counter_label: Optional[Text] = field(default=None, metadata={"skip": True})
    _paused: bool = field(default=False, metadata={"skip": True})
    _attached_serial: Any = skip_field()
    _prev_on_data: Any = skip_field()
    _send_tasks: Any = skip_field()

    def __post_init__(self, *args):
        super().__post_init__(*args)
        self._build_ui()

    def _safe_update(self):
        with contextlib.suppress(RuntimeError):
            self.update()

    def _build_ui(self):
        """Construct terminal view, toolbar, and data entry bar."""
        self._counter_label = Text(
            "Lines: 0 / " + str(self.max_lines), size=11, color=Colors.GREY_500
        )

        clear_btn = IconButton(
            icon=Icons.CLEAR_ALL,
            tooltip="Clear console buffer",
            icon_size=18,
            on_click=lambda _: self.clear(),
        )

        self._autoscroll_btn = IconButton(
            icon=Icons.VERTICAL_ALIGN_BOTTOM,
            tooltip="Auto-scroll enabled",
            icon_size=18,
            on_click=self._toggle_autoscroll,
        )

        self._pause_btn = IconButton(
            icon=Icons.PAUSE,
            tooltip="Pause stream updates",
            icon_size=18,
            on_click=self._toggle_pause,
        )

        toolbar = Row(
            controls=[
                Text(
                    self.title,
                    size=12,
                    weight=FontWeight.BOLD,
                    color=Colors.BLUE_GREY_200,
                ),
                Row(
                    controls=[
                        self._counter_label,
                        self._autoscroll_btn,
                        self._pause_btn,
                        clear_btn,
                    ],
                    spacing=2,
                ),
            ],
            alignment="spaceBetween",
            vertical_alignment="center",
        )

        # Terminal scroll area
        self._list_view = ListView(
            controls=self._lines,
            auto_scroll=self.auto_scroll,
            expand=True,
            spacing=1,
        )

        terminal_container = Container(
            content=self._list_view,
            bgcolor="#121212",
            border=Border(
                top=BorderSide(1, "#333333"),
                bottom=BorderSide(1, "#333333"),
                left=BorderSide(1, "#333333"),
                right=BorderSide(1, "#333333"),
            ),
            border_radius=BorderRadius.all(6),
            padding=Padding(left=8, top=6, right=8, bottom=6),
            expand=True,
        )

        # Data entry controls
        self._input_field = TextField(
            hint_text="Enter command / send data...",
            expand=True,
            on_submit=self._handle_send,
            dense=True,
        )

        send_btn = IconButton(
            icon=Icons.SEND,
            tooltip="Send to device",
            on_click=self._handle_send,
        )

        self._line_ending_dropdown = Dropdown(
            options=[
                DropdownOption(key=r"\r\n", text="CRLF (\\r\\n)"),
                DropdownOption(key=r"\n", text="LF (\\n)"),
                DropdownOption(key=r"\r", text="CR (\\r)"),
                DropdownOption(key="none", text="None"),
            ],
            value=r"\r\n",
            width=130,
            dense=True,
        )

        self._hex_mode_checkbox = Checkbox(
            label="HEX",
            value=False,
        )

        entry_bar = Row(
            controls=[
                self._input_field,
                self._line_ending_dropdown,
                self._hex_mode_checkbox,
                send_btn,
            ],
            alignment="start",
            vertical_alignment="center",
            spacing=8,
        )

        self.content = Column(
            controls=[
                toolbar,
                terminal_container,
                entry_bar,
            ],
            spacing=8,
            expand=True,
        )

    def _toggle_autoscroll(self, _):
        self.auto_scroll = not self.auto_scroll
        if self._list_view:
            self._list_view.auto_scroll = self.auto_scroll
        if self._autoscroll_btn:
            self._autoscroll_btn.icon = (
                Icons.VERTICAL_ALIGN_BOTTOM
                if self.auto_scroll
                else Icons.VERTICAL_ALIGN_TOP
            )
            self._autoscroll_btn.tooltip = (
                "Auto-scroll enabled" if self.auto_scroll else "Auto-scroll disabled"
            )
        self._safe_update()

    def _toggle_pause(self, _):
        self._paused = not self._paused
        if self._pause_btn:
            self._pause_btn.icon = Icons.PLAY_ARROW if self._paused else Icons.PAUSE
            self._pause_btn.tooltip = (
                "Resume stream" if self._paused else "Pause stream"
            )
        self._safe_update()

    def append(self, text: Union[str, bytes]):
        """Append incoming serial data to the console with ANSI color parsing."""
        if self._paused:
            return

        if isinstance(text, (bytes, bytearray)):
            str_data = text.decode("utf-8", errors="replace")
        else:
            str_data = str(text)

        # Split into individual lines
        lines = str_data.splitlines()
        if not lines and str_data:
            lines = [str_data]

        for line in lines:
            spans = parse_ansi_to_spans(line)
            line_ctrl = Text(
                spans=spans,
                font_family=self.font_family,
                size=self.font_size,
                selectable=True,
            )
            self._lines.append(line_ctrl)

        # Prune buffer overflow beyond max_lines
        overflow = len(self._lines) - self.max_lines
        if overflow > 0:
            del self._lines[:overflow]

        if self._counter_label:
            self._counter_label.value = f"Lines: {len(self._lines)} / {self.max_lines}"

        self._safe_update()

    def write_line(self, line: str):
        """Append a single line to the console."""
        self.append(line + "\n")

    def clear(self):
        """Clear all buffered terminal lines."""
        self._lines.clear()
        if self._counter_label:
            self._counter_label.value = f"Lines: 0 / {self.max_lines}"
        self._safe_update()

    def get_content(self) -> str:
        """Extract plain-text representation of all lines in the buffer."""
        parts = []
        for line_ctrl in self._lines:
            if line_ctrl.spans:
                parts.append("".join(s.text or "" for s in line_ctrl.spans))
            elif line_ctrl.value:
                parts.append(line_ctrl.value)
        return "\n".join(parts)

    def attach(self, transport: Any):
        """
        Bind a transport (`AsyncSerial`, `BleTransport`, `MqttTransport`, ...) to
        this console for bidirectional streaming.

        Received data is appended to the console and submitted input is written
        to the transport. Any `on_data` handler already set on the transport is
        still called.
        """
        self.detach()
        self._attached_serial = transport
        self._prev_on_data = getattr(transport, "on_data", None)
        prev = self._prev_on_data

        def _on_data(chunk: bytes):
            self.append(chunk)
            if prev:
                return prev(chunk)

        transport.on_data = _on_data

    def attach_serial(self, serial_instance: Any):
        """Alias of [`attach()`][(c).attach] kept for backwards compatibility."""
        self.attach(serial_instance)

    def detach(self):
        """Unbind the currently attached transport, restoring its `on_data`."""
        transport = self._attached_serial
        if transport is not None:
            transport.on_data = self._prev_on_data
        self._attached_serial = None
        self._prev_on_data = None

    async def _send_payload(self, payload: bytes):
        try:
            await self._attached_serial.write(payload)
        except Exception as e:
            self.append(f"\x1b[31m[Error] Send failed: {e}\x1b[0m\n")

    def _schedule(self, coro_fn, *args):
        """Run a coroutine from either an async or a threaded (sync) handler."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            page = None
            with contextlib.suppress(RuntimeError):
                page = self.page
            if page is not None:
                page.run_task(coro_fn, *args)
            else:
                self.append(
                    "\x1b[33m[Warning] Console is not on a page; cannot send.\x1b[0m\n"
                )
            return
        if self._send_tasks is None:
            self._send_tasks = set()
        task = asyncio.ensure_future(coro_fn(*args))
        self._send_tasks.add(task)
        task.add_done_callback(self._send_tasks.discard)

    def _handle_send(self, _):
        """Process send action from input field or button."""
        if not self._input_field or not self._input_field.value:
            return

        text = self._input_field.value
        self._input_field.value = ""

        # Parse line ending
        le_val = (
            self._line_ending_dropdown.value if self._line_ending_dropdown else r"\r\n"
        )
        ending_map = {r"\r\n": "\r\n", r"\n": "\n", r"\r": "\r", "none": ""}
        suffix = ending_map.get(le_val, "\r\n")

        # Check hex mode
        is_hex = self._hex_mode_checkbox.value if self._hex_mode_checkbox else False
        if is_hex:
            try:
                hex_clean = "".join(text.split())
                payload = bytes.fromhex(hex_clean)
            except ValueError:
                self.append(f"\x1b[31m[Error] Invalid HEX sequence: {text}\x1b[0m\n")
                return
        else:
            payload = (text + suffix).encode("utf-8")

        # Echo locally in console (dimmed/cyan)
        self.append(f"\x1b[36m> {text}\x1b[0m\n")

        # Send to attached serial or callback
        if self.on_send:
            result = self.on_send(text)
            if inspect.isawaitable(result):

                async def _await_result():
                    await result

                self._schedule(_await_result)

        if self._attached_serial is not None:
            if self._attached_serial.is_open:
                self._schedule(self._send_payload, payload)
            else:
                self.append("\x1b[33m[Warning] Device is not connected.\x1b[0m\n")

        self._safe_update()
