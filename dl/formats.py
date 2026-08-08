import json
import subprocess
from dataclasses import dataclass

from . import ytdlp

MHTML = "mhtml"


@dataclass(frozen=True)
class Offer:
    """What a URL actually has on offer, as far as yt-dlp can tell."""

    heights: tuple[int, ...] = ()
    bitrates: tuple[int, ...] = ()
    containers: tuple[str, ...] = ()
    subtitles: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.heights and not self.bitrates

    @property
    def audio_only(self) -> bool:
        return bool(self.bitrates) and not self.heights


def usable(fmt: dict) -> bool:
    """Whether this format describes something worth offering.

    Video formats report abr as 0 rather than None, so truthiness rather than
    presence is what separates a real bitrate from a placeholder. Storyboards
    fail this on their own: they carry a height but no stream.
    """
    if fmt.get("ext") == MHTML:
        return False
    return bool(fmt.get("height")) or bool(fmt.get("abr"))


def parse(info: dict) -> Offer:
    """Reduce a `yt-dlp -J` result to the choices worth showing."""
    offered = [f for f in (info.get("formats") or []) if usable(f)]
    heights = sorted({f["height"] for f in offered if f.get("height")}, reverse=True)
    bitrates = sorted({round(f["abr"]) for f in offered if f.get("abr")}, reverse=True)
    containers = sorted({f["ext"] for f in offered if f.get("ext")})
    subtitles = sorted(info.get("subtitles") or {})
    return Offer(tuple(heights), tuple(bitrates), tuple(containers), tuple(subtitles))


def probe_command(url: str, proxy: str, cookies_from: str) -> list[str]:
    argv = [ytdlp.binary(), "-J", "--no-warnings", "--no-playlist"]
    if proxy:
        argv += ["--proxy", proxy]
    if cookies_from:
        argv += ["--cookies-from-browser", cookies_from]
    argv.append(url)
    return argv


def probe(
    url: str, proxy: str = "", cookies_from: str = "", timeout: float = 120
) -> Offer | None:
    """What this URL offers, or None if asking did not work.

    None rather than an empty Offer: the caller shows nothing either way, but
    the two mean different things and only one of them is worth logging.
    """
    try:
        done = subprocess.run(
            probe_command(url, proxy, cookies_from),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if done.returncode != 0:
        return None
    try:
        return parse(json.loads(done.stdout))
    except (json.JSONDecodeError, TypeError):
        return None
