import re
import subprocess
from dataclasses import dataclass

from . import ytdlp

SEARCH_COUNT = 5
SEPARATOR = "\t"
# The title goes last so a tab inside it cannot shift the fields before it.
PRINT_FORMAT = SEPARATOR.join(
    ("%(url)s", "%(duration)s", "%(uploader,channel)s", "%(title)s")
)
NA = "NA"

REJECT_SECONDS = 15
EXACT_SECONDS = 2
CLOSE_SECONDS = 5

TOPIC_SUFFIX = " - Topic"
JUNK = frozenset(
    {
        "live", "remix", "cover", "karaoke", "instrumental", "sped", "slowed",
        "reverb", "nightcore", "8d", "mashup", "acapella", "parody", "reaction",
    }
)

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    uploader: str
    duration: int


@dataclass(frozen=True)
class Scored:
    candidate: Candidate
    points: int
    confident: bool


def _words(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _is_topic(candidate) -> bool:
    return candidate.uploader.endswith(TOPIC_SUFFIX)


def _is_official(track, candidate) -> bool:
    name = candidate.uploader.lower().removesuffix(TOPIC_SUFFIX.lower()).strip()
    return any(name == artist.lower() for artist in track.artists)


def score(track, candidate) -> Scored | None:
    """How well this YouTube result matches the track, or None to reject it.

    Duration is the discriminator and it is checked first: a search for a
    popular song returns adverts, hour-long compilations and radio segments
    whose only reliable difference from the real thing is length.
    """
    if candidate.duration <= 0:
        return None
    gap = abs(candidate.duration - track.duration)
    if gap > REJECT_SECONDS:
        return None

    topic = _is_topic(candidate)
    official = _is_official(track, candidate)
    points = 0
    if topic:
        points += 50
    elif official:
        points += 35
    if gap <= EXACT_SECONDS:
        points += 30
    elif gap <= CLOSE_SECONDS:
        points += 15

    wanted = _words(track.title)
    offered = _words(candidate.title)
    if wanted:
        points += int(20 * len(wanted & offered) / len(wanted))

    intruders = (offered & JUNK) - wanted
    points -= 40 * len(intruders)

    return Scored(
        candidate=candidate,
        points=points,
        confident=gap <= EXACT_SECONDS and (topic or official) and not intruders,
    )


def rank(track, candidates) -> list[Scored]:
    scored = [s for s in (score(track, c) for c in candidates) if s is not None]
    return sorted(scored, key=lambda s: s.points, reverse=True)


def best(track, candidates) -> Scored | None:
    found = rank(track, candidates)
    return found[0] if found else None


class Throttled(Exception):
    """YouTube asked us to slow down. The track is fine; the pace is not."""


THROTTLE_SIGNS = ("HTTP Error 429", "Too Many Requests", "Sign in to confirm")


def search_command(query: str, count: int, proxy: str, cookies_from: str) -> list[str]:
    argv = [
        ytdlp.binary(),
        "--flat-playlist",
        "--skip-download",
        "--no-warnings",
        "--ignore-errors",
    ]
    if proxy:
        argv += ["--proxy", proxy]
    if cookies_from:
        argv += ["--cookies-from-browser", cookies_from]
    argv += ["--print", PRINT_FORMAT, f"ytsearch{count}:{query}"]
    return argv


def parse_candidates(output: str) -> list[Candidate]:
    found = []
    for line in (output or "").splitlines():
        parts = line.split(SEPARATOR)
        if len(parts) < 4:
            continue
        url, duration, uploader = parts[0].strip(), parts[1].strip(), parts[2].strip()
        title = SEPARATOR.join(parts[3:])
        if not url.startswith(("http://", "https://")) or duration in ("", NA):
            continue
        try:
            seconds = int(float(duration))
        except ValueError:
            continue
        found.append(Candidate(url=url, title=title, uploader=uploader, duration=seconds))
    return found


def find(track, proxy="", cookies_from="", count=SEARCH_COUNT, timeout=60) -> list[Candidate]:
    """What YouTube offers for this track. An empty list is a normal answer.

    Throttling is not: it means every remaining track is about to fail for a
    reason that has nothing to do with the track, so it is raised rather than
    flattened into "nothing found".
    """
    try:
        done = subprocess.run(
            search_command(track.query, count, proxy, cookies_from),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    found = parse_candidates(done.stdout)
    if not found and any(sign in (done.stderr or "") for sign in THROTTLE_SIGNS):
        raise Throttled(done.stderr.strip().splitlines()[-1] if done.stderr else "throttled")
    return found
