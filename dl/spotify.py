import re
from dataclasses import dataclass
from urllib.parse import urlsplit

HOST = "open.spotify.com"
KINDS = ("track", "album", "playlist")
MAX_NAME = 200

_ILLEGAL = re.compile(r'[/\\:*?"<>|\x00-\x1f]+')
_RUNS = re.compile(r"\s+")
_URI = re.compile(r"^spotify:(track|album|playlist):([A-Za-z0-9]+)$")
_PATH = re.compile(r"^/(?:intl-[a-z-]+/)?(track|album|playlist)/([A-Za-z0-9]+)")


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
