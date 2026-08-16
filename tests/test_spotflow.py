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


def test_a_job_carries_the_details_its_file_should_wear():
    """Without this the tags are never written: the download runs in another
    process and the Track object does not survive the trip."""
    job = spotflow.jobs_for([match(title="Song")], config.defaults(), Path("/tmp"))[0]
    assert job[spotflow.DETAILS]["title"] == "Song"
    assert job[spotflow.DETAILS]["artists"] == ["X"]


def test_the_details_survive_a_round_trip_through_json():
    import json

    job = spotflow.jobs_for([match(title="Song")], config.defaults(), Path("/tmp"))[0]
    revived = json.loads(json.dumps(job))
    track = spotflow.track_from_details(revived[spotflow.DETAILS])
    assert track.title == "Song"
    assert track.artists == ("X",)


def sample_m4a(tmp_path):
    source = Path(__file__).parent / "fixtures" / "silence.m4a"
    target = tmp_path / "out.m4a"
    target.write_bytes(source.read_bytes())
    return target


def test_apply_tags_writes_them_onto_the_finished_file(tmp_path, monkeypatch):
    from mutagen.mp4 import MP4

    monkeypatch.setattr(spotflow.tagging, "fetch_cover", lambda *a, **k: b"")
    landed = sample_m4a(tmp_path)
    job = spotflow.jobs_for([match(title="Song")], config.defaults(), Path("/tmp"))[0]
    assert spotflow.apply_tags(landed, job, config.defaults()) is True
    assert MP4(landed)["\xa9nam"] == ["Song"]


def test_a_job_without_spotify_details_is_left_alone(tmp_path):
    """Every YouTube download reaches this too, and must pass straight through."""
    landed = sample_m4a(tmp_path)
    assert spotflow.apply_tags(landed, {"url": "https://y.test/1"}, config.defaults()) is False


def test_a_download_that_produced_no_file_is_not_tagged():
    job = spotflow.jobs_for([match()], config.defaults(), Path("/tmp"))[0]
    assert spotflow.apply_tags(None, job, config.defaults()) is False


def test_the_cover_is_fetched_through_the_proxy_when_its_host_is_listed(monkeypatch):
    from dataclasses import replace as dc_replace

    seen = {}
    monkeypatch.setattr(
        spotflow.tagging,
        "fetch_cover",
        lambda url, proxy="", **k: seen.update(url=url, proxy=proxy) or b"",
    )
    monkeypatch.setattr(spotflow.tagging, "apply", lambda *a, **k: True)
    track = Track(title="S", artists=("X",), duration=200, cover="https://i.scdn.co/image/x")
    job = {spotflow.DETAILS: spotflow.details_of(track)}
    cfg = dc_replace(config.defaults(), proxy_domains=("scdn.co",))
    spotflow.apply_tags(Path("/tmp/x.m4a"), job, cfg)
    assert seen["proxy"] == cfg.proxy


def test_a_job_goes_through_the_proxy_when_its_host_is_listed():
    """The search and the download are both YouTube requests. Proxying only
    the search finds the video and then fails to fetch it."""
    from dataclasses import replace as dc_replace

    cfg = dc_replace(config.defaults(), proxy_domains=("youtube.com",))
    m = match(url="https://www.youtube.com/watch?v=abc")
    job = spotflow.jobs_for([m], cfg, Path("/tmp"))[0]
    assert job["proxy"] == cfg.proxy


def test_a_job_is_direct_when_its_host_is_not_listed():
    m = match(url="https://www.youtube.com/watch?v=abc")
    job = spotflow.jobs_for([m], config.defaults(), Path("/tmp"))[0]
    assert job["proxy"] == ""
