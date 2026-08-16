import json
from pathlib import Path

import pytest

from dl import spotify

FIXTURES = Path(__file__).parent / "fixtures"


def embed_html(name: str) -> str:
    """The page as the parser meets it: JSON inside the script tag."""
    body = (FIXTURES / name).read_text()
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{body}</script></body></html>"
    )


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


def test_a_single_track_page_yields_one_track():
    tracks = spotify.parse_embed(embed_html("spotify_track.json"))
    assert len(tracks) == 1
    assert tracks[0].title == "Never Gonna Give You Up"
    assert tracks[0].artists == ("Rick Astley",)
    assert tracks[0].duration == 213


def test_a_playlist_page_yields_every_track_in_order():
    tracks = spotify.parse_embed(embed_html("spotify_playlist.json"))
    assert [t.title for t in tracks] == ["Animal", "Earrings", "Dai Dai"]
    assert tracks[0].duration == 158


def test_a_playlist_entry_splits_its_artists():
    """The list page gives one subtitle string, not an array, so the split
    happens here or the tags carry both names as a single artist."""
    tracks = spotify.parse_embed(embed_html("spotify_playlist.json"))
    assert tracks[2].artists == ("Shakira", "Burna Boy")


def test_a_playlist_numbers_its_tracks_from_one():
    tracks = spotify.parse_embed(embed_html("spotify_playlist.json"))
    assert [t.number for t in tracks] == [1, 2, 3]


def test_it_takes_the_largest_cover_offered():
    tracks = spotify.parse_embed(embed_html("spotify_track.json"))
    assert tracks[0].cover == "https://i.scdn.co/image/big"


def test_a_page_without_the_data_block_is_an_error_not_an_empty_list():
    """Silence here is the dangerous failure: an empty list looks like an
    empty playlist and would report success having downloaded nothing."""
    with pytest.raises(spotify.SpotifyUnreadable):
        spotify.parse_embed("<html><body>nope</body></html>")


def test_a_data_block_of_the_wrong_shape_is_also_an_error():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props": {"pageProps": {}}}</script>'
    )
    with pytest.raises(spotify.SpotifyUnreadable):
        spotify.parse_embed(html)
