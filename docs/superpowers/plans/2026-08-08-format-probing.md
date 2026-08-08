# Format Probing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the yt-dlp options screen from the formats a URL actually offers, instead of a fixed YouTube-shaped ladder, without ever making the user wait on the network.

**Architecture:** A new `dl/formats.py` turns `yt-dlp -J` output into an `Offer` — the heights, bitrates, containers and subtitle languages genuinely on offer. The options screen accepts an `Offer` and narrows its rows to it, behaving exactly as today when it has none. `ytadd` starts the probe in a worker as it pushes the screen and delivers the result only if the screen is still mounted.

**Tech Stack:** Python 3.11+, yt-dlp (`-J`), Textual, pytest.

## Global Constraints

- Python floor is `>=3.11`.
- **Write no comments** unless the logic is genuinely unreadable without one — a non-obvious *why*, a deliberate deviation that looks like a mistake, or a required marker. No comments restating code, no section banners. Match the density of the file being edited.
- Docstrings only on public API surface, and short.
- Tests must not touch the network. Probe output is supplied as fixtures.
- The probe timeout is `cfg.probe_timeout`, the existing setting — do not introduce a new one.
- A failed probe is silent: the screen keeps today's behaviour and shows no error.
- Run the suite with `~/.local/share/dl/venv/bin/python -m pytest -p no:randomly`. It is currently **1774 passing** and must stay green.
- Commit after every task.

---

### Task 1: Reduce a probe result to what is on offer

**Files:**
- Create: `dl/formats.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Offer` (frozen dataclass with `heights: tuple[int, ...]`, `bitrates: tuple[int, ...]`, `containers: tuple[str, ...]`, `subtitles: tuple[str, ...]`), `usable(fmt: dict) -> bool`, `parse(info: dict) -> Offer`, and `Offer.audio_only` / `Offer.empty` properties.

- [ ] **Step 1: Write the failing test**

Create `tests/test_formats.py`. The two fixtures below are the real shapes
captured from a live Instagram reel and SoundCloud track — do not simplify them.

```python
from dl import formats

# A real Instagram reel: one audio format, three renditions stripped of
# metadata, and nine video formats reporting abr as 0 rather than None.
INSTAGRAM = {
    "title": "Video by tinkertwist",
    "formats": [
        {"format_id": "dash-a", "ext": "m4a", "height": None, "abr": 59.135, "vcodec": "none"},
        {"format_id": "1", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "2", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "3", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "dash-b", "ext": "mp4", "height": 640, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-c", "ext": "mp4", "height": 960, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-d", "ext": "mp4", "height": 1280, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-e", "ext": "mp4", "height": 1280, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-f", "ext": "mp4", "height": 1920, "abr": 0, "vcodec": "vp09"},
    ],
}

# A real SoundCloud track: audio only, no heights anywhere.
SOUNDCLOUD = {
    "title": "Houston We Have a Podcast",
    "formats": [
        {"format_id": "hls_mp3", "ext": "mp3", "height": None, "abr": 128, "vcodec": "none"},
        {"format_id": "hls_aac", "ext": "m4a", "height": None, "abr": 96, "vcodec": "none"},
        {"format_id": "hls_opus", "ext": "m4a", "height": None, "abr": 96, "vcodec": "none"},
    ],
}

# What a yt-dlp without yt-dlp-ejs returns for YouTube: storyboards only.
STORYBOARDS = {
    "title": "Some Video",
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "height": 180, "abr": None, "vcodec": "images"},
        {"format_id": "sb1", "ext": "mhtml", "height": 90, "abr": None, "vcodec": "images"},
    ],
}


def test_heights_come_back_largest_first():
    assert formats.parse(INSTAGRAM).heights == (1920, 1280, 960, 640)


def test_repeated_heights_appear_once():
    assert formats.parse(INSTAGRAM).heights.count(1280) == 1


def test_a_zero_bitrate_is_not_offered():
    """Video formats report abr as 0, not None. Without a truthiness check
    the screen would offer "0 kbps" as a quality."""
    assert 0 not in formats.parse(INSTAGRAM).bitrates
    assert formats.parse(INSTAGRAM).bitrates == (59,)


def test_a_track_with_no_video_has_no_heights():
    assert formats.parse(SOUNDCLOUD).heights == ()
    assert formats.parse(SOUNDCLOUD).bitrates == (128, 96)


def test_audio_only_is_bitrates_without_heights():
    assert formats.parse(SOUNDCLOUD).audio_only is True
    assert formats.parse(INSTAGRAM).audio_only is False


def test_containers_come_from_formats_that_describe_something():
    """The renditions named 1, 2 and 3 carry no height and no bitrate, so
    they describe nothing and shape nothing."""
    assert set(formats.parse(SOUNDCLOUD).containers) == {"mp3", "m4a"}
    assert set(formats.parse(INSTAGRAM).containers) == {"m4a", "mp4"}


def test_storyboards_offer_nothing():
    """mhtml storyboards carry a height but no bitrate and no real stream.
    A yt-dlp missing yt-dlp-ejs returns only these for YouTube."""
    offer = formats.parse(STORYBOARDS)
    assert offer.empty is True
    assert offer.heights == ()


def test_an_empty_offer_is_not_audio_only():
    """Knowing nothing is different from knowing there is no video."""
    offer = formats.parse(STORYBOARDS)
    assert offer.empty is True
    assert offer.audio_only is False


def test_subtitles_are_listed_when_present():
    info = dict(SOUNDCLOUD, subtitles={"en": [{}], "fa": [{}]})
    assert set(formats.parse(info).subtitles) == {"en", "fa"}


def test_a_result_without_a_subtitles_key_has_none():
    """Instagram omits the key entirely rather than sending an empty one."""
    assert formats.parse(INSTAGRAM).subtitles == ()


def test_a_result_with_no_formats_is_empty():
    assert formats.parse({"title": "x"}).empty is True


def test_usable_needs_a_height_or_a_bitrate():
    assert formats.usable({"height": 720, "abr": 0}) is True
    assert formats.usable({"height": None, "abr": 128}) is True
    assert formats.usable({"height": None, "abr": None}) is False
    assert formats.usable({"height": None, "abr": 0}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_formats.py -p no:randomly`
