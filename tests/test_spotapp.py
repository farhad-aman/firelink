from dl import config, spotify
from dl.spotmatch import Candidate, Scored
from dl.spotresolve import Match
from dl.tui import spotadd, spotapp


def a_track(title="T"):
    return spotify.Track(title=title, artists=("X",), duration=200)


def a_match(title="T", confident=True, choices=True):
    picks = []
    if choices:
        picks = [
            Scored(
                candidate=Candidate("https://y.test/1", title, "X - Topic", 200),
                points=90,
                confident=confident,
            )
        ]
    return Match(track=a_track(title), choices=picks)


async def run(monkeypatch, tmp_path, listing, matches, keys=()):
    """Drive the app with the network replaced on both sides."""
    monkeypatch.setattr(spotadd.spotify, "fetch", lambda url, cfg=None, timeout=0: listing)
    monkeypatch.setattr(spotadd.spotresolve, "resolve", lambda tracks, **kw: matches)
    started = []
    monkeypatch.setattr(
        spotadd, "default_spawn", lambda job, state=None, cap=0: started.append(job)
    )
    app = spotapp.SpotifySetupApp(
        config.defaults(), ["https://open.spotify.com/track/x"], state=tmp_path
    )
    async with app.run_test() as pilot:
        for _ in range(4):
            await pilot.pause()
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
    return app, started


async def test_a_confident_batch_never_shows_the_review_screen(monkeypatch, tmp_path):
    """The whole reason a single track stays one keypress."""
    listing = spotify.Listing([a_track()], "track", False)
    app, started = await run(monkeypatch, tmp_path, listing, [a_match()])
    assert app.reviewed is False
    assert len(started) == 1


async def test_a_doubtful_match_stops_for_review(monkeypatch, tmp_path):
    listing = spotify.Listing([a_track()], "track", False)
    app, started = await run(
        monkeypatch, tmp_path, listing, [a_match(confident=False)], keys=["enter"]
    )
    assert app.reviewed is True
    assert len(started) == 1


async def test_cancelling_the_review_queues_nothing(monkeypatch, tmp_path):
    listing = spotify.Listing([a_track()], "track", False)
    app, started = await run(
        monkeypatch, tmp_path, listing, [a_match(confident=False)], keys=["escape"]
    )
    assert started == []
    assert app.cancelled is True


async def test_a_truncated_playlist_is_warned_about(monkeypatch, tmp_path):
    """The warning has to be said. A silent partial download is the failure
    this whole flag exists to prevent."""
    listing = spotify.Listing([a_track("A")], "playlist", True)
    app, _ = await run(monkeypatch, tmp_path, listing, [a_match("A")])
    assert any(spotify.TRUNCATION_ADVICE in line for line in app.notes)


async def test_a_listing_that_cannot_be_read_fails_without_a_screen(monkeypatch, tmp_path):
    def boom(url, cfg=None, timeout=0):
        raise spotify.SpotifyUnreadable("page changed")

    monkeypatch.setattr(spotadd.spotify, "fetch", boom)
    app = spotapp.SpotifySetupApp(
        config.defaults(), ["https://open.spotify.com/track/x"], state=tmp_path
    )
    async with app.run_test() as pilot:
        for _ in range(4):
            await pilot.pause()
    assert "page changed" in app.failed


async def test_tracks_with_no_match_are_named_in_the_summary(monkeypatch, tmp_path):
    listing = spotify.Listing([a_track("Gone")], "playlist", False)
    app, started = await run(
        monkeypatch, tmp_path, listing, [a_match("Gone", choices=False)], keys=["s"]
    )
    assert started == []
    assert any("Gone" in line for line in app.lines)
