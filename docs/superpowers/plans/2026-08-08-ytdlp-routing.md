# yt-dlp Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace firelink's six-hostname frozenset with a three-tier decision that asks yt-dlp which URLs are its own, so all 1751 supported sites work, and give collections under 100 items a checkbox list instead of a count chooser.

**Architecture:** A new `dl/ytdlp.py` owns every question about yt-dlp extractors behind a lazy, process-cached import. Routing asks three tiers in order — known YouTube host, file-shaped URL, then yt-dlp — where tier 1 exists for correctness, not speed. Collection detection returns a three-valued answer so the ambiguous 13% resolve through the flat listing that already runs.

**Tech Stack:** Python 3.11+, yt-dlp (new dependency), Textual, pytest.

## Global Constraints

- Python floor is `>=3.11`; do not use syntax newer than that.
- **Write no comments** unless the logic is genuinely unreadable without one — non-obvious *why*, a deliberate deviation that looks like a mistake, or a required marker. No comments restating code, no section banners, no changelog narration. Match the density of the file you are editing.
- Docstrings only on public API surface, and short. None on trivially obvious functions.
- Tests must not touch the network. Extractor lookups are faked.
- `tests/conftest.py` redirects `STATE_DIR` across modules; add any new module holding one to that list.
- Run the suite with `make test`. It is currently 1720 passing; it must stay green.
- Commit after every task.

---

### Task 1: The extractor lookup

**Files:**
- Create: `dl/ytdlp.py`
- Test: `tests/test_ytdlp.py`

**Interfaces:**
- Consumes: nothing
- Produces: `extractor_for(url: str) -> type | None`, `return_type(url: str) -> str | None`, `working(url: str) -> bool`, and the private `_load() -> list` / `_classes` cache that tests patch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ytdlp.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dl.ytdlp'`

- [ ] **Step 3: Write minimal implementation**

Create `dl/ytdlp.py`:

```python
_classes = None


def _load() -> list:
    try:
        from yt_dlp.extractor import gen_extractor_classes
    except ImportError:
        return []
    return [cls for cls in gen_extractor_classes() if cls.IE_NAME != "generic"]


def _extractors() -> list:
    global _classes
    if _classes is None:
        _classes = _load()
    return _classes


def extractor_for(url: str):
    """The extractor yt-dlp would use for this address, or None.

    The generic extractor is left out on purpose: it claims every URL by
    fetching the page and looking for something embedded, so keeping it would
    make every address look like yt-dlp's.
    """
    if not url:
        return None
    for cls in _extractors():
        try:
            if cls.suitable(url):
                return cls
        except (TypeError, ValueError):
            continue
    return None


def return_type(url: str) -> str | None:
    """Whether the extractor yields one item, many, or will not say."""
    found = extractor_for(url)
    return getattr(found, "_RETURN_TYPE", None) if found is not None else None


def working(url: str) -> bool:
    """False only when yt-dlp itself marks the matching extractor broken."""
    found = extractor_for(url)
    return True if found is None else getattr(found, "_WORKING", True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add dl/ytdlp.py tests/test_ytdlp.py
git commit -m "Ask yt-dlp which extractor claims an address"
```

---

### Task 2: The three-tier decision

**Files:**
- Modify: `dl/ytdlp.py`
- Modify: `pyproject.toml:10`
- Test: `tests/test_ytdlp.py`

**Interfaces:**
- Consumes: `extractor_for()` from Task 1; `dl.youtube.is_youtube()`; `dl.torrent.is_torrent()`; `dl.routing.filename_from_url()`
- Produces: `handles(url: str) -> bool`, `looks_like_file(url: str) -> bool`, `FILE_EXTENSIONS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ytdlp.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -v`
Expected: FAIL — `AttributeError: module 'dl.ytdlp' has no attribute 'handles'`

- [ ] **Step 3: Write minimal implementation**

Add to the top of `dl/ytdlp.py`, below the existing imports area:

