import subprocess

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from .. import duplicates

SCHEMES = ("http://", "https://", "ftp://", "magnet:")


def clipboard_text() -> str:
    try:
        value = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, check=False, timeout=2
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return value if value.startswith(SCHEMES) else ""


def write_clipboard(text: str) -> bool:
    if not text:
        return False
    try:
        done = subprocess.run(
            ["pbcopy"], input=text, text=True, capture_output=True, check=False, timeout=2
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


ARROWS = (
    Binding("down", "next_control", "next", show=False, priority=True),
    Binding("up", "previous_control", "previous", show=False, priority=True),
)

MOVE_HINT = "↑↓ move    ⏎ choose    esc cancel"
ADD_HINT = "↑↓ move    ctrl+s queue    esc cancel"
LIMIT_HINT = "↑↓ move    ⏎ apply    esc cancel"


class ArrowKeys:
    """Up and down move between a dialog's controls.

    priority is not decoration: without it the focused Button consumes the
    arrow keys and the action never runs. The bindings cannot live here
    either — Textual collects BINDINGS from DOMNode subclasses only, so each
    modal splices ARROWS into its own list.
    """

    def action_next_control(self) -> None:
        self.focus_next()

    def action_previous_control(self) -> None:
        self.focus_previous()


class AddUrlModal(ArrowKeys, ModalScreen[list[str] | None]):
    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        Binding("ctrl+s", "queue", "queue", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-box"):
            yield Label("Add downloads — one URL per line")
            yield TextArea(clipboard_text(), id="urls")
            yield Button("Queue", variant="primary", id="ok")
            yield Static(ADD_HINT, id="add-hint")

    def action_next_control(self) -> None:
        """Inside the text, down belongs to the cursor until it reaches the end.

        The end rather than the last line: a clipboard fills the box with one
        line, so the cursor starts on the last line already and leaving there
        would mean never moving through the text at all.
        """
        box = self.query_one("#urls", TextArea)
        if self.focused is box and box.cursor_location != box.document.end:
            box.action_cursor_down()
            return
        self.focus_next()

    def action_queue(self) -> None:
        raw = self.query_one("#urls", TextArea).text
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        self.dismiss(urls or None)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.action_queue()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class SpeedLimitModal(ArrowKeys, ModalScreen[str | None]):
    BINDINGS = [*ARROWS, ("escape", "dismiss_none", "cancel")]

    def __init__(self, current: str):
        super().__init__()
        self.current = "off" if current in ("0", "", "off") else current

    def compose(self) -> ComposeResult:
        with Vertical(id="limit-box"):
            yield Label("Speed limit — e.g. 2M, 500K, or off")
            yield Input(self.current, id="rate")
            yield Button("Apply", variant="primary", id="ok")
            yield Static(LIMIT_HINT, id="limit-hint")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#rate", Input).value.strip())

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.dismiss(self.query_one("#rate", Input).value.strip())

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class DeleteModal(ArrowKeys, ModalScreen[str | None]):
    """Dismisses with 'list', 'disk', or None."""

    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        ("l", "from_list", "from list"),
        ("d", "from_disk", "from disk"),
    ]

    def __init__(self, label: str, has_file: bool):
        super().__init__()
        self.label = label
        self.has_file = has_file

    def compose(self) -> ComposeResult:
        with Vertical(id="delete-box"):
            yield Label(f"Delete {self.label}?")
            yield Button("Remove from list only  (l)", id="list")
            if self.has_file:
                yield Button("Delete file from disk too  (d)", variant="error", id="disk")
            yield Button("Cancel  (esc)", id="cancel")
            yield Static(MOVE_HINT, id="delete-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id if event.button.id in ("list", "disk") else None)

    def action_from_list(self) -> None:
        self.dismiss("list")

    def action_from_disk(self) -> None:
        if self.has_file:
            self.dismiss("disk")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class DuplicateModal(ArrowKeys, ModalScreen[str | None]):
    """Dismisses with a dl.duplicates decision, or None to cancel the batch.

    Which buttons appear depends on the kind of collision: a name that matches
    while the source does not gets a blunt warning, because overwriting there
    destroys a file this download never produced.
    """

    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        ("s", "pick_skip", "skip"),
        ("r", "pick_rename", "rename"),
        ("o", "pick_overwrite", "overwrite"),
        ("d", "pick_download", "download"),
    ]

    def __init__(self, name: str, collision, size_text: str):
        super().__init__()
        self.download_name = name
        self.collision = collision
        self.size_text = size_text

    @property
    def headline(self) -> str:
        if self.collision.kind == duplicates.URL_ONLY:
            return f"⚠  You already downloaded {self.download_name}"
        if self.collision.in_flight:
            return f"⚠  {self.download_name} is already downloading"
        return f"⚠  {self.download_name} already exists"

    @property
    def detail(self) -> str:
        where = f"{self.collision.path}  ({self.size_text})"
        if self.collision.risky_overwrite:
            return f"{where}\n\n‼️  A different URL produced that file — overwriting loses it."
        if self.collision.kind == duplicates.URL_ONLY:
            return f"Same URL, saved earlier at\n{where}"
        return where

    def compose(self) -> ComposeResult:
        with Vertical(id="duplicate-box"):
            yield Label(self.headline, id="duplicate-head")
            yield Label(self.detail, id="duplicate-detail")
            for choice in self.collision.choices:
                yield self._button(choice)
            yield Button("Cancel  (esc)", id="cancel")
            yield Static(MOVE_HINT, id="duplicate-hint")

    def _button(self, choice: str) -> Button:
        if choice == duplicates.SKIP:
            return Button("Skip — do not download  (s)", id=duplicates.SKIP)
        if choice == duplicates.RENAME:
            return Button("Download alongside, renamed  (r)", id=duplicates.RENAME)
        if choice == duplicates.DOWNLOAD:
            return Button("Download anyway  (d)", variant="primary", id=duplicates.DOWNLOAD)
        label = "Overwrite the existing file  (o)"
        if self.collision.in_flight:
            label = "Overwrite — drops the running download  (o)"
        return Button(label, variant="error", id=duplicates.OVERWRITE)

    def _pick(self, choice: str) -> None:
        if choice in self.collision.choices:
            self.dismiss(choice)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id if event.button.id != "cancel" else None)

    def action_pick_skip(self) -> None:
        self._pick(duplicates.SKIP)

    def action_pick_rename(self) -> None:
        self._pick(duplicates.RENAME)

    def action_pick_overwrite(self) -> None:
        self._pick(duplicates.OVERWRITE)

    def action_pick_download(self) -> None:
        self._pick(duplicates.DOWNLOAD)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class ConfirmModal(ArrowKeys, ModalScreen[bool]):
    BINDINGS = [*ARROWS, ("escape", "dismiss_false", "cancel")]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.question)
            yield Button("Yes", variant="error", id="yes")
            yield Button("No", id="no")
            yield Static(MOVE_HINT, id="confirm-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_dismiss_false(self) -> None:
        self.dismiss(False)
