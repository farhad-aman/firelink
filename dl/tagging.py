import urllib.error
import urllib.request
from pathlib import Path

COVER_AGENT = "Mozilla/5.0"


def fetch_cover(url: str, timeout: float = 20) -> bytes:
    """The cover image, or nothing. Never raises: art is not worth a failure."""
    if not url:
        return b""
    request = urllib.request.Request(url, headers={"User-Agent": COVER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return b""


def apply(path: Path, track, cover: bytes = b"") -> bool:
    """Write Spotify's metadata onto a finished file.

    Returns whether it worked rather than raising. This runs after a download
    has already succeeded, and a missing tag is not a reason to present a
    finished file as a failure.
    """
    try:
        from mutagen.mp4 import MP4, MP4Cover
    except ImportError:
        return False
    target = Path(path)
    if not target.exists():
        return False
    try:
        tags = MP4(target)
        tags["\xa9nam"] = [track.title]
        tags["\xa9ART"] = [track.artist]
        if track.album:
            tags["\xa9alb"] = [track.album]
        if track.number:
            tags["trkn"] = [(track.number, 0)]
        if cover:
            kind = MP4Cover.FORMAT_PNG if cover[:4] == b"\x89PNG" else MP4Cover.FORMAT_JPEG
            tags["covr"] = [MP4Cover(cover, imageformat=kind)]
        tags.save()
    except Exception:
        return False
    return True
