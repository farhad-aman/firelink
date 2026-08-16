from pathlib import Path

from . import ytjob
from .theme import glyph
from .youtube import Choices

AUDIO = Choices(video="none", audio="best", subs="off", sub_lang="en", container="m4a")


def needs_review(matches) -> list:
    """The matches a person has to look at before anything downloads.

    A track with nothing found is included even though it cannot be accepted:
    dropping it here would leave a playlist quietly short with nothing said.
    """
    return [m for m in matches if not m.confident]


def jobs_for(matches, cfg, directory: Path) -> list[dict]:
    jobs = []
    for match in matches:
        if not match.pick:
            continue
        job = ytjob.new_job(
            match.pick.candidate.url,
            directory,
            AUDIO,
            proxy="",
            cookies_from=cfg.cookies_from,
        )
        job["outname"] = match.track.filename
        job["title"] = f"{match.track.artist} — {match.track.title}"
        jobs.append(job)
    return jobs


def summarise(queued, skipped, icons: bool = True) -> list[str]:
    lines = [f"  {glyph('🎵', icons)} {len(queued)} queued from Spotify"]
    for match in skipped:
        lines.append(f"  {glyph('⏭', icons)}  skipped  {match.track.title} — no match found")
    return lines
