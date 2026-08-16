import re
from dataclasses import dataclass

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
