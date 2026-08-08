from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..config import DEFAULT_NEWEST as NEWEST
from ..format import cells
from .table import escape


class PlaylistScreen(ModalScreen[list[int] | None]):
    """How much of a collection to take.

    Dismisses with the indices to queue, or None for cancel. A collection
    short enough to read is listed so you can tick what you want; a channel
    holding thousands is not a list anyone scrolls, so that keeps the count
    chooser it always had.

    No size is shown either way: a flat listing has none, and getting one
    means extracting every entry first.
    """

    BINDINGS = [
        # SelectionList would otherwise take ⏎ as a toggle, and ⏎ has always
        # meant "take the lot" on this screen.
        Binding("enter", "submit", "queue", priority=True),
        ("escape", "cancel", "cancel"),
        ("a", "all", "all"),
        ("n", "none_or_newest", "none"),
    ]

    def __init__(
        self, title: str, entries: list, newest: int = NEWEST, unavailable: int = 0
    ):
        super().__init__()
        self.collection = title
        self.entries = list(entries)
        self.count = len(self.entries)
        self.newest = newest
        self.unavailable = unavailable

    @property
    def picks_individually(self) -> bool:
        return self.count <= self.newest

    @property
    def offers_newest(self) -> bool:
        return self.count > self.newest

    def all_indices(self) -> list[int]:
        return list(range(self.count))

    def newest_indices(self) -> list[int]:
        return list(range(min(self.newest, self.count)))

    def compose(self) -> ComposeResult:
        with Vertical(id="playlist-box"):
            yield Label("Download a whole collection?", id="playlist-head")
            yield Static(self.summary(), id="playlist-detail")
            if self.picks_individually:
                yield SelectionList[int](
                    *[
                        Selection(escape(entry.title), index, True)
                        for index, entry in enumerate(self.entries)
                    ],
                    id="playlist-entries",
                )
                yield Button("Queue selected  (⏎)", id="selected")
            else:
                yield Button(f"Download all {self.count}  (⏎)", id="all")
                yield Button(f"Newest {self.newest} only  (n)", id="newest")
            yield Button("Cancel  (esc)", id="cancel")

    def summary(self) -> str:
        name = escape(self.collection) if self.collection else "(untitled)"
        if cells(name) > 60:
            name = name[:57] + "…"
        line = f"  {name}\n  {self.count} item{'s' if self.count != 1 else ''}"
        if self.unavailable:
            # Said plainly, because the count on screen will not match the
            # one the site shows and that looks like dl losing some.
            line += f"\n  {self.unavailable} more are private or deleted"
        return line

    def _selected(self) -> list[int]:
        return sorted(self.query_one(SelectionList).selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "selected":
            self.dismiss(self._selected())
        elif event.button.id == "all":
            self.dismiss(self.all_indices())
        elif event.button.id == "newest":
            self.dismiss(self.newest_indices())
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self.dismiss(self._selected() if self.picks_individually else self.all_indices())

    def action_all(self) -> None:
        if self.picks_individually:
            self.query_one(SelectionList).select_all()
            return
        self.dismiss(self.all_indices())

    def action_none_or_newest(self) -> None:
        if self.picks_individually:
            self.query_one(SelectionList).deselect_all()
            return
        self.dismiss(self.newest_indices())