```python
from . import routing, torrent
from .youtube import is_youtube

FILE_EXTENSIONS = frozenset(
    {
        "iso", "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "exe", "dmg",
        "pkg", "deb", "rpm", "msi", "img", "bin", "apk", "epub", "pdf",
        "mp4", "mkv", "webm", "avi", "mov", "mp3", "m4a", "flac", "wav",
    }
)
```

Add these functions at the end of `dl/ytdlp.py`:

```python
def looks_like_file(url: str) -> bool:
    """Whether this address plainly names a file to fetch.

    Deliberately narrow: only extensions nothing streams from. A handle may
    carry a dot, so treating any trailing .word as an extension would route a
    profile page to aria2.
    """
    if torrent.is_torrent(url):
        return True
    name = routing.filename_from_url(url)
    if "." not in name:
        return False
    return name.rsplit(".", 1)[-1].lower() in FILE_EXTENSIONS


def handles(url: str) -> bool:
    """Whether yt-dlp owns this address rather than aria2.

    Three tiers, first answer wins. The YouTube tier is not an optimisation:
    youtu.be links carrying ?list= match no extractor at all, so asking
    yt-dlp about one gets the wrong answer.
    """
    if is_youtube(url):
        return True
    if looks_like_file(url):
        return False
    return extractor_for(url) is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -v`
Expected: PASS, 21 tests

- [ ] **Step 5: Add the dependency**

Edit `pyproject.toml` line 10:

```toml
dependencies = ["textual>=0.80", "tomlkit>=0.13", "yt-dlp>=2025.1.1"]
```

- [ ] **Step 6: Install and run the whole suite**

Run: `make test`
Expected: PASS, 1741 tests (1720 existing + 21 new)

- [ ] **Step 7: Commit**

```bash
git add dl/ytdlp.py tests/test_ytdlp.py pyproject.toml
git commit -m "Route by asking yt-dlp, with YouTube as the backstop"
```

---

### Task 3: Move the call sites over

**Files:**
- Modify: `dl/__main__.py:191`
- Modify: `dl/tui/app.py:621-622`
- Modify: `dl/watch.py:52`
- Test: `tests/test_ytdlp.py`

**Interfaces:**
- Consumes: `ytdlp.handles()` from Task 2
- Produces: nothing new. `dl/playlist.py` keeps importing `is_youtube` and is not touched.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ytdlp.py`:

```python
def test_a_soundcloud_url_reaches_the_yt_dlp_path(monkeypatch):
    """The whole point: a site that was never in the hostname list."""
    import dl.watch as watch

    monkeypatch.setattr(ytdlp, "_classes", None)
    monkeypatch.setattr(ytdlp, "_load", lambda: [Fake])
    assert watch.ytdlp.handles("https://fake.test/track") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -k soundcloud -v`
Expected: FAIL — `AttributeError: module 'dl.watch' has no attribute 'ytdlp'`

- [ ] **Step 3: Change the three files**

In `dl/__main__.py`, add `ytdlp` to the existing `from . import ...` line, then replace line 191:

```python
        tube = [u for u in urls if ytdlp.handles(u)]
```

In `dl/tui/app.py`, add `ytdlp` to the existing `from .. import ...` line, then replace lines 621-622:

```python
        watches = [url for url in urls if ytdlp.handles(url)]
        direct = [url for url in urls if not ytdlp.handles(url)]
```

In `dl/watch.py`, add `ytdlp` to the existing `from . import ...` line, then replace line 52:

```python
    if ytdlp.handles(value):
```

Leave the `youtube` import in each file — `watch.py` still uses `youtube.DEFAULTS`, and the others may still reference it.

- [ ] **Step 4: Run the whole suite**

Run: `make test`
Expected: PASS, 1742 tests. If any existing test fails, it is asserting old hostname behaviour — read it before changing it, since it may be one of the two traps.

- [ ] **Step 5: Remove any now-unused youtube import**

Run: `~/.local/share/dl/venv/bin/python -c "import ast,sys
for p in ['dl/__main__.py','dl/tui/app.py','dl/watch.py']:
    src=open(p).read()
    if 'youtube.' not in src.split('import',1)[1]:
        print('check for unused youtube import:', p)"`

