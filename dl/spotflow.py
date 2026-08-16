from pathlib import Path

from . import routing, tagging, ytjob
from .spotify import Track
from .theme import glyph
from .youtube import Choices

AUDIO = Choices(video="none", audio="best", subs="off", sub_lang="en", container="m4a")

# Where a job carries the Spotify metadata its file should end up wearing.
# The job is written to JSON between processes, so this holds plain values
# rather than the Track it came from.
DETAILS = "spotify"


def details_of(track: Track) -> dict:
    return {
        "title": track.title,
        "artists": list(track.artists),
        "album": track.album,
        "number": track.number,
        "cover": track.cover,
    }


def track_from_details(details: dict) -> Track:
    return Track(
        title=str(details.get("title") or ""),
        artists=tuple(details.get("artists") or ()),
        duration=0,
        album=str(details.get("album") or ""),
        number=int(details.get("number") or 0),
        cover=str(details.get("cover") or ""),
    )


def apply_tags(landed: Path | None, job: dict, cfg) -> bool:
    """Write Spotify's details onto a finished file.

    Runs after the download for every job that carried any, and answers False
    for the ones that did not rather than making the caller check first.
    """
    details = job.get(DETAILS)
    if not details or landed is None:
        return False
    track = track_from_details(details)
    cover = tagging.fetch_cover(track.cover, proxy=routing.proxy_for(track.cover, cfg))
    return tagging.apply(landed, track, cover)


def music_dir(cfg) -> Path:
    """Where an m4a lands. Routing decides by extension, so the name only has
    to carry the suffix for the audio category to claim it."""
    return routing.resolve("", "track.m4a", cfg).path


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
            # The search and the download are the same host. Proxying one and
            # not the other finds the video and then cannot fetch it.
            proxy=routing.proxy_for(match.pick.candidate.url, cfg),
            cookies_from=cfg.cookies_from,
        )
        job["outname"] = match.track.filename
        job["title"] = f"{match.track.artist} — {match.track.title}"
        job[DETAILS] = details_of(match.track)
        jobs.append(job)
    return jobs


def skipped_lines(skipped, icons: bool = True) -> list[str]:
    """The tracks nothing was found for, named so a short playlist is visibly
    short rather than quietly so."""
    return [
        f"  {glyph('⏭', icons)}  skipped  {match.track.title} — no match found"
        for match in skipped
    ]
