import asyncio
from pathlib import Path

from .. import routing, spotflow, spotify, spotresolve
from ..config import STATE_DIR, Config
from .matchscreen import MatchScreen
from .ytflow import spawn as default_spawn

SEARCH_HOST = "https://www.youtube.com/"


class SpotifyAdder:
    """Drives one Spotify address from link to queued jobs.

    Read the tracks, match each to a recording, ask about the doubtful ones,
    queue the rest. Lives apart from any one App so the dashboard and the
    command line ask the same questions in the same order — the same contract
    YouTubeAdder follows: the host supplies push_screen and run_worker.
    """

    def __init__(
        self,
        host,
        cfg: Config,
        urls: list[str],
        state: Path | None = None,
        spawn=None,
        progress=None,
    ):
        self.host = host
        self.cfg = cfg
        self.urls = list(urls)
        self.state = state or STATE_DIR
        self._spawn = spawn or default_spawn
        self._progress = progress
        self.notes: list[str] = []
        self.queued: list[dict] = []
        self.skipped: list = []
        self.failed = ""
        self.cancelled = False
        self.reviewed = False
        self._finished = None

    def start(self, finished=None) -> None:
        self._finished = finished
        self.host.run_worker(self._resolve(), exclusive=False)

    async def _resolve(self) -> None:
        try:
            listing = await asyncio.to_thread(spotify.fetch, self.urls[0], self.cfg)
        except spotify.SpotifyUnreadable as exc:
            self.failed = str(exc)
            self._done()
            return
        if listing.truncated:
            self.notes.append(spotify.TRUNCATION_ADVICE)
        if not listing.tracks:
            self.failed = "nothing in it"
            self._done()
            return

        matches = await asyncio.to_thread(
            spotresolve.resolve,
            listing.tracks,
            # The search is a YouTube request, so it follows YouTube's rule
            # rather than Spotify's — and the proxy list decides, not the fact
            # that a proxy is configured.
            proxy=routing.proxy_for(SEARCH_HOST, self.cfg),
            cookies_from=self.cfg.cookies_from,
            progress=self._report,
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
                self._done()
                return
            self._queue(confident + list(chosen), matches)

        self.host.push_screen(MatchScreen(doubtful, confident_count=len(confident)), decided)

    def _report(self, done: int, total: int) -> None:
        if self._progress is None:
            return
        self.host.call_from_thread(self._progress, done, total)

    def _queue(self, accepted, considered) -> None:
        """considered is every track the listing held, not just the kept ones.

        A track skipped at the review screen never reaches `accepted`, so
        without the wider list its name is lost and the playlist comes up
        quietly short.
        """
        jobs = spotflow.jobs_for(accepted, self.cfg, spotflow.music_dir(self.cfg))
        for job in jobs:
            self._spawn(job, self.state, self.cfg.general.max_concurrent)
        self.queued = jobs
        kept = {match.track for match in accepted if match.pick}
        self.skipped = [match for match in considered if match.track not in kept]
        self._done()

    def _done(self) -> None:
        if self._finished is not None:
            self._finished(self)
