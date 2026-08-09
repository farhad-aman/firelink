import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from dl.formats import Offer
from dl.tui.ytoptions import YouTubeOptionsScreen
from dl.youtube import DEFAULTS, VIDEO_CHOICES, Choices


class Host(App):
    def __init__(self, screen):
        super().__init__()
        self._screen = screen
        self.result = "unset"

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self):
        self.push_screen(self._screen, lambda value: setattr(self, "result", value))


def make(**over):
    return YouTubeOptionsScreen("Some Video Title", DEFAULTS)


async def test_enter_accepts_the_defaults():
    app = Host(make())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == DEFAULTS


async def test_escape_cancels():
    app = Host(make())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


async def test_the_title_is_shown():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Some Video Title" in screen.head


async def test_right_arrow_lowers_the_video_quality():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result.video == "2160"


async def test_left_arrow_wraps_to_audio_only():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert screen.values["video"] == "none"


async def test_choosing_audio_only_switches_the_container():
    """mp4 is not an audio container."""
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert screen.values["container"] == "m4a"


async def test_audio_only_hides_the_subtitle_fields():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert "subs" not in screen.visible_fields()
        assert "Subtitles" not in screen.body


async def test_the_language_appears_only_once_subtitles_are_on():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "sub_lang" not in screen.visible_fields()
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("right")
        await pilot.pause()
        assert screen.values["subs"] == "soft"
        assert "sub_lang" in screen.visible_fields()


async def test_moving_down_then_changing_edits_the_second_field():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result.audio == "256"
    assert app.result.video == "best"


async def test_the_selected_field_is_marked():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen.body.splitlines()[0].startswith("▌")
        await pilot.press("down")
        await pilot.pause()
        assert screen.body.splitlines()[1].startswith("▌")


async def test_field_focus_never_falls_off_the_end_when_fields_disappear():
    """Turning subtitles on then switching to audio-only shortens the list."""
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        for _ in range(4):
            await pilot.press("down")
        await pilot.pause()
        screen.field = len(screen.visible_fields()) - 1
        screen.values["video"] = "none"
        screen._settle_container()
        screen.field = min(screen.field, len(screen.visible_fields()) - 1)
        screen._repaint()
        await pilot.press("right")
        await pilot.pause()
        assert screen.field < len(screen.visible_fields())


async def test_hard_subtitles_warn_when_ffmpeg_cannot_burn_them():
    screen = YouTubeOptionsScreen("Title", DEFAULTS, can_burn=False)
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.values["subs"] = "hard"
        screen._repaint()
        assert "cannot burn in subtitles" in screen.body


async def test_no_warning_when_ffmpeg_can_burn_them():
    screen = YouTubeOptionsScreen("Title", DEFAULTS, can_burn=True)
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.values["subs"] = "hard"
        screen._repaint()
        assert "cannot burn in" not in screen.body


async def test_a_full_selection_round_trips():
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.values.update(video="1080", audio="192", subs="hard", sub_lang="fa", container="mkv")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result.video == "1080"
    assert app.result.subs == "hard"
    assert app.result.sub_lang == "fa"
    assert app.result.container == "mkv"


async def test_the_burn_in_warning_names_a_remedy_that_works():
    """`brew reinstall ffmpeg` does not help: homebrew-core's formula has no
    libass at all, so the rebuild produces the same binary."""
    screen = YouTubeOptionsScreen("clip", can_burn=False)
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        for _ in range(2):
            await pilot.press("down")
        while screen.values["subs"] != "hard":
            await pilot.press("right")
        await pilot.pause()
        text = screen.body
        assert "libass" in text
        assert "homebrew-ffmpeg" in text
        assert "reinstall" not in text


VIDEO_OFFER = Offer(heights=(1920, 1280, 640), bitrates=(59,), containers=("mp4", "m4a"))
AUDIO_OFFER = Offer(heights=(), bitrates=(128, 96), containers=("mp3", "m4a"))


def test_without_an_offer_the_screen_is_unchanged():
    assert YouTubeOptionsScreen("x").options_for("video") == VIDEO_CHOICES


def test_an_offer_replaces_the_ladder_with_real_heights():
    screen = YouTubeOptionsScreen("x", offer=VIDEO_OFFER)
    assert screen.options_for("video") == ("best", "1920", "1280", "640", "none")


def test_an_audio_only_offer_hides_the_video_row():
    assert "video" not in YouTubeOptionsScreen("x", offer=AUDIO_OFFER).visible_fields()


def test_an_audio_only_offer_hides_subtitles_too():
    """There is no picture to put them on."""
    fields = YouTubeOptionsScreen("x", offer=AUDIO_OFFER).visible_fields()
    assert "subs" not in fields
    assert "sub_lang" not in fields


def test_an_audio_only_offer_gives_real_bitrates():
    screen = YouTubeOptionsScreen("x", offer=AUDIO_OFFER)
    assert screen.options_for("audio") == ("best", "128", "96")


def test_an_offer_without_subtitles_hides_the_subtitle_rows():
    assert "subs" not in YouTubeOptionsScreen("x", offer=VIDEO_OFFER).visible_fields()


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


def test_choosing_audio_only_keeps_the_video_row_so_it_can_be_undone():
    """Different from a site that has no video: there, nothing to go back to."""
    screen = YouTubeOptionsScreen("x", choices=Choices("none", "best", "off", "en", "m4a"))
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


def test_an_empty_offer_is_not_applied():
    screen = YouTubeOptionsScreen("x", choices=Choices("1080", "best", "off", "en", "mp4"))
    screen.apply_offer(Offer())
    assert screen.values["video"] == "1080"
    assert screen.offer is None


async def test_a_probe_landing_after_dismissal_does_not_crash():
    """The probe runs beside the screen and can outlive it: accept the
    defaults quickly and the answer arrives with nothing left to draw on.
    is_mounted still reports True there, so it is the wrong thing to ask."""
    screen = make()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen.apply_offer(VIDEO_OFFER)
