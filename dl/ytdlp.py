import shutil
import sys
from pathlib import Path

from . import routing, torrent
from .youtube import is_youtube

BINARY = "yt-dlp"

FILE_EXTENSIONS = frozenset(
    {
        "iso", "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "exe", "dmg",
        "pkg", "deb", "rpm", "msi", "img", "bin", "apk", "epub", "pdf",
        "mp4", "mkv", "webm", "avi", "mov", "mp3", "m4a", "flac", "wav",
    }
)

_classes = None


def _load() -> list:
    try:
        from yt_dlp.extractor import gen_extractor_classes
    except ImportError:
        return []
    return [cls for cls in gen_extractor_classes() if cls.IE_NAME != "generic"]


def _extractors() -> list:
    global _classes
    if _classes is None:
        _classes = _load()
    return _classes


def extractor_for(url: str):
    """The extractor yt-dlp would use for this address, or None.

    The generic extractor is left out on purpose: it claims every URL by
    fetching the page and looking for something embedded, so keeping it would
    make every address look like yt-dlp's.
    """
    if not url:
        return None
    for cls in _extractors():
        try:
            if cls.suitable(url):
                return cls
        except (TypeError, ValueError):
            continue
    return None


def return_type(url: str) -> str | None:
    """Whether the extractor yields one item, many, or will not say."""
    found = extractor_for(url)
    return getattr(found, "_RETURN_TYPE", None) if found is not None else None


def working(url: str) -> bool:
    """False only when yt-dlp itself marks the matching extractor broken."""
    found = extractor_for(url)
    return True if found is None else getattr(found, "_WORKING", True)


def _bundled() -> Path:
    return Path(sys.executable).parent / BINARY


def binary() -> str:
    """The yt-dlp to run.

    firelink installs its own, and the copy answering what a URL is has to be
    the copy that fetches it. Leaving it to PATH runs whichever yt-dlp the
    machine happens to have — usually Homebrew's — so the two could drift a
    release apart and disagree about what a site even offers.
    """
    beside = _bundled()
    return str(beside) if beside.exists() else BINARY


def available() -> bool:
    return _bundled().exists() or shutil.which(BINARY) is not None


def looks_like_file(url: str) -> bool:
    """Whether this address plainly names a file to fetch.

    Deliberately narrow: only extensions nothing streams from. A handle may
    carry a dot, so treating any trailing .word as an extension would route a
    profile page to aria2.
    """
    if torrent.is_torrent(url):
        return True
    name = routing.filename_from_url(url)
    if "." not in name:
        return False
    return name.rsplit(".", 1)[-1].lower() in FILE_EXTENSIONS


def handles(url: str) -> bool:
    """Whether yt-dlp owns this address rather than aria2.

    Three tiers, first answer wins. The YouTube tier is not an optimisation:
    youtu.be links carrying ?list= match no extractor at all, so asking
    yt-dlp about one gets the wrong answer.
    """
    if is_youtube(url):
        return True
    if looks_like_file(url):
        return False
    return extractor_for(url) is not None
