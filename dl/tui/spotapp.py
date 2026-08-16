from pathlib import Path

from textual.app import App
from textual.widgets import Static

from .. import instance, spotflow
from ..config import STATE_DIR, Config
from ..theme import glyph, select
from .spotadd import SpotifyAdder


class SpotifySetupApp(App):
    """Asks what a Spotify link holds, then queues it, one link at a time."""

    CSS = """
    Screen { align: center middle; }
    MatchScreen { align: center middle; }
    #match-box { width: 76; padding: 1 2; border: round $accent; background: $surface; }
    #match-head { text-style: bold; }
    #match-list { height: auto; }
    #match-hint { height: 1; padding-top: 1; text-style: dim; }
    #spot-status { height: auto; padding: 1 2; }
    """

    def __init__(self, cfg: Config, urls: list[str], state: Path | None = None):
        super().__init__()
        self.cfg = cfg
        self.urls = list(urls)
        self.state = state or STATE_DIR
        self.theme_data = select(cfg)
        self.lines: list[str] = []
        self.notes: list[str] = []
        self.failed = ""
        self.cancelled = False
        self.reviewed = False
        self.queued: list[dict] = []
        self.adder = SpotifyAdder(self, cfg, urls, state=self.state, progress=self._say)

    def compose(self):
        yield Static("  reading Spotify…", id="spot-status")

    def on_mount(self) -> None:
        self.adder.start(self._finished)

    def _say(self, done: int, total: int) -> None:
        found = self.query("#spot-status")
        if found:
            found.first(Static).update(f"  matched {done} of {total}…")

    def _finished(self, adder: SpotifyAdder) -> None:
        icons = self.theme_data.icons
        self.failed = adder.failed
        self.cancelled = adder.cancelled
        self.reviewed = adder.reviewed
        self.queued = adder.queued
        self.notes = [f"  {glyph('⚠', icons)}  {note}" for note in adder.notes]
        self.lines = self.notes + spotflow.summarise(adder.queued, adder.skipped, icons)
        self.exit()


def run_spotify(cfg: Config, urls: list[str], state: Path | None = None):
    """Ask, match, queue. Same contract as ytflow.run_youtube.

    A full screen, so it may not open beside the dashboard — and unlike a
    plain download there is nothing queued yet, so this refuses rather than
    standing down.
    """
    where = state or STATE_DIR
    if instance.holder(where):
        return ["  dl is already running — press a in that window to add it"], True
    if not instance.acquire(where):
        return ["  dl is already running"], True
    try:
        app = SpotifySetupApp(cfg, urls, where)
        app.run()
        if app.failed:
            return [f"  {glyph('❌', select(cfg).icons)} {app.failed}"], True
        if app.cancelled:
            return [f"  {glyph('✖', select(cfg).icons)} cancelled — nothing queued"], True
        return app.lines, False
    finally:
        instance.release(where)
