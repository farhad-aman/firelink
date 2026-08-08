import pytest

from dl import ytdlp


class Fake:
    IE_NAME = "fake"
    _RETURN_TYPE = "video"
    _WORKING = True
    prefix = "https://fake.test/"

    @classmethod
    def suitable(cls, url):
        return url.startswith(cls.prefix)


class FakeList(Fake):
    IE_NAME = "fake:list"
    _RETURN_TYPE = "playlist"
    prefix = "https://fake.test/set/"


class FakeBroken(Fake):
    IE_NAME = "fake:broken"
    _WORKING = False
    prefix = "https://broken.test/"


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", lambda: [FakeList, Fake, FakeBroken])
    yield
    ytdlp._classes = None


def test_a_known_url_finds_its_extractor():
    assert ytdlp.extractor_for("https://fake.test/thing").IE_NAME == "fake"


def test_an_unknown_url_finds_nothing():
    assert ytdlp.extractor_for("https://example.com/a.iso") is None


def test_an_empty_url_finds_nothing():
    assert ytdlp.extractor_for("") is None


def test_the_first_matching_extractor_wins():
    """yt-dlp resolves in list order, and the more specific entry is listed
    first. Picking any other match would send a set to the track extractor."""
    assert ytdlp.extractor_for("https://fake.test/set/x").IE_NAME == "fake:list"


def test_the_return_type_comes_from_the_extractor():
    assert ytdlp.return_type("https://fake.test/set/x") == "playlist"
    assert ytdlp.return_type("https://fake.test/thing") == "video"


def test_an_unknown_url_has_no_return_type():
    assert ytdlp.return_type("https://example.com/a.iso") is None


def test_a_broken_extractor_is_reported():
    assert ytdlp.working("https://broken.test/x") is False


def test_a_healthy_extractor_is_reported():
    assert ytdlp.working("https://fake.test/thing") is True


def test_an_unknown_url_is_not_called_broken():
    """Nothing claims it, so there is no broken extractor to warn about."""
    assert ytdlp.working("https://example.com/a.iso") is True


def test_the_extractor_list_is_built_once(monkeypatch):
    calls = []

    def counted():
        calls.append(1)
        return [Fake]

    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", counted)
    ytdlp.extractor_for("https://fake.test/a")
    ytdlp.extractor_for("https://fake.test/b")
    assert len(calls) == 1


def test_a_missing_yt_dlp_leaves_everything_unclaimed(monkeypatch):
    """Without the module installed the tool still runs; every URL simply
    goes to aria2, which is where it went before any of this existed."""
    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", lambda: [])
    assert ytdlp.extractor_for("https://fake.test/a") is None


