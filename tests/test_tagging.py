from pathlib import Path

import pytest
from mutagen.mp4 import MP4

from dl import tagging
from dl.spotify import Track

TRACK = Track(
    title="Superhero",
    artists=("Metro Boomin", "Future"),
    duration=183,
    album="HEROES & VILLAINS",
    number=6,
)


def sample(tmp_path: Path) -> Path:
    """A real m4a, because mutagen refuses anything that is not one."""
    source = Path(__file__).parent / "fixtures" / "silence.m4a"
    target = tmp_path / "out.m4a"
    target.write_bytes(source.read_bytes())
    return target


def test_it_writes_the_fields_a_music_library_reads(tmp_path):
    path = sample(tmp_path)
    assert tagging.apply(path, TRACK) is True
    tags = MP4(path)
    assert tags["\xa9nam"] == ["Superhero"]
    assert tags["\xa9ART"] == ["Metro Boomin, Future"]
    assert tags["\xa9alb"] == ["HEROES & VILLAINS"]
    assert tags["trkn"] == [(6, 0)]


def test_a_track_with_no_album_still_gets_its_title_and_artist(tmp_path):
    path = sample(tmp_path)
    bare = Track(title="T", artists=("A",), duration=10)
    assert tagging.apply(path, bare) is True
    assert MP4(path)["\xa9nam"] == ["T"]
    assert "\xa9alb" not in MP4(path)


def test_cover_art_is_embedded_when_it_was_fetched(tmp_path):
    path = sample(tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    tagging.apply(path, TRACK, cover=png)
    assert MP4(path)["covr"]


def test_a_missing_file_is_false_rather_than_an_exception(tmp_path):
    """Tagging runs after the download, and a download can vanish. It must
    never turn a finished job into a crash."""
    assert tagging.apply(tmp_path / "gone.m4a", TRACK) is False


def test_a_file_that_is_not_audio_is_false_rather_than_an_exception(tmp_path):
    junk = tmp_path / "not.m4a"
    junk.write_bytes(b"this is not an m4a")
    assert tagging.apply(junk, TRACK) is False


def test_a_cover_that_cannot_be_fetched_is_empty_not_an_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(tagging.urllib.request, "urlopen", boom)
    assert tagging.fetch_cover("https://i.scdn.co/image/x") == b""


def test_no_cover_url_makes_no_request(monkeypatch):
    monkeypatch.setattr(
        tagging.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("should not have made a request"),
    )
    assert tagging.fetch_cover("") == b""
