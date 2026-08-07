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