Expected: FAIL — `ImportError: cannot import name 'formats' from 'dl'`

- [ ] **Step 3: Write minimal implementation**

Create `dl/formats.py`:

```python
from dataclasses import dataclass

MHTML = "mhtml"


@dataclass(frozen=True)
class Offer:
    """What a URL actually has on offer, as far as yt-dlp can tell."""

    heights: tuple[int, ...] = ()
    bitrates: tuple[int, ...] = ()
    containers: tuple[str, ...] = ()
    subtitles: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.heights and not self.bitrates

    @property
    def audio_only(self) -> bool:
        return bool(self.bitrates) and not self.heights


def usable(fmt: dict) -> bool:
    """Whether this format describes something worth offering.

    Video formats report abr as 0 rather than None, so truthiness rather than
    presence is what separates a real bitrate from a placeholder. Storyboards
    fail this on their own: they carry a height but no stream.
    """
    if fmt.get("ext") == MHTML:
        return False
    return bool(fmt.get("height")) or bool(fmt.get("abr"))


def parse(info: dict) -> Offer:
    """Reduce a `yt-dlp -J` result to the choices worth showing."""
    formats = [f for f in (info.get("formats") or []) if usable(f)]
    heights = sorted({f["height"] for f in formats if f.get("height")}, reverse=True)
    bitrates = sorted({round(f["abr"]) for f in formats if f.get("abr")}, reverse=True)
    containers = sorted({f["ext"] for f in formats if f.get("ext")})
    subtitles = sorted(info.get("subtitles") or {})
    return Offer(tuple(heights), tuple(bitrates), tuple(containers), tuple(subtitles))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_formats.py -p no:randomly`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add dl/formats.py tests/test_formats.py
git commit -m "Read what a URL actually offers out of a probe"
```

---

### Task 2: Ask yt-dlp for it

**Files:**
- Modify: `dl/formats.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: `parse()` from Task 1; `dl.ytdlp.binary()`
- Produces: `probe_command(url: str, proxy: str, cookies_from: str) -> list[str]`, `probe(url: str, proxy: str = "", cookies_from: str = "", timeout: float = 120) -> Offer | None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formats.py`:

