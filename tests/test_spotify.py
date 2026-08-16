import json
from dataclasses import replace
from pathlib import Path

import pytest

from dl import config, spotify

FIXTURES = Path(__file__).parent / "fixtures"


class Fake:
    """The bytes urlopen would have returned."""

    def __init__(self, text: str):
        self._text = text

    def read(self) -> bytes:
        return self._text.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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


def test_it_fetches_the_embed_page_for_the_parsed_kind_and_id(monkeypatch):
    asked = {}

    def fake_open(request, timeout=0):
        asked["url"] = request.full_url
        asked["agent"] = request.get_header("User-agent")
        return Fake(embed_html("spotify_track.json"))

    monkeypatch.setattr(spotify.urllib.request, "urlopen", fake_open)
    listing = spotify.fetch("https://open.spotify.com/track/abc123")
    assert asked["url"] == "https://open.spotify.com/embed/track/abc123"
    assert asked["agent"], "a default urllib agent gets a different page back"
    assert listing.kind == "track"
    assert len(listing.tracks) == 1


def test_a_short_playlist_is_not_flagged_as_cut_short(monkeypatch):
    monkeypatch.setattr(
        spotify.urllib.request,
        "urlopen",
        lambda r, timeout=0: Fake(embed_html("spotify_playlist.json")),
    )
    assert spotify.fetch("https://open.spotify.com/playlist/p1").truncated is False


def test_exactly_fifty_tracks_is_treated_as_probably_cut_short(monkeypatch):
    """The embed page carries no total, so a full page is the only signal
    there is. A false warning costs a sentence; a silent truncation costs
    two thirds of a playlist."""
    entries = [
        {"title": f"t{i}", "subtitle": "a", "duration": 1000} for i in range(spotify.EMBED_LIMIT)
    ]
    page = json.dumps(
        {"props": {"pageProps": {"state": {"data": {"entity": {"name": "p", "trackList": entries}}}}}}
    )
    html = f'<script id="__NEXT_DATA__" type="application/json">{page}</script>'
    monkeypatch.setattr(spotify.urllib.request, "urlopen", lambda r, timeout=0: Fake(html))
    listing = spotify.fetch("https://open.spotify.com/playlist/p1")
    assert listing.truncated is True
    assert len(listing.tracks) == 50


def test_a_single_track_is_never_flagged_as_cut_short(monkeypatch):
    monkeypatch.setattr(
        spotify.urllib.request,
        "urlopen",
        lambda r, timeout=0: Fake(embed_html("spotify_track.json")),
    )
    assert spotify.fetch("https://open.spotify.com/track/abc").truncated is False


def test_an_address_this_cannot_read_says_so_before_any_request(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("should not have made a request")

    monkeypatch.setattr(spotify.urllib.request, "urlopen", explode)
    with pytest.raises(spotify.SpotifyUnreadable):
        spotify.fetch("https://open.spotify.com/episode/abc")


def test_a_network_failure_is_reported_as_unreadable(monkeypatch):
    def boom(*a, **k):
        raise OSError("no route to host")

    monkeypatch.setattr(spotify.urllib.request, "urlopen", boom)
    with pytest.raises(spotify.SpotifyUnreadable, match="no route"):
        spotify.fetch("https://open.spotify.com/track/abc")


def test_the_api_is_not_used_when_no_credentials_are_set(monkeypatch):
    monkeypatch.setattr(
        spotify.urllib.request,
        "urlopen",
        lambda r, timeout=0: Fake(embed_html("spotify_playlist.json")),
    )
    listing = spotify.fetch("https://open.spotify.com/playlist/p1", cfg=config.defaults())
    assert len(listing.tracks) == 3


def api_row(name):
    return {
        "track": {
            "name": name,
            "duration_ms": 1000,
            "artists": [{"name": "A"}],
            "album": {"name": "Alb", "images": [{"url": "u", "width": 640}]},
        }
    }


def test_the_api_reads_every_page_of_a_long_playlist(monkeypatch):
    """The whole point of the credentials: the public page stops at 50 and
    cannot say it did."""
    pages = {
        0: {
            "items": [api_row(f"t{i}") for i in range(100)],
            "total": 150,
            "next": "https://api.spotify.com/v1/playlists/p1/tracks?offset=100",
        },
        100: {
            "items": [api_row(f"t{i}") for i in range(100, 150)],
            "total": 150,
            "next": None,
        },
    }

    def fake_open(request, timeout=0):
        if "accounts.spotify.com" in request.full_url:
            return Fake(json.dumps({"access_token": "t0k", "expires_in": 3600}))
        offset = 100 if "offset=100" in request.full_url else 0
        return Fake(json.dumps(pages[offset]))

    monkeypatch.setattr(spotify.urllib.request, "urlopen", fake_open)
    cfg = replace(config.defaults(), spotify_id="a", spotify_secret="b")
    listing = spotify.fetch("https://open.spotify.com/playlist/p1", cfg=cfg)
    assert len(listing.tracks) == 150
    assert listing.truncated is False


def test_an_api_track_carries_its_album_and_number():
    parsed = spotify.track_from_api(
        {
            "name": "Song",
            "duration_ms": 183000,
            "artists": [{"name": "X"}, {"name": "Y"}],
            "album": {
                "name": "Alb",
                "images": [{"url": "small", "width": 64}, {"url": "big", "width": 640}],
            },
        },
        number=6,
    )
    assert parsed.title == "Song"
    assert parsed.artists == ("X", "Y")
    assert parsed.duration == 183
    assert parsed.album == "Alb"
    assert parsed.number == 6
    assert parsed.cover == "big"


def test_a_playlist_entry_with_no_track_is_skipped():
    """A removed or region-locked entry comes back as a null track. Reading
    it as a Track puts an empty row in the review screen."""
    assert spotify.tracks_from_items([{"track": None}, {"track": {}}]) == []


def test_credentials_the_api_rejects_fall_back_to_the_public_page(monkeypatch):
    """A typo in the config must not make every Spotify link stop working."""

    def fake_open(request, timeout=0):
        if "accounts.spotify.com" in request.full_url:
            raise OSError("401 Unauthorized")
        return Fake(embed_html("spotify_playlist.json"))

    monkeypatch.setattr(spotify.urllib.request, "urlopen", fake_open)
    cfg = replace(config.defaults(), spotify_id="bad", spotify_secret="bad")
    listing = spotify.fetch("https://open.spotify.com/playlist/p1", cfg=cfg)
    assert len(listing.tracks) == 3