Remove `youtube` from the import line of any file that no longer references it.

- [ ] **Step 6: Commit**

```bash
git add dl/__main__.py dl/tui/app.py dl/watch.py tests/test_ytdlp.py
git commit -m "Send every site yt-dlp knows down the yt-dlp path"
```

---

### Task 4: Three-valued collection detection

**Files:**
- Modify: `dl/playlist.py:24-44`
- Test: `tests/test_playlist.py`

**Interfaces:**
- Consumes: `ytdlp.return_type()` from Task 1
- Produces: `classify(url: str) -> str` returning `COLLECTION`, `SINGLE` or `UNKNOWN`; the constants `COLLECTION = "collection"`, `SINGLE = "single"`, `UNKNOWN = "unknown"`. `is_collection()` stays and keeps its exact current behaviour for YouTube.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playlist.py`:

```python
from dl import ytdlp as ytdlp_module


class OnePer:
    IE_NAME = "one"
    _RETURN_TYPE = "video"
    _WORKING = True

    @classmethod
    def suitable(cls, url):
        return url.startswith("https://one.test/")


class ManyPer:
    IE_NAME = "many"
    _RETURN_TYPE = "playlist"
    _WORKING = True

    @classmethod
    def suitable(cls, url):
        return url.startswith("https://many.test/")


class EitherPer:
    IE_NAME = "either"
    _RETURN_TYPE = "any"
    _WORKING = True

    @classmethod
    def suitable(cls, url):
        return url.startswith("https://either.test/")


@pytest.fixture
def extractors(monkeypatch):
    monkeypatch.setattr(ytdlp_module, "_classes", None)
    monkeypatch.setattr(ytdlp_module, "_load", lambda: [OnePer, ManyPer, EitherPer])
    yield
    ytdlp_module._classes = None


def test_a_youtube_playlist_is_a_collection(extractors):
    url = "https://www.youtube.com/playlist?list=PLxyz"
    assert playlist.classify(url) == playlist.COLLECTION