```python
import json
import subprocess


def test_the_command_asks_for_json_about_one_item():
    argv = formats.probe_command("https://e.test/x", "", "")
    assert "-J" in argv
    assert "--no-playlist" in argv, "a collection is probed by its first entry, not as a whole"
    assert argv[-1] == "https://e.test/x"


def test_the_command_runs_the_yt_dlp_firelink_installed():
    from pathlib import Path

    assert Path(formats.probe_command("https://e.test/x", "", "")[0]).name == "yt-dlp"


def test_the_command_carries_the_proxy_and_cookies():
    argv = formats.probe_command("https://e.test/x", "http://p:1", "chrome")
    assert argv[argv.index("--proxy") + 1] == "http://p:1"
    assert argv[argv.index("--cookies-from-browser") + 1] == "chrome"


def test_the_command_sends_no_cookies_when_disabled():
    assert "--cookies-from-browser" not in formats.probe_command("https://e.test/x", "", "")


class Done:
    returncode = 0
    stderr = ""

    def __init__(self, payload):
        self.stdout = json.dumps(payload)


def test_probe_returns_the_offer(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done(SOUNDCLOUD))
    assert formats.probe("https://e.test/x").bitrates == (128, 96)


def test_a_failing_probe_says_nothing(monkeypatch):
    """An enhancement that fails should leave the screen exactly as it was."""

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "ERROR: nope"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Failed())
    assert formats.probe("https://e.test/x") is None


def test_unparseable_output_is_no_offer(monkeypatch):
    class Garbage:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Garbage())
    assert formats.probe("https://e.test/x") is None


def test_a_timeout_is_no_offer(monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("yt-dlp", 5)

    monkeypatch.setattr(subprocess, "run", slow)
    assert formats.probe("https://e.test/x") is None


def test_a_missing_yt_dlp_is_no_offer(monkeypatch):
    def missing(*a, **k):
        raise OSError("No such file")

    monkeypatch.setattr(subprocess, "run", missing)
    assert formats.probe("https://e.test/x") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_formats.py -p no:randomly`
Expected: FAIL — `AttributeError: module 'dl.formats' has no attribute 'probe_command'`

- [ ] **Step 3: Write minimal implementation**

Add to the top of `dl/formats.py`:

```python
import json
import subprocess

from . import ytdlp
```

Add at the end of `dl/formats.py`:

```python
def probe_command(url: str, proxy: str, cookies_from: str) -> list[str]:
    argv = [ytdlp.binary(), "-J", "--no-warnings", "--no-playlist"]
    if proxy:
        argv += ["--proxy", proxy]
    if cookies_from:
        argv += ["--cookies-from-browser", cookies_from]
    argv.append(url)
    return argv


def probe(
    url: str, proxy: str = "", cookies_from: str = "", timeout: float = 120
) -> Offer | None:
    """What this URL offers, or None if asking did not work.

    None rather than an empty Offer: the caller shows nothing either way, but
    the two mean different things and only one of them is worth logging.
    """
    try:
        done = subprocess.run(
            probe_command(url, proxy, cookies_from),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if done.returncode != 0:
        return None
    try:
        return parse(json.loads(done.stdout))
    except (json.JSONDecodeError, TypeError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_formats.py -p no:randomly`
Expected: PASS, 22 tests

- [ ] **Step 5: Commit**

```bash
git add dl/formats.py tests/test_formats.py
git commit -m "Ask a site what it has before offering it"
```

---

### Task 3: Narrow the options screen to the offer

**Files:**
- Modify: `dl/tui/ytoptions.py`
- Test: `tests/test_ytoptions.py`

**Interfaces:**
- Consumes: `formats.Offer` from Task 1
- Produces: `YouTubeOptionsScreen(title, choices=DEFAULTS, can_burn=True, offer=None)`, and `apply_offer(offer: Offer) -> None`. `options_for()` and `visible_fields()` keep their existing signatures.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ytoptions.py`, following the construction style already
used in that file. **First extend its imports** — the file currently imports
only `YouTubeOptionsScreen` and `DEFAULTS`:

```python
from dl.formats import Offer
from dl.youtube import VIDEO_CHOICES, Choices
```

Then the tests:

```python

VIDEO_OFFER = Offer(heights=(1920, 1280, 640), bitrates=(59,), containers=("mp4", "m4a"))
AUDIO_OFFER = Offer(heights=(), bitrates=(128, 96), containers=("mp3", "m4a"))


def test_without_an_offer_the_screen_is_unchanged():
    screen = YouTubeOptionsScreen("x")
    assert screen.options_for("video") == VIDEO_CHOICES