def test_a_youtube_url_is_handled_without_asking():
    assert ytdlp.handles("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True


def test_a_youtube_link_carrying_a_list_is_still_handled():
    """Regression: youtu.be/ID?list= matches no extractor at all — every one
    of the 1751 declines it. Tier 3 would send a YouTube link to aria2, which
    would fetch an HTML page. Tier 1 is what stops that."""
    assert ytdlp.handles("https://youtu.be/dQw4w9WgXcQ?list=PLxyz") is True


def test_a_plain_file_is_not_handled():
    assert ytdlp.handles("https://example.com/ubuntu.iso") is False


def test_a_magnet_is_not_handled():
    assert ytdlp.handles("magnet:?xt=urn:btih:abc") is False


def test_a_torrent_file_is_not_handled():
    assert ytdlp.handles("https://example.com/thing.torrent") is False


def test_an_extractor_url_is_handled():
    assert ytdlp.handles("https://fake.test/thing") is True


def test_a_url_with_a_dot_in_its_last_segment_is_not_mistaken_for_a_file():
    """A handle can hold a dot. Treating it as an extension would route the
    profile to aria2 and download an HTML page."""
    assert ytdlp.looks_like_file("https://fake.test/@user.name") is False


def test_a_file_url_short_circuits_before_the_extractor_list(monkeypatch):
    """Tier 2 exists so a plain download never pays to build 1751 classes."""

    def explode():
        raise AssertionError("tier 3 was reached for a plain file")

    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", explode)
    assert ytdlp.handles("https://example.com/ubuntu.iso") is False


def test_a_page_url_is_not_treated_as_a_file():
    assert ytdlp.looks_like_file("https://fake.test/watch") is False


def test_a_trailing_slash_url_is_not_treated_as_a_file():
    assert ytdlp.looks_like_file("https://fake.test/p/Cxyz/") is False


def test_the_bundled_yt_dlp_is_preferred_over_the_one_on_path(monkeypatch, tmp_path):
    """firelink owns its yt-dlp, and the copy answering what a URL is has to
    be the copy that fetches it. PATH would hand back Homebrew's instead."""
    where = tmp_path / "bin"
    where.mkdir()
    (where / "yt-dlp").write_text("")
    monkeypatch.setattr(ytdlp.sys, "executable", str(where / "python"))
    assert ytdlp.binary() == str(where / "yt-dlp")


def test_without_a_bundled_copy_the_name_is_left_to_path(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(ytdlp.sys, "executable", str(empty / "python"))
    assert ytdlp.binary() == "yt-dlp"


def test_a_bundled_copy_counts_as_available(monkeypatch, tmp_path):
    where = tmp_path / "bin"
    where.mkdir()
    (where / "yt-dlp").write_text("")
    monkeypatch.setattr(ytdlp.sys, "executable", str(where / "python"))
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: None)
    assert ytdlp.available() is True


def test_nothing_anywhere_is_not_available(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(ytdlp.sys, "executable", str(empty / "python"))
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: None)
    assert ytdlp.available() is False


def test_the_clipboard_watcher_catches_a_site_that_was_never_listed(monkeypatch):
    """The whole point of the change: six hostnames used to stand between
    firelink and every other site yt-dlp supports."""
    from collections import deque

    from dl import watch

    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", lambda: [Fake])
    monkeypatch.setattr(watch.ytdlp, "available", lambda: True)

    caught = []
    monkeypatch.setattr(watch, "_catch_youtube", lambda url, cfg: caught.append(url) or True)
    watch.poll_once("https://fake.test/track", deque(maxlen=8), None, None)
    assert caught == ["https://fake.test/track"]


def test_the_command_line_sends_an_unlisted_site_to_yt_dlp(monkeypatch):
    from dl import __main__ as entry

    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", lambda: [Fake])
    assert entry.ytdlp.handles("https://fake.test/track") is True
    assert entry.ytdlp.handles("https://example.com/a.iso") is False


def test_a_fresh_yt_dlp_needs_no_advice(monkeypatch):
    monkeypatch.setattr(ytdlp, "age_days", lambda: 3)
    assert ytdlp.staleness_advice() == ""


def test_a_stale_yt_dlp_says_how_to_update(monkeypatch):
    """firelink owns yt-dlp now, so brew upgrade no longer touches it. A
    silent stale copy shows up as sites mysteriously breaking."""
    monkeypatch.setattr(ytdlp, "age_days", lambda: 200)
    advice = ytdlp.staleness_advice()
    assert "make install" in advice
    assert "200" in advice


def test_an_unreadable_version_gives_no_advice(monkeypatch):
    monkeypatch.setattr(ytdlp, "age_days", lambda: None)
    assert ytdlp.staleness_advice() == ""


def test_the_version_date_is_read_from_yt_dlp(monkeypatch):
    monkeypatch.setattr(ytdlp, "installed_version", lambda: "2026.07.04")
    assert ytdlp.age_days() is not None


def test_a_nonsense_version_has_no_age(monkeypatch):
    monkeypatch.setattr(ytdlp, "installed_version", lambda: "unknown")
    assert ytdlp.age_days() is None


def test_the_day_before_the_limit_is_still_quiet(monkeypatch):
    monkeypatch.setattr(ytdlp, "age_days", lambda: ytdlp.STALE_DAYS - 1)
    assert ytdlp.staleness_advice() == ""


def test_yt_dlp_is_declared_with_its_default_extras():
    """Bare `pip install yt-dlp` omits yt-dlp-ejs, which solves YouTube's
    player challenge. Without it YouTube returns storyboard images and
    nothing else, and every download fails with "Requested format is not
    available" — while a Homebrew yt-dlp of the identical version works,
    because that formula bundles the extras."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    declared = tomllib.loads((root / "pyproject.toml").read_text())
    deps = declared["project"]["dependencies"]
    ytdlp_dep = next(d for d in deps if d.startswith("yt-dlp"))
    assert "[default]" in ytdlp_dep, ytdlp_dep
