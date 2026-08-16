from pathlib import Path

from dl import config, spotflow
from dl.spotify import Track
from dl.spotmatch import Candidate, Scored
from dl.spotresolve import Match


def match(title="T", url="https://y.test/1", confident=True, choices=True):
    picks = []
    if choices:
        picks = [
            Scored(
                candidate=Candidate(url=url, title=title, uploader="X - Topic", duration=200),
                points=90,
                confident=confident,
            )
        ]
    return Match(track=Track(title=title, artists=("X",), duration=200), choices=picks)


def test_a_job_downloads_audio_only_as_m4a():
    """Video would be a needless download and a re-encode away from the
    audio the file is meant to hold."""
    job = spotflow.jobs_for([match()], config.defaults(), Path("/tmp/music"))[0]
    assert job["choices"]["video"] == "none"
    assert job["choices"]["container"] == "m4a"


def test_a_job_points_at_the_matched_youtube_url_not_the_spotify_one():
    job = spotflow.jobs_for([match(url="https://y.test/abc")], config.defaults(), Path("/tmp"))[0]
    assert job["url"] == "https://y.test/abc"


def test_a_job_carries_the_name_the_file_should_end_up_with():
    job = spotflow.jobs_for([match(title="Song")], config.defaults(), Path("/tmp"))[0]
    assert job["outname"] == "X - Song.m4a"


def test_a_match_with_nothing_chosen_produces_no_job():
    assert spotflow.jobs_for([match(choices=False)], config.defaults(), Path("/tmp")) == []


def test_only_the_doubtful_matches_need_review():
    found = spotflow.needs_review([match(confident=True), match(confident=False)])
    assert len(found) == 1


def test_a_track_with_no_candidates_needs_review_too():
    """It cannot be accepted, but the summary has to name it, and silently
    dropping it would leave a playlist quietly short."""
    assert len(spotflow.needs_review([match(choices=False)])) == 1


def test_a_fully_confident_batch_needs_no_review_at_all():
    assert spotflow.needs_review([match(), match()]) == []


def test_the_summary_names_what_was_skipped_and_why():
    lines = spotflow.summarise([match()], skipped=[match(title="Missing", choices=False)])
    assert any("Missing" in line for line in lines)
    assert any("1" in line for line in lines)