def test_an_offer_replaces_the_ladder_with_real_heights():
    screen = YouTubeOptionsScreen("x", offer=VIDEO_OFFER)
    assert screen.options_for("video") == ("best", "1920", "1280", "640", "none")


def test_an_audio_only_offer_hides_the_video_row():
    screen = YouTubeOptionsScreen("x", offer=AUDIO_OFFER)
    assert "video" not in screen.visible_fields()


def test_an_audio_only_offer_hides_subtitles_too():
    """There is no picture to put them on."""
    screen = YouTubeOptionsScreen("x", offer=AUDIO_OFFER)
    assert "subs" not in screen.visible_fields()
    assert "sub_lang" not in screen.visible_fields()


def test_an_audio_only_offer_gives_real_bitrates():
    screen = YouTubeOptionsScreen("x", offer=AUDIO_OFFER)
    assert screen.options_for("audio") == ("best", "128", "96")


def test_an_offer_without_subtitles_hides_the_subtitle_rows():
    screen = YouTubeOptionsScreen("x", offer=VIDEO_OFFER)
    assert "subs" not in screen.visible_fields()


def test_an_offer_with_subtitles_keeps_them():
    offer = Offer(heights=(720,), bitrates=(128,), containers=("mp4",), subtitles=("en", "fa"))
    screen = YouTubeOptionsScreen("x", offer=offer)
    assert "subs" in screen.visible_fields()
    assert screen.options_for("sub_lang") == ("en", "fa")


def test_an_empty_offer_changes_nothing():
    """Knowing nothing is not the same as knowing there is no video."""
    screen = YouTubeOptionsScreen("x", offer=Offer())
    assert screen.options_for("video") == VIDEO_CHOICES
    assert "video" in screen.visible_fields()


def test_a_still_available_choice_survives_narrowing():
    """The probe lands after you may have already chosen. It refines the
    menu; it must not overrule the decision."""
    screen = YouTubeOptionsScreen("x", choices=Choices("1280", "best", "off", "en", "mp4"))
    screen.apply_offer(VIDEO_OFFER)
    assert screen.values["video"] == "1280"


def test_a_vanished_choice_snaps_to_the_nearest():
    screen = YouTubeOptionsScreen("x", choices=Choices("1080", "best", "off", "en", "mp4"))
    screen.apply_offer(VIDEO_OFFER)
    assert screen.values["video"] == "1280"


def test_narrowing_to_audio_only_drops_a_video_choice():
    screen = YouTubeOptionsScreen("x", choices=Choices("1080", "best", "off", "en", "mp4"))
    screen.apply_offer(AUDIO_OFFER)
    assert screen.values["video"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytoptions.py -p no:randomly`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'offer'`

- [ ] **Step 3: Write minimal implementation**

In `dl/tui/ytoptions.py`, add the import:

```python
from ..formats import Offer
```

Replace `__init__` so it accepts an offer:

```python
    def __init__(
        self,
        title: str,
        choices: Choices = DEFAULTS,
        can_burn: bool = True,
        offer: Offer | None = None,
    ):
        super().__init__()
        self.video_title = title
        self.can_burn = can_burn
        self.offer = offer
        self.values = dict(
            video=choices.video,
            audio=choices.audio,
            subs=choices.subs,
            sub_lang=choices.sub_lang,
            container=choices.container,
        )
        self.field = 0
        self.body = ""
        self.head = f"  ▶  {title}"
```

Replace `options_for` and `visible_fields`:

```python
    def options_for(self, field: str) -> tuple[str, ...]:
        known = self.offer if self.offer is not None and not self.offer.empty else None
        if field == "video":
            if known and known.heights:
                return ("best", *(str(h) for h in known.heights), "none")
            return VIDEO_CHOICES
        if field == "audio":
            if known and known.bitrates:
                return ("best", *(str(b) for b in known.bitrates))
            return AUDIO_CHOICES
        if field == "subs":
            return SUB_CHOICES
        if field == "sub_lang":
            return known.subtitles if known and known.subtitles else LANGS
        return AUDIO_CONTAINERS if self.audio_only else VIDEO_CONTAINERS

    def visible_fields(self) -> tuple[str, ...]:
        """Subtitles are meaningless without a picture, and the language only
        matters once subtitles are on.

        Choosing audio-only keeps the video row, so the choice can be undone.
        A site that has no video at all loses the row entirely — there is
        nothing to go back to.
        """
        known = self.offer if self.offer is not None and not self.offer.empty else None
        no_video = known is not None and known.audio_only
        fields = [] if no_video else ["video"]
        fields.append("audio")
        silent = known is not None and not known.subtitles
        if not no_video and not self.audio_only and not silent:
            fields.append("subs")
            if self.values["subs"] != "off":
                fields.append("sub_lang")
        fields.append("container")
        return tuple(fields)
```

That distinction is the whole reason this method is not a lookup table. With
no offer it reproduces today's behaviour exactly: `("video", "audio", "subs",
"container")` by default, and `("video", "audio", "container")` once video is
set to `none`.

Add `apply_offer` and its helper:

```python
    def apply_offer(self, offer: Offer) -> None:
        """Take up what the probe found, without overruling a choice made
        while it was still running."""
        if not self.is_mounted or offer.empty:
            return
        self.offer = offer
        if offer.audio_only:
            self.values["video"] = "none"
        for field in self.FIELDS:
            self.values[field] = self._nearest(field, self.values[field])
        self.field = min(self.field, len(self.visible_fields()) - 1)
        self._repaint()

    def _nearest(self, field: str, current: str) -> str:
        options = self.options_for(field)
        if current in options:
            return current
        numeric = [o for o in options if o.isdigit()]
        if current.isdigit() and numeric:
            return min(numeric, key=lambda o: abs(int(o) - int(current)))
        return options[0]
