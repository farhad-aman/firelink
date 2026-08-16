import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import spotmatch

WORKERS = 4
BACKOFF = 5
RETRIES = 1


@dataclass(frozen=True)
class Match:
    track: object
    choices: list

    @property
    def pick(self):
        return self.choices[0] if self.choices else None

    @property
    def confident(self) -> bool:
        return bool(self.choices) and self.choices[0].confident


def resolve(
    tracks,
    proxy="",
    cookies_from="",
    workers=WORKERS,
    progress=None,
    finder=None,
    backoff=BACKOFF,
):
    """A match for every track, best candidate first, in the original order.

    Bounded concurrency rather than a delay between searches: a long playlist
    finishes in minutes without opening a connection per track.
    """
    items = list(tracks)
    if not items:
        return []
    search = finder or (lambda track: spotmatch.find(track, proxy, cookies_from))
    done = 0

    def one(track):
        candidates = []
        for attempt in range(RETRIES + 1):
            try:
                candidates = search(track)
                break
            except spotmatch.Throttled:
                # The track is fine and the pace is not, so waiting is the
                # whole fix. Giving up here would lose a track to a problem
                # that clears itself in a second.
                if attempt < RETRIES:
                    time.sleep(backoff)
            except Exception:
                break
        return Match(track=track, choices=spotmatch.rank(track, candidates))

    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for match in pool.map(one, items):
            results.append(match)
            done += 1
            if progress is not None:
                progress(done, len(items))
    return results
