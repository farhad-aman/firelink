from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Static, TextArea

from dl import duplicates
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