```

Note the `audio_only` property already reads `self.values["video"] == "none"`,
so setting that value is what makes the audio-only rows take effect.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_ytoptions.py -p no:randomly`
Expected: PASS. If a pre-existing test fails, read it before changing it — it
encodes the screen's contract.

- [ ] **Step 5: Run the whole suite**

Run: `~/.local/share/dl/venv/bin/python -m pytest -p no:randomly`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add dl/tui/ytoptions.py tests/test_ytoptions.py
git commit -m "Offer only the qualities a site actually has"
```

---

### Task 4: Probe in the background while the screen is up

**Files:**
- Modify: `dl/tui/ytadd.py`
- Test: `tests/test_playlist_flow.py`

**Interfaces:**
- Consumes: `formats.probe()` from Task 2, `YouTubeOptionsScreen.apply_offer()` from Task 3
- Produces: no new public names. `YouTubeAdder` gains `_probe_into(screen, url)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playlist_flow.py`:

```python
async def test_the_options_screen_opens_without_waiting_for_the_probe(
    cfg, spawned, monkeypatch
):
    """8-12 seconds is too long to hold the screen shut."""
    import asyncio

    from dl import formats

    async def never(*a, **k):
        await asyncio.sleep(3600)

    monkeypatch.setattr(formats, "probe", lambda *a, **k: None)
    app = DlApp(cfg, FakeClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._accept(["https://youtu.be/abc"])
        await pilot.pause()
        assert type(app.screen).__name__ == "YouTubeOptionsScreen"


async def test_the_offer_reaches_the_open_screen(cfg, spawned, monkeypatch):
    from dl import formats
    from dl.formats import Offer

    monkeypatch.setattr(
        formats, "probe", lambda *a, **k: Offer(heights=(), bitrates=(128, 96),
                                                containers=("mp3",))
    )
    app = DlApp(cfg, FakeClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._accept(["https://youtu.be/abc"])
        for _ in range(40):
            await pilot.pause()
            if getattr(app.screen, "offer", None):
                break
        assert app.screen.offer.audio_only is True
        assert app.screen.options_for("audio") == ("best", "128", "96")


async def test_a_failed_probe_leaves_the_screen_alone(cfg, spawned, monkeypatch):
    from dl import formats

    monkeypatch.setattr(formats, "probe", lambda *a, **k: None)
    app = DlApp(cfg, FakeClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._accept(["https://youtu.be/abc"])
        for _ in range(20):
            await pilot.pause()
        assert app.screen.offer is None
        assert app.screen.options_for("video") == (
            "best", "2160", "1440", "1080", "720", "480", "360", "none",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist_flow.py -k "probe or offer" -p no:randomly`
Expected: FAIL — `AttributeError: 'YouTubeOptionsScreen' object has no attribute 'offer'` on the second test, because nothing delivers one yet.

- [ ] **Step 3: Write minimal implementation**

In `dl/tui/ytadd.py`, add `formats` to the existing `from .. import ...` line.

Replace the body of `_ask_options` that pushes the screen:

```python
        screen = YouTubeOptionsScreen(self._label(url), can_burn=self.can_burn)
        self.host.push_screen(screen, chosen)
        self.host.run_worker(self._probe_into(screen, url), exclusive=False)
```

Add the worker:

```python
    async def _probe_into(self, screen, url: str) -> None:
        """Refine the open screen once the site says what it has.

        Runs beside the screen rather than before it: asking takes eight to
        twelve seconds, which is too long to hold it shut.
        """
        offer = await asyncio.to_thread(
            formats.probe,
            url,
            self._proxy_for(url),
            self.cfg.cookies_from,
            self.cfg.probe_timeout,
        )
        if offer is not None:
            screen.apply_offer(offer)
```

For a collection, `_ask_options(0)` is called with `self.urls` already reduced
to the chosen entries, so `self.urls[0]` is the first entry — the probe covers
the batch without further change.

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/share/dl/venv/bin/python -m pytest tests/test_playlist_flow.py -p no:randomly`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `~/.local/share/dl/venv/bin/python -m pytest -p no:randomly`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add dl/tui/ytadd.py tests/test_playlist_flow.py
git commit -m "Ask what a site offers while you are already choosing"
```

---

### Task 5: Drive it against real sites

**Files:**
- None, unless it finds something.

**Interfaces:**
- Consumes: everything above
- Produces: a verified feature, or a bug list

The YouTube breakage found the day this was written passed 1773 tests. The
suite does not decide whether this works.

- [ ] **Step 1: Confirm the offers offline**

Run:

```bash
~/.local/share/dl/venv/bin/python -c "
from dl import config, formats
cfg = config.load()
for url in ['https://www.instagram.com/reel/DakwbFxtxk4/',
            'https://soundcloud.com/nasa',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ']:
    o = formats.probe(url, cfg.proxy, cfg.cookies_from, 120)
    print(url)
    print('   ', o)
"
```

Expected: SoundCloud reports `audio_only=True` with real bitrates and no
heights. Instagram reports heights `(1920, 1280, 960, 640)`. YouTube reports a
full ladder — if it reports nothing, `yt-dlp-ejs` is missing again.

- [ ] **Step 2: A SoundCloud track in the real UI**

Run `dl https://soundcloud.com/nasa`, pick one track, and watch the options
screen. It must open **immediately**, then within about ten seconds lose its
video row and show real bitrates.

- [ ] **Step 3: A YouTube video**

Run `dl -p "https://www.youtube.com/watch?v=dQw4w9WgXcQ"`. The ladder should
narrow to the heights that video actually has.

- [ ] **Step 4: Choose before the probe lands**

Open the options screen and immediately change the video quality, before the
probe returns. Your choice must survive if that height still exists, and snap
to the nearest if it does not. It must never jump back to a default.

- [ ] **Step 5: Close before the probe lands**

Open the options screen and press escape straight away. Nothing should crash
when the probe returns to a screen that is gone.

- [ ] **Step 6: Record what happened**

If anything failed, stop and fix it before claiming the feature works.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `Offer` dataclass and fields | 1 |
| Usable-format rule, truthy height or abr | 1 |
| `abr: 0` excluded | 1 |
| Storyboards yield an empty offer | 1 |
| Subtitles key may be absent | 1 |
| `probe_command` / `probe` | 2 |
| `probe()` returns None on failure | 2 |
| Uses `cfg.probe_timeout` | 4 |
| Screen unchanged without an offer | 3 |
| Heights replace the ladder | 3 |
| Audio-only hides video and subtitle rows | 3 |
| Empty offer treated as no information | 3 |
| Selection preserved, else snapped | 3 |
| Screen opens without waiting | 4 |
| Late offer reaches the open screen | 4 |
| Offer discarded if the screen closed | 3 (`is_mounted` guard) |
| Collection probes its first entry | 4 |
| Failure is silent | 2, 4 |
| Real runs | 5 |

No gaps.

**Type consistency:** `Offer(heights, bitrates, containers, subtitles)` all
tuples; `parse(dict) -> Offer`; `probe(...) -> Offer | None`;
`apply_offer(Offer) -> None`; `usable(dict) -> bool`. Used identically in every
task that names them.

**Error handling not deferred:** subprocess failure, non-zero exit, unparseable
output, timeout, missing binary (Task 2); empty offer and unmounted screen
(Task 3); probe returning None (Task 4).
