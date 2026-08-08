from dataclasses import dataclass

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
