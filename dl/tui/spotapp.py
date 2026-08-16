import asyncio
from pathlib import Path

from textual.app import App
from textual.widgets import Static

from .. import instance, routing, spotflow, spotify, spotresolve
from ..config import STATE_DIR, Config
from ..theme import glyph, select
from .matchscreen import MatchScreen
from .ytflow import spawn


def music_dir(cfg: Config) -> Path:
    """Where an m4a lands. Routing decides by extension, so the name only has
    to carry the suffix for the audio category to claim it."""
    return routing.resolve("", "track.m4a", cfg).path


class SpotifySetupApp(App):
    """Resolve a Spotify address, confirm what was doubtful, queue the rest."""

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
        self.notes: list[str] = []
        self.lines: list[str] = []
        self.failed = ""
        self.cancelled = False
        self.reviewed = False
        self.queued: list[dict] = []

    def compose(self):
        yield Static("  reading Spotify…", id="spot-status")

    def on_mount(self) -> None:
        self.run_worker(self._start(), exclusive=False)

    async def _start(self) -> None:
        try:
            listing = await asyncio.to_thread(spotify.fetch, self.urls[0], self.cfg)
        except spotify.SpotifyUnreadable as exc:
            self.failed = str(exc)
            self.exit()
            return
        if listing.truncated:
            self.notes.append(
                f"  {glyph('⚠', self.theme_data.icons)}  {spotify.TRUNCATION_ADVICE}"
            )

        def progress(done: int, total: int) -> None:
            self.call_from_thread(self._say, f"  matched {done} of {total}…")

        matches = await asyncio.to_thread(
            spotresolve.resolve,
            listing.tracks,
            proxy=self.cfg.proxy,
            cookies_from=self.cfg.cookies_from,
            progress=progress,
        )
        doubtful = spotflow.needs_review(matches)
        if not doubtful:
            self._queue(matches, matches)
            return
        self.reviewed = True
        confident = [m for m in matches if m.confident]

        def decided(chosen) -> None:
            if chosen is None:
                self.cancelled = True
                self.exit()
                return
            self._queue(confident + list(chosen), matches)

        self.push_screen(MatchScreen(doubtful, confident_count=len(confident)), decided)

    def _say(self, text: str) -> None:
        found = self.query("#spot-status")
        if found:
            found.first(Static).update(text)

    def _queue(self, accepted, considered) -> None:
        """considered is every track the listing held, not just the kept ones.

        A track skipped at the review screen never reaches `accepted`, so
        without the wider list its name is lost and the playlist comes up
        quietly short.
        """
        jobs = spotflow.jobs_for(accepted, self.cfg, music_dir(self.cfg))
        for job in jobs:
            spawn(job, self.state, self.cfg.general.max_concurrent)
        self.queued = jobs
        kept = {match.track for match in accepted if match.pick}
        skipped = [match for match in considered if match.track not in kept]
        self.lines = self.notes + spotflow.summarise(jobs, skipped, self.theme_data.icons)
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
