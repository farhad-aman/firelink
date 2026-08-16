import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

HOST = "open.spotify.com"
KINDS = ("track", "album", "playlist")
MAX_NAME = 200

EMBED = "https://open.spotify.com/embed"
EMBED_LIMIT = 50
AGENT = "Mozilla/5.0"
TRUNCATION_ADVICE = (
    f"Spotify's public page gives at most {EMBED_LIMIT} tracks and does not say "
    "how many it held. Set client_id and client_secret under [spotify] in the "
    "config to read the whole thing."
)

_ILLEGAL = re.compile(r'[/\\:*?"<>|\x00-\x1f]+')
_RUNS = re.compile(r"\s+")
_URI = re.compile(r"^spotify:(track|album|playlist):([A-Za-z0-9]+)$")
_PATH = re.compile(r"^/(?:intl-[a-z-]+/)?(track|album|playlist)/([A-Za-z0-9]+)")
_BLOCK = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


class SpotifyUnreadable(Exception):
    """Spotify's page was not in either shape this knows how to read."""


@dataclass(frozen=True)
class Track:
    title: str
    artists: tuple[str, ...]
    duration: int
    album: str = ""
    number: int = 0
    cover: str = ""

    @property
    def artist(self) -> str:
        return ", ".join(self.artists)

    @property
    def query(self) -> str:
        return f"{self.artist} {self.title}"

    @property
    def filename(self) -> str:
        stem = _clean(f"{self.artist} - {self.title}")
        return f"{stem[: MAX_NAME - len('.m4a')].rstrip()}.m4a"


def _clean(text: str) -> str:
    return _RUNS.sub(" ", _ILLEGAL.sub(" ", text)).strip()


def is_spotify(url: str) -> bool:
    return parse_url(url) is not None


def parse_url(url: str) -> tuple[str, str] | None:
    """The kind and id in this address, or None for anything else.

    Episodes and artist pages parse to nothing on purpose: they are Spotify
    addresses this cannot turn into a list of tracks, and claiming them would
    route them away from the error that explains why.
    """
    if not url:
        return None
    uri = _URI.match(url.strip())
    if uri:
        return uri.group(1), uri.group(2)
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if (parts.hostname or "").lower() != HOST:
        return None
    found = _PATH.match(parts.path)
    return (found.group(1), found.group(2)) if found else None


def parse_embed(html: str) -> list[Track]:
    """The tracks on an embed page, single or collection.

    Raises rather than returning nothing when the shape is unfamiliar. An
    empty list is indistinguishable from an empty playlist, and reporting a
    successful download of nothing is worse than an error nobody expected.
    """
    found = _BLOCK.search(html or "")
    if not found:
        raise SpotifyUnreadable("no data block on the page")
    try:
        entity = json.loads(found.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SpotifyUnreadable(f"unfamiliar page shape: {exc}") from None
    cover = _cover(entity)
    listing = entity.get("trackList")
    if isinstance(listing, list) and listing:
        album = str(entity.get("name") or "")
        return [
            Track(
                title=str(item.get("title") or ""),
                artists=_split(str(item.get("subtitle") or "")),
                duration=int(item.get("duration") or 0) // 1000,
                album=album,
                number=index,
                cover=cover,
            )
            for index, item in enumerate(listing, start=1)
        ]
    title = entity.get("title") or entity.get("name")
    if not title:
        raise SpotifyUnreadable("no tracks and no title on the page")
    return [
        Track(
            title=str(title),
            artists=tuple(str(a.get("name", "")) for a in entity.get("artists", []) if a),
            duration=int(entity.get("duration") or 0) // 1000,
            cover=cover,
        )
    ]


@dataclass(frozen=True)
class Listing:
    tracks: list[Track]
    kind: str
    truncated: bool


def api_configured(cfg) -> bool:
    """Both halves, or neither. One alone cannot authenticate."""
    return bool(getattr(cfg, "spotify_id", "") and getattr(cfg, "spotify_secret", ""))


def fetch(url: str, timeout: float = 25) -> Listing:
    """The tracks behind a Spotify address.

    truncated is a guess and says so: a full page is the only evidence
    available, because the response carries no total to compare against.
    """
    parsed = parse_url(url)
    if parsed is None:
        raise SpotifyUnreadable(f"not a Spotify track, album or playlist: {url}")
    kind, spotify_id = parsed
    request = urllib.request.Request(
        f"{EMBED}/{kind}/{spotify_id}", headers={"User-Agent": AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SpotifyUnreadable(str(exc)) from None
    tracks = parse_embed(html)
    return Listing(
        tracks=tracks,
        kind=kind,
        truncated=kind != "track" and len(tracks) >= EMBED_LIMIT,
    )


def _split(subtitle: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in subtitle.split(",") if part.strip())


def _cover(entity: dict) -> str:
    sources = (entity.get("coverArt") or {}).get("sources") or []
    if not sources:
        return ""
    biggest = max(sources, key=lambda s: int(s.get("width") or 0))
    return str(biggest.get("url") or "")