def test_a_video_copied_from_inside_a_playlist_stays_single(extractors):
    """Regression: yt-dlp resolves this to youtube:tab with return type
    'any', so deferring to it would queue the whole playlist behind one
    video the user copied while watching it."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz&index=4"
    assert playlist.classify(url) == playlist.SINGLE


def test_an_extractor_that_yields_many_is_a_collection(extractors):
    assert playlist.classify("https://many.test/set") == playlist.COLLECTION


def test_an_extractor_that_yields_one_is_single(extractors):
    assert playlist.classify("https://one.test/track") == playlist.SINGLE


def test_an_extractor_that_will_not_say_is_unknown(extractors):
    """Instagram and Reddit sit here: a post may be one item or a carousel."""
    assert playlist.classify("https://either.test/p/abc") == playlist.UNKNOWN


def test_an_unclaimed_url_is_single(extractors):
    assert playlist.classify("https://example.com/a.iso") == playlist.SINGLE


def test_is_collection_still_answers_for_youtube(extractors):
    assert playlist.is_collection("https://www.youtube.com/playlist?list=PL") is True
    assert playlist.is_collection("https://www.youtube.com/watch?v=abc123") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist.py -k classify -v`
Expected: FAIL — `AttributeError: module 'dl.playlist' has no attribute 'classify'`

- [ ] **Step 3: Write minimal implementation**

In `dl/playlist.py`, add `from . import ytdlp` to the imports and append after `is_collection`:

```python
COLLECTION = "collection"
SINGLE = "single"
UNKNOWN = "unknown"


def classify(url: str) -> str:
    """Whether this address means many items, one, or cannot be told apart.

    YouTube keeps its own rules because they are more accurate here than
    yt-dlp's: a watch link carrying &list= resolves to youtube:tab, which
    would expand a whole playlist from one copied video.
    """
    if is_youtube(url):
        return COLLECTION if is_collection(url) else SINGLE
    kind = ytdlp.return_type(url)
    if kind == "playlist":
        return COLLECTION
    if kind is None or kind == "video":
        return SINGLE
    return UNKNOWN
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist.py -v`
Expected: PASS — all existing playlist tests plus 7 new

- [ ] **Step 5: Commit**

```bash
git add dl/playlist.py tests/test_playlist.py
git commit -m "Tell a collection from one item without a hostname list"
```

---

### Task 5: Resolve the ambiguous case by listing it

**Files:**
- Modify: `dl/tui/ytadd.py:67-71` and `dl/tui/ytadd.py:74-116`
- Test: `tests/test_playlist_flow.py`

**Interfaces:**
- Consumes: `playlist.classify()`, `playlist.COLLECTION`, `playlist.UNKNOWN` from Task 4
- Produces: no new public names. `YouTubeAdder._open_collection` gains the single-entry fallthrough.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playlist_flow.py`. That file drives a live `DlApp` through
`run_test()`/`pilot` and uses the fixtures `cfg`, `spawned`, `state` plus
`FakeClient` from `tests.test_app` — follow that pattern exactly; there is no
fake-host helper in this codebase.

```python
AMBIGUOUS = "https://either.test/p/abc"


async def settle(pilot, times=30):
    for _ in range(times):
        await pilot.pause()


async def test_an_ambiguous_url_holding_one_item_skips_the_collection_screen(
    cfg, spawned, monkeypatch
):
    """An Instagram post is 'any' until listed. One entry means it was never
    a collection, and a "download all 1?" screen would be noise."""
    one = [playlist.Entry(AMBIGUOUS, "Just One")]
    monkeypatch.setattr(ytadd.playlist, "expand", lambda *a, **k: playlist.Listing(one, 0))
    monkeypatch.setattr(ytadd.playlist, "classify", lambda url: playlist.UNKNOWN)

    app = DlApp(cfg, FakeClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._accept([AMBIGUOUS])
        await settle(pilot)
        assert not any(
            type(s).__name__ == "PlaylistScreen" for s in app.screen_stack
        )
        assert type(app.screen).__name__ == "YouTubeOptionsScreen"


async def test_an_ambiguous_url_holding_many_shows_the_collection_screen(
    cfg, spawned, monkeypatch
):
    many = [
        playlist.Entry("https://either.test/p/a", "One"),
        playlist.Entry("https://either.test/p/b", "Two"),
    ]
    monkeypatch.setattr(ytadd.playlist, "expand", lambda *a, **k: playlist.Listing(many, 0))
    monkeypatch.setattr(ytadd.playlist, "classify", lambda url: playlist.UNKNOWN)

    app = DlApp(cfg, FakeClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._accept([AMBIGUOUS])
        await settle(pilot)
        assert any(type(s).__name__ == "PlaylistScreen" for s in app.screen_stack)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist_flow.py -k ambiguous -v`
Expected: FAIL — the one-item case still pushes `PlaylistScreen`

- [ ] **Step 3: Write minimal implementation**

In `dl/tui/ytadd.py`, replace the collection test in `start()` (currently line 67):

```python
        collections = [
            url for url in self.urls
            if playlist.classify(url) in (playlist.COLLECTION, playlist.UNKNOWN)
        ]
```

In `_open_collection`, after `entries = listing.entries`, insert:

```python
        if len(entries) == 1:
            self.urls = [entries[0].url]
            self.titles = {entries[0].url: entries[0].title}
            self._ask_options(0)
            return
```

- [ ] **Step 4: Run tests**

Run: `make test`
Expected: PASS, all green

- [ ] **Step 5: Commit**

```bash
git add dl/tui/ytadd.py tests/test_playlist_flow.py
git commit -m "Let the listing settle whether a post was a collection"
```

---

### Task 6: The checkbox list

**Files:**
- Modify: `dl/tui/playlistscreen.py` (whole file)
- Modify: `dl/tui/ytadd.py:97-116`
- Test: `tests/test_playlist_flow.py`

**Interfaces:**
- Consumes: `playlist.Entry` from Task 4's module
- Produces: `PlaylistScreen(title: str, entries: list[Entry], newest: int, unavailable: int)` dismissing with `list[int] | None` — the indices to queue, or None for cancel. **The count is no longer the return value.** Both modes return indices, so `ytadd` has one code path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playlist_flow.py`:

```python
def make_entries(n):
    from dl.playlist import Entry

    return [Entry(f"https://e.test/{i}", f"Item {i}") for i in range(n)]


def test_a_small_collection_offers_a_checkbox_list():
    screen = PlaylistScreen("Set", make_entries(14), newest=100)
    assert screen.picks_individually is True


def test_a_large_collection_keeps_the_count_chooser():
    screen = PlaylistScreen("Channel", make_entries(4812), newest=100)
    assert screen.picks_individually is False


def test_the_threshold_is_the_newest_setting():
    """Exactly at the limit is still small enough to list."""
    assert PlaylistScreen("x", make_entries(100), newest=100).picks_individually is True
    assert PlaylistScreen("x", make_entries(101), newest=100).picks_individually is False


def test_the_count_chooser_returns_every_index():
    screen = PlaylistScreen("Channel", make_entries(300), newest=100)
    assert screen.all_indices() == list(range(300))


def test_the_newest_button_returns_the_first_n_indices():
    screen = PlaylistScreen("Channel", make_entries(300), newest=100)
    assert screen.newest_indices() == list(range(100))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist_flow.py -k "checkbox or threshold or chooser or newest_button" -v`
Expected: FAIL — `TypeError: __init__() takes ... ` because the signature still takes a count

- [ ] **Step 3: Write minimal implementation**

Replace `dl/tui/playlistscreen.py` with:

```python
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..config import DEFAULT_NEWEST as NEWEST
from ..format import cells
from .table import escape


class PlaylistScreen(ModalScreen[list[int] | None]):
    """How much of a collection to take.

    Dismisses with the indices to queue, or None for cancel. Small enough to
    read, and you tick what you want; a channel of thousands is not a list
    anyone scrolls, so that keeps the count chooser it always had.

    No size is shown in either mode: a flat listing has none, and getting one
    means extracting every entry first.
    """

    BINDINGS = [
        # SelectionList would otherwise take ⏎ as a toggle, and ⏎ has always
        # meant "take the lot" on this screen.
        Binding("enter", "submit", "queue", priority=True),
        ("escape", "cancel", "cancel"),
        ("a", "all", "all"),
        ("n", "none_or_newest", "none"),
    ]

    def __init__(
        self, title: str, entries: list, newest: int = NEWEST, unavailable: int = 0
    ):
        super().__init__()
        self.collection = title
        self.entries = list(entries)
        self.count = len(self.entries)
        self.newest = newest
        self.unavailable = unavailable

    @property
    def picks_individually(self) -> bool:
        return self.count <= self.newest

    @property
    def offers_newest(self) -> bool:
        return self.count > self.newest

    def all_indices(self) -> list[int]:
        return list(range(self.count))

    def newest_indices(self) -> list[int]:
        return list(range(min(self.newest, self.count)))

    def compose(self) -> ComposeResult:
        with Vertical(id="playlist-box"):
            yield Label("Download a whole collection?", id="playlist-head")
            yield Static(self.summary(), id="playlist-detail")
            if self.picks_individually:
                yield SelectionList[int](
                    *[
                        Selection(escape(entry.title), index, True)
                        for index, entry in enumerate(self.entries)
                    ],
                    id="playlist-entries",
                )
                yield Button("Queue selected  (⏎)", id="selected")
            else:
                yield Button(f"Download all {self.count}  (⏎)", id="all")
                yield Button(f"Newest {self.newest} only  (n)", id="newest")
            yield Button("Cancel  (esc)", id="cancel")

    def summary(self) -> str:
        name = escape(self.collection) if self.collection else "(untitled)"
        if cells(name) > 60:
            name = name[:57] + "…"
        line = f"  {name}\n  {self.count} item{'s' if self.count != 1 else ''}"
        if self.unavailable:
            line += f"\n  {self.unavailable} more are private or deleted"
        return line

    def _selected(self) -> list[int]:
        return sorted(self.query_one(SelectionList).selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "selected":
            self.dismiss(self._selected())
        elif event.button.id == "all":
            self.dismiss(self.all_indices())
        elif event.button.id == "newest":
            self.dismiss(self.newest_indices())
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self.dismiss(self._selected() if self.picks_individually else self.all_indices())

    def action_all(self) -> None:
        if self.picks_individually:
            self.query_one(SelectionList).select_all()
            return
        self.dismiss(self.all_indices())

    def action_none_or_newest(self) -> None:
        if self.picks_individually:
            self.query_one(SelectionList).deselect_all()
            return
        self.dismiss(self.newest_indices())
```

- [ ] **Step 4: Update the caller**

In `dl/tui/ytadd.py`, replace the `decided` callback and the `push_screen` call in `_open_collection`:

```python
        def decided(chosen: list[int] | None) -> None:
            if not chosen:
                self.cancelled = True
                self._done()
                return
            taken = [entries[index] for index in chosen]
            self.urls = [entry.url for entry in taken]
            self.titles = {entry.url: entry.title for entry in taken}
            self.shared = True
            self._ask_options(0)

        self.host.push_screen(
            PlaylistScreen(
                self.collection_title(url, entries),
                entries,
                self.cfg.newest,
                listing.unavailable,
            ),
            decided,
        )
```

- [ ] **Step 5: Run tests**

Run: `make test`
Expected: PASS, including the existing flow tests **unchanged**.

Nothing constructs `PlaylistScreen` directly except `ytadd.py:109`, so every
existing test reaches it through the live app. They keep passing because two
defaults preserve the old behaviour: every entry starts ticked, and the
priority `enter` binding still means "take the lot". The `listing` fixture's
five entries now render as a checkbox list rather than the count chooser, but
`screen.count == 5`, `escape` cancelling, and `enter` spawning five jobs all
hold.

If a flow test does fail, do not adjust it to match the new screen until you
have confirmed the behaviour change was intended — these tests encode the
collection contract.

- [ ] **Step 6: Commit**

```bash
git add dl/tui/playlistscreen.py dl/tui/ytadd.py tests/test_playlist_flow.py
git commit -m "Tick what you want from a collection you can actually read"
```

---

### Task 7: Surface what yt-dlp knows about itself

**Files:**
- Modify: `dl/ytdlp.py`
- Modify: `dl/tui/ytadd.py:58-72`
- Test: `tests/test_ytdlp.py`

**Interfaces:**
- Consumes: `working()` from Task 1
- Produces: `installed_version() -> str`, `age_days() -> int | None`, `STALE_DAYS = 60`, `staleness_advice() -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ytdlp.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -k "stale or version or age" -v`
Expected: FAIL — `AttributeError: module 'dl.ytdlp' has no attribute 'staleness_advice'`

- [ ] **Step 3: Write minimal implementation**

Add to the top of `dl/ytdlp.py`:

```python
from datetime import date, datetime

STALE_DAYS = 60
```

Add at the end of `dl/ytdlp.py`:

```python
def installed_version() -> str:
    try:
        from yt_dlp.version import __version__
    except ImportError:
        return ""
    return __version__


def age_days() -> int | None:
    """How old the installed yt-dlp is. Its version is its release date."""
    raw = installed_version()
    try:
        released = datetime.strptime(raw[:10], "%Y.%m.%d").date()
    except (ValueError, TypeError):
        return None
    return (date.today() - released).days


def staleness_advice() -> str:
    """Said only when it is old enough to be the reason a site broke."""
    days = age_days()
    if days is None or days < STALE_DAYS:
        return ""
    return f"yt-dlp is {days} days old — sites break silently; run `make install`"
```

- [ ] **Step 4: Warn on a broken extractor before queueing**

In `dl/tui/ytadd.py`, add `ytdlp` to the `from .. import ...` line, then insert into `start()` immediately after the ffmpeg check:

```python
        broken = [url for url in self.urls if not ytdlp.working(url)]
        if broken:
            self.failed = (
                f"yt-dlp marks this site's extractor broken: {broken[0]}"
            )
            self._done()
            return
```

- [ ] **Step 5: Run tests**

Run: `make test`
Expected: PASS, all green

- [ ] **Step 6: Commit**

```bash
git add dl/ytdlp.py dl/tui/ytadd.py tests/test_ytdlp.py
git commit -m "Say when an extractor is broken or yt-dlp has gone stale"
```

---

### Task 8: Drive it against real sites

**Files:**
- None. This task changes no code unless it finds something.

**Interfaces:**
- Consumes: everything above
- Produces: a verified tool, or a bug list

Every real defect in this project so far was found by using it, not by the suite. 1720 tests passed while torrents landed in the wrong folder, the preview closed at handoff, and delete silently did nothing.

- [ ] **Step 1: Confirm the routing decisions offline**

Run:

```bash
~/.local/share/dl/venv/bin/python -c "
from dl import ytdlp, playlist
for u in [
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz&index=4',
  'https://youtu.be/dQw4w9WgXcQ?list=PLxyz',
  'https://www.instagram.com/reel/Cabc123/',
  'https://soundcloud.com/artist/sets/summer',
  'https://www.aparat.com/v/abc123',
  'https://example.com/ubuntu.iso',
  'magnet:?xt=urn:btih:abc',
]:
    print(f'{str(ytdlp.handles(u)):<6} {playlist.classify(u):<11} {u}')
"
```

Expected: the two YouTube list URLs are `True`; `watch?v=…&list=` classifies `single`; `ubuntu.iso` and the magnet are `False`.

- [ ] **Step 2: Run a real single item**

Run `dl <a public Instagram reel URL>` and confirm it queues, downloads, and lands in the right folder.

- [ ] **Step 3: Run a real collection under the threshold**

Run `dl <a SoundCloud set URL>` and confirm the checkbox list appears, titles are readable, `a` and `n` work, and only ticked entries queue.

- [ ] **Step 4: Run a real collection over the threshold**

Run `dl <a YouTube channel URL>` and confirm the count chooser still appears unchanged.

- [ ] **Step 5: Confirm no regression on the trap**

Copy a YouTube video URL from inside a playlist (it will carry `&list=`) and confirm exactly one video queues.

- [ ] **Step 6: Record what happened**

If everything passed, note it in the commit. If anything failed, stop and fix it before claiming the feature works.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Three-tier routing | 2 |
| Tier 1 YouTube-only backstop | 2 |
| Tier 2 file short-circuit | 2 |
| Tier 3 lazy cached import | 1, 2 |
| Collection detection by return type | 4 |
| `any` resolved by probe | 5 |
| Checkbox list under `cfg.newest` | 6 |
| Count chooser above it | 6 |
| `_WORKING` warning | 7 |
| Staleness advice | 7 |
| `yt-dlp` dependency | 2 |
| 4 call sites moved | 3 |
| `dl/youtube.py` left alone | 3 (explicitly) |
| Offline tests, faked extractors | 1, 2, 4 |
| Real runs | 8 |
| Both traps as named regressions | 2, 4 |

No gaps.

**Type consistency:** `handles(str) -> bool`, `extractor_for(str) -> type | None`, `return_type(str) -> str | None`, `working(str) -> bool`, `classify(str) -> str`, `PlaylistScreen.dismiss(list[int] | None)` — used identically in every task that references them. `PlaylistScreen` takes `entries` in Tasks 6 and its caller, never a count.

**Error handling not deferred:** missing `yt_dlp` (Task 1), broken extractor (Task 7), unreadable version (Task 7), one-entry ambiguous listing (Task 5). Probe failure and empty collections use the existing `ListingFailed` path, unchanged.
