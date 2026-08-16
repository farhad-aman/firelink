import pytest

from dl import spotify


def test_it_knows_a_spotify_url_from_any_other():
    assert spotify.is_spotify("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert spotify.is_spotify("http://open.spotify.com/album/abc?si=xyz")
    assert not spotify.is_spotify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not spotify.is_spotify("")


def test_it_reads_the_kind_and_id_out_of_the_address():
    assert spotify.parse_url("https://open.spotify.com/track/abc123") == ("track", "abc123")
    assert spotify.parse_url("https://open.spotify.com/album/xyz") == ("album", "xyz")
    assert spotify.parse_url("https://open.spotify.com/playlist/p1?si=q") == ("playlist", "p1")


def test_a_locale_sits_between_the_host_and_the_kind():
    """Spotify hands out links like /intl-de/track/… when the browser is not
    in English. Missing it makes every shared link from a friend abroad fail."""
    assert spotify.parse_url("https://open.spotify.com/intl-de/track/abc") == ("track", "abc")


def test_an_episode_is_not_something_this_downloads():
    assert spotify.parse_url("https://open.spotify.com/episode/abc") is None
    assert spotify.parse_url("https://open.spotify.com/artist/abc") is None


def test_a_uri_works_as_well_as_a_url():
    """The desktop app's right-click copies spotify:track:… rather than a URL."""
    assert spotify.parse_url("spotify:track:abc123") == ("track", "abc123")


def test_a_track_joins_its_artists_for_the_search():
    track = spotify.Track(title="Superhero", artists=("Metro Boomin", "Future"), duration=183)
    assert track.artist == "Metro Boomin, Future"
    assert track.query == "Metro Boomin, Future Superhero"


def test_a_filename_loses_the_characters_a_path_cannot_hold():
    track = spotify.Track(title="A/B: the sequel", artists=("X",), duration=100)
    assert track.filename == "X - A B the sequel.m4a"


def test_a_filename_never_grows_past_what_a_filesystem_takes():
    track = spotify.Track(title="t" * 200, artists=("a" * 200,), duration=100)
    assert len(track.filename) <= 200
    assert track.filename.endswith(".m4a")
