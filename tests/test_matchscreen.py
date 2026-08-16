from textual.app import App, ComposeResult
from textual.widgets import Static

from dl.spotify import Track
from dl.spotmatch import Candidate, Scored
from dl.spotresolve import Match
from dl.tui.matchscreen import MatchScreen


class Host(App):
    def __init__(self, screen):
        super().__init__()
        self._screen = screen
        self.result = "unset"

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self) -> None:
        self.push_screen(self._screen, lambda value: setattr(self, "result", value))


def scored(url, uploader, points):
    return Scored(
        candidate=Candidate(url=url, title="T", uploader=uploader, duration=200),
        points=points,
        confident=False,
    )


def a_match(title="T", urls=("https://y.test/1", "https://y.test/2")):
    return Match(
        track=Track(title=title, artists=("X",), duration=200),
        choices=[scored(u, f"up{i}", 50 - i) for i, u in enumerate(urls)],
    )


async def press(screen, keys):
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
    return app.result


async def test_enter_accepts_the_suggested_take():
    result = await press(MatchScreen([a_match()], confident_count=0), ["enter"])
    assert len(result) == 1
    assert result[0].pick.candidate.url == "https://y.test/1"


async def test_right_cycles_to_the_next_candidate_for_that_track():
    result = await press(MatchScreen([a_match()], confident_count=0), ["right", "enter"])
    assert result[0].pick.candidate.url == "https://y.test/2"


async def test_right_wraps_round_rather_than_stopping():
    result = await press(MatchScreen([a_match()], confident_count=0), ["right", "right", "enter"])
    assert result[0].pick.candidate.url == "https://y.test/1"


async def test_s_skips_the_track_entirely():
    result = await press(MatchScreen([a_match()], confident_count=0), ["s"])
    assert result == []


async def test_a_accepts_everything_remaining_at_once():
    screen = MatchScreen([a_match("A"), a_match("B")], confident_count=0)
    result = await press(screen, ["a"])
    assert [m.track.title for m in result] == ["A", "B"]


async def test_escape_cancels_the_whole_batch():
    assert await press(MatchScreen([a_match()], confident_count=0), ["escape"]) is None


async def test_down_moves_to_the_next_track_and_up_returns():
    screen = MatchScreen([a_match("A"), a_match("B")], confident_count=0)
    result = await press(screen, ["down", "right", "up", "enter", "enter"])
    assert result[0].pick.candidate.url == "https://y.test/1"
    assert result[1].pick.candidate.url == "https://y.test/2"


async def test_a_track_with_no_candidates_can_only_be_skipped():
    empty = Match(track=Track(title="T", artists=("X",), duration=200), choices=[])
    result = await press(MatchScreen([empty], confident_count=0), ["enter"])
    assert result == []


def test_the_hint_names_every_key_the_screen_answers_to():
    from dl.tui import matchscreen

    for key in ("↑↓", "⏎", "s", "a", "esc"):
        assert key in matchscreen.MATCH_HINT


async def test_the_header_says_how_many_matched_without_asking():
    """The count is the reassurance that the other 171 are not lost."""
    screen = MatchScreen([a_match()], confident_count=171)
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "171" in str(screen.query_one("#match-head", Static).render())
