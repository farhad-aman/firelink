from dataclasses import replace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

MATCH_HINT = "↑↓ track    → other take    ⏎ accept    s skip    a accept all    esc cancel"


class MatchScreen(ModalScreen[list | None]):
    """Confirm the matches that were not obvious.

    Only doubtful matches reach here. A batch where everything matched
    cleanly must never push this screen, which is what keeps a single track
    to one keypress.

    The arrows carry priority because a focused widget would otherwise
    consume them, the same reason dl/tui/modals.py sets it.
    """

    BINDINGS = [
        Binding("up", "previous_track", "previous", show=False, priority=True),
        Binding("down", "next_track", "next", show=False, priority=True),
        Binding("right", "next_take", "other take", show=False, priority=True),
        Binding("left", "previous_take", "previous take", show=False, priority=True),
        Binding("enter", "accept", "accept", priority=True),
        ("s", "skip", "skip"),
        ("a", "accept_all", "accept all"),
        ("escape", "cancel", "cancel"),
    ]

    def __init__(self, matches: list, confident_count: int = 0):
        super().__init__()
        self.matches = list(matches)
        self.confident_count = confident_count
        self.cursor = 0
        self.takes = [0] * len(self.matches)
        self.decided: dict[int, int | None] = {}

    @property
    def header_text(self) -> str:
        settled = f"{self.confident_count} matched confidently" if self.confident_count else ""
        needing = f"{len(self.matches)} need a look"
        return f"  Spotify   {settled}{'   ' if settled else ''}{needing}"

    def compose(self) -> ComposeResult:
        with Vertical(id="match-box"):
            yield Static(self.header_text, id="match-head")
            yield Static("", id="match-list")
            yield Static(MATCH_HINT, id="match-hint")

    def on_mount(self) -> None:
        self._repaint()

    def _repaint(self) -> None:
        rows = []
        for index, match in enumerate(self.matches):
            mark = "▸" if index == self.cursor else " "
            state = self.decided.get(index, "pending")
            if state is None:
                detail = "skipped"
            elif match.choices:
                take = match.choices[self.takes[index]].candidate
                minutes, seconds = divmod(take.duration, 60)
                detail = f"{minutes}:{seconds:02d}  {take.uploader[:22]}  {take.title[:30]}"
            else:
                detail = "nothing found — will be skipped"
            rows.append(f"  {mark} {match.track.title[:24]:<24}  {detail}")
        listing = self.query("#match-list")
        if listing:
            listing.first(Static).update("\n".join(rows))

    def action_next_track(self) -> None:
        self.cursor = min(self.cursor + 1, len(self.matches) - 1)
        self._repaint()

    def action_previous_track(self) -> None:
        self.cursor = max(self.cursor - 1, 0)
        self._repaint()

    def action_next_take(self) -> None:
        self._cycle(1)

    def action_previous_take(self) -> None:
        self._cycle(-1)

    def _cycle(self, step: int) -> None:
        match = self.matches[self.cursor]
        if not match.choices:
            return
        self.takes[self.cursor] = (self.takes[self.cursor] + step) % len(match.choices)
        self._repaint()

    def action_accept(self) -> None:
        self.decided[self.cursor] = self.takes[self.cursor]
        self._advance()

    def action_skip(self) -> None:
        self.decided[self.cursor] = None
        self._advance()

    def action_accept_all(self) -> None:
        for index in range(len(self.matches)):
            self.decided.setdefault(index, self.takes[index])
        self._finish()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _advance(self) -> None:
        if len(self.decided) >= len(self.matches):
            self._finish()
            return
        while self.cursor in self.decided:
            self.cursor = (self.cursor + 1) % len(self.matches)
        self._repaint()

    def _finish(self) -> None:
        chosen = []
        for index, match in enumerate(self.matches):
            take = self.decided.get(index)
            if take is None or not match.choices:
                continue
            chosen.append(replace(match, choices=[match.choices[take]]))
        self.dismiss(chosen)
