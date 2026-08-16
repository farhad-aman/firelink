import pytest

from dl import spotify, spotmatch

pytestmark = pytest.mark.live

TRACK = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"


def test_spotify_still_serves_the_shape_the_parser_expects():
    listing = spotify.fetch(TRACK)
    assert len(listing.tracks) == 1
    track = listing.tracks[0]
    assert track.title
    assert track.artists
    assert track.duration > 0
    assert track.cover.startswith("https://")


def test_an_album_still_lists_its_tracks():
    listing = spotify.fetch("https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv")
    assert len(listing.tracks) > 1
    assert all(t.duration > 0 for t in listing.tracks)
    assert [t.number for t in listing.tracks] == list(range(1, len(listing.tracks) + 1))


def test_a_real_track_still_finds_a_confident_match_on_youtube():
    """The end-to-end claim the feature rests on. If this fails, matching has
    drifted and the review screen will start appearing for everything."""
    track = spotify.fetch(TRACK).tracks[0]
    found = spotmatch.find(track, timeout=90)
    assert found, "YouTube returned nothing at all"
    picked = spotmatch.best(track, found)
    assert picked is not None
    assert picked.confident, f"best was {picked.candidate.uploader} at {picked.candidate.duration}s"
