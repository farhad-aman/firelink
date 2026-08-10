from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Static, TextArea

from dl import duplicates
from dl.tui import modals as modals_module
from dl.tui.modals import AddUrlModal, ConfirmModal, DeleteModal, DuplicateModal, SpeedLimitModal


class Host(App):
    """Pushes one modal and records what it dismissed with."""

    def __init__(self, screen):
        super().__init__()
        self._screen = screen
        self.result = "unset"

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self) -> None:
        self.push_screen(self._screen, lambda value: setattr(self, "result", value))


async def press(screen, keys, before=None):
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        if before is not None:
            before(screen)
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
    return app.result


def a_collision():
    return duplicates.Collision(
        kind=duplicates.BOTH, path=Path("/tmp/x.iso"), url="https://e.test/x.iso"
    )


def fill(screen):
    screen.query_one("#urls", TextArea).text = "https://e.test/x.iso"


async def test_tab_then_enter_still_queues():
    """This worked before the arrow keys were added and must keep working."""
    assert await press(AddUrlModal(), ["tab", "enter"], fill) == ["https://e.test/x.iso"]


async def test_enter_alone_still_confirms():
    """The first button holds focus, so plain enter answers yes."""
    assert await press(ConfirmModal("go?"), ["enter"]) is True


async def test_tab_then_enter_still_declines():
    assert await press(ConfirmModal("go?"), ["tab", "enter"]) is False


async def test_escape_still_cancels_every_modal():
    assert await press(AddUrlModal(), ["escape"]) is None
    assert await press(DeleteModal("f.iso", True), ["escape"]) is None
    assert await press(ConfirmModal("go?"), ["escape"]) is False
    assert await press(SpeedLimitModal("2M"), ["escape"]) is None
    assert await press(DuplicateModal("x.iso", a_collision(), "1 MB"), ["escape"]) is None


async def test_the_letter_shortcuts_still_work():
    assert await press(DeleteModal("f.iso", True), ["l"]) == "list"
    assert await press(DeleteModal("f.iso", True), ["d"]) == "disk"
    assert await press(DuplicateModal("x.iso", a_collision(), "1 MB"), ["s"]) == duplicates.SKIP


async def test_down_then_enter_picks_the_second_button():
    assert await press(DeleteModal("f.iso", True), ["down", "enter"]) == "disk"


async def test_down_then_up_returns_to_the_first():
    assert await press(DeleteModal("f.iso", True), ["down", "up", "enter"]) == "list"


async def test_arrows_reach_the_confirm_buttons():
    assert await press(ConfirmModal("go?"), ["down", "enter"]) is False
    assert await press(ConfirmModal("go?"), ["down", "up", "enter"]) is True


async def test_arrows_reach_the_duplicate_buttons():
    """Whichever button is second, arrowing to it and pressing enter takes it."""
    screen = DuplicateModal("x.iso", a_collision(), "1 MB")
    second = a_collision().choices[1]
    assert await press(screen, ["down", "enter"]) == second


async def test_ctrl_s_queues_without_leaving_the_box():
    assert await press(AddUrlModal(), ["ctrl+s"], fill) == ["https://e.test/x.iso"]


async def test_ctrl_s_on_an_empty_box_queues_nothing():
    def empty(screen):
        screen.query_one("#urls", TextArea).text = ""

    assert await press(AddUrlModal(), ["ctrl+s"], empty) is None


async def test_down_leaves_the_box_only_from_the_end_of_the_text():
    """A clipboard fills the box with a single line, so the cursor starts on
    the last line already. Leaving on the first press means never getting to
    move through the text at all."""
    assert await press(AddUrlModal(), ["down", "down", "enter"], fill) == [
        "https://e.test/x.iso"
    ]


async def test_the_first_down_on_one_line_runs_to_the_end_of_it():
    screen = AddUrlModal()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        fill(screen)
        await pilot.press("down")
        await pilot.pause()
        box = screen.query_one("#urls", TextArea)
        assert screen.focused is box, "one press should not leave a box just filled"
        assert box.cursor_location == box.document.end


async def test_down_moves_the_cursor_while_lines_remain_below():
    """A second URL must still be reachable, so the arrow key belongs to the
    text until there is nothing under the cursor."""
    screen = AddUrlModal()

    def two_lines(target):
        box = target.query_one("#urls", TextArea)
        box.text = "https://e.test/a.iso\nhttps://e.test/b.iso"
        box.cursor_location = (0, 0)

    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        two_lines(screen)
        await pilot.press("down")
        await pilot.pause()
        box = screen.query_one("#urls", TextArea)
        assert screen.focused is box, "focus left the box with a line still below"
        assert box.cursor_location[0] == 1


def test_every_modal_names_the_arrow_keys():
    """The keys all worked before; nothing on screen said so, which is why
    the dialog looked like it needed a mouse."""
    for hint in (modals_module.MOVE_HINT, modals_module.ADD_HINT, modals_module.LIMIT_HINT):
        assert "↑↓" in hint
        assert "esc" in hint


def test_the_add_hint_names_the_submit_key():
    assert "ctrl+s" in modals_module.ADD_HINT


async def test_the_hint_is_on_screen():
    screen = AddUrlModal()
    app = Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert str(screen.query_one("#add-hint", Static).render()) == modals_module.ADD_HINT
