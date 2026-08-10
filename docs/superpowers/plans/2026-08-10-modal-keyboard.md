# Keyboard-operable modals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every modal answers to `↑`/`↓` and says so on screen, so no dialog looks like it needs a mouse.

**Architecture:** A module-level `ARROWS` bindings tuple spliced into each modal's own `BINDINGS`, plus an `ArrowKeys` mixin supplying the two action methods. The Add box gains `ctrl+s` and a cursor-aware `↓`. Every modal gains a hint line in the style `YouTubeOptionsScreen` already uses.

**Tech Stack:** Textual 8.2.8, pytest with `App.run_test()` pilots.

**Spec:** `docs/superpowers/specs/2026-08-10-modal-keyboard-design.md`

## Global Constraints

These were measured against the installed Textual, not assumed. Getting any of them wrong produces code that silently does nothing.

- **Textual 8.2.8.**
- **A plain mixin's `BINDINGS` are NOT collected.** Textual gathers `BINDINGS` from `DOMNode` subclasses only. `class ArrowKeys: BINDINGS = [...]` is silently ignored. Each modal must splice the shared tuple into its own list: `BINDINGS = [*ARROWS, ...]`. Action *methods* inherit normally — only binding collection is special.
- **`priority=True` is required on the arrow bindings.** Without it the focused `Button` swallows `down` and the action never fires. This is why `YouTubeOptionsScreen` already uses it.
- **`Screen` has no `action_focus_next`.** Only the `focus_next()` method exists, so the mixin must define `action_next_control` / `action_previous_control` itself.
- **`Button` already binds `enter` to `press`.** Do not add an enter binding; it would shadow a working one.
- **`TextArea.tab_behavior` already defaults to `"focus"`.** Do not change it.
- **Write no comments.** Per the repo's standing instruction, only non-obvious *why*. Test docstrings explaining why a test exists are established style and welcome.
- Baseline is **1826 tests passing**. Run with `~/.local/share/dl/venv/bin/python -m pytest`.
- Work on the `modal-keyboard` branch, already created, holding `a1af448`.

## File Structure

- **Create `tests/test_modals.py`** — the modals have no dedicated tests today; `test_app_search.py` is the only file that touches them.
- **Modify `dl/tui/modals.py`** — `ARROWS`, `ArrowKeys`, hints, `ctrl+s`, cursor-aware `↓`.
- **Modify `dl/tui/chrome.py:68-80`** — hint styling for the dashboard's modals.
- **Modify `dl/tui/ytflow.py:44-55`** — the same styling, because these modals appear in the YouTube flow's app too.

---

### Task 1: Lock in what already works

Before changing a binding, record the behaviour that exists. `tab` `⏎` operates all five modals today; a change that quietly broke it would trade one complaint for a worse one.

**Files:**
- Create: `tests/test_modals.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Host` test app, reused by every later task in this file.

- [ ] **Step 1: Write the regression tests**

Create `tests/test_modals.py`:

```python
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
```

- [ ] **Step 2: Run them — they must all pass now, before any change**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -q
```

Expected: 5 passed. A failure here means the baseline is not what the spec measured — stop and re-measure rather than proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/test_modals.py
git commit -m "Record the modal keys that already work"
```

---

### Task 2: `↑`/`↓` move between a modal's controls

**Files:**
- Modify: `dl/tui/modals.py` — imports, new `ARROWS` and `ArrowKeys`, and the five class declarations
- Modify: `tests/test_modals.py`

**Interfaces:**
- Consumes: `Host`, `press`, `a_collision`, `fill` from Task 1.
- Produces: `modals.ARROWS` (a tuple of `Binding`), `modals.ArrowKeys` with `action_next_control()` and `action_previous_control()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_modals.py`:

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -k "down or arrows" -q
```

Expected: FAIL — `down` does nothing, so `enter` presses the first button and the results are `"list"` and `True`.

- [ ] **Step 3: Add the shared bindings and the mixin**

In `dl/tui/modals.py`, add `Binding` to the Textual imports:

```python
from textual.binding import Binding
```

Then, above `class AddUrlModal`, add:

```python
ARROWS = (
    Binding("down", "next_control", "next", show=False, priority=True),
    Binding("up", "previous_control", "previous", show=False, priority=True),
)


class ArrowKeys:
    """Up and down move between a dialog's controls.

    priority is not decoration: without it the focused Button consumes the
    arrow keys and the action never runs. The bindings cannot live here
    either — Textual collects BINDINGS from DOMNode subclasses only, so each
    modal splices ARROWS into its own list.
    """

    def action_next_control(self) -> None:
        self.focus_next()

    def action_previous_control(self) -> None:
        self.focus_previous()
```

- [ ] **Step 4: Apply it to all five modals**

Change each class declaration and splice `ARROWS` into each `BINDINGS`:

```python
class AddUrlModal(ArrowKeys, ModalScreen[list[str] | None]):
    BINDINGS = [*ARROWS, ("escape", "dismiss_none", "cancel")]
```

```python
class SpeedLimitModal(ArrowKeys, ModalScreen[str | None]):
    BINDINGS = [*ARROWS, ("escape", "dismiss_none", "cancel")]
```

```python
class DeleteModal(ArrowKeys, ModalScreen[str | None]):
    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        ("l", "from_list", "from list"),
        ("d", "from_disk", "from disk"),
    ]
```

```python
class DuplicateModal(ArrowKeys, ModalScreen[str | None]):
    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        ("s", "pick_skip", "skip"),
        ("r", "pick_rename", "rename"),
        ("o", "pick_overwrite", "overwrite"),
        ("d", "pick_download", "download"),
    ]
```

```python
class ConfirmModal(ArrowKeys, ModalScreen[bool]):
    BINDINGS = [*ARROWS, ("escape", "dismiss_false", "cancel")]
```

The mixin goes first in the bases, before `ModalScreen`.

- [ ] **Step 5: Run the modal tests**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -q
```

Expected: 9 passed — the four new ones and the five regressions from Task 1.

- [ ] **Step 6: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1835 tests.

- [ ] **Step 7: Commit**

```bash
git add dl/tui/modals.py tests/test_modals.py
git commit -m "Move between a dialog's controls with the arrow keys"
```

---

### Task 3: `ctrl+s` queues, and `↓` leaves the text box from its last line

**Files:**
- Modify: `dl/tui/modals.py` — `AddUrlModal`
- Modify: `tests/test_modals.py`

**Interfaces:**
- Consumes: `ARROWS`, `ArrowKeys` from Task 2.
- Produces: `AddUrlModal.action_queue()`, and an overriding `AddUrlModal.action_next_control()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_modals.py`:

```python
async def test_ctrl_s_queues_without_leaving_the_box():
    assert await press(AddUrlModal(), ["ctrl+s"], fill) == ["https://e.test/x.iso"]


async def test_ctrl_s_on_an_empty_box_queues_nothing():
    def empty(screen):
        screen.query_one("#urls", TextArea).text = ""

    assert await press(AddUrlModal(), ["ctrl+s"], empty) is None


async def test_down_leaves_the_box_when_the_cursor_is_on_the_last_line():
    assert await press(AddUrlModal(), ["down", "enter"], fill) == ["https://e.test/x.iso"]


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
```

- [ ] **Step 2: Run them and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -k "ctrl_s or cursor or last_line" -q
```

Expected: FAIL — `ctrl+s` is unbound, and `down` moves focus out of the box regardless of the cursor.

- [ ] **Step 3: Implement it**

Replace the whole of `AddUrlModal` with:

```python
class AddUrlModal(ArrowKeys, ModalScreen[list[str] | None]):
    BINDINGS = [
        *ARROWS,
        ("escape", "dismiss_none", "cancel"),
        Binding("ctrl+s", "queue", "queue", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-box"):
            yield Label("Add downloads — one URL per line")
            yield TextArea(clipboard_text(), id="urls")
            yield Button("Queue", variant="primary", id="ok")

    def action_next_control(self) -> None:
        """Inside the text, down belongs to the cursor until the last line."""
        box = self.query_one("#urls", TextArea)
        if self.focused is box and box.cursor_location[0] < box.document.line_count - 1:
            box.action_cursor_down()
            return
        self.focus_next()

    def action_queue(self) -> None:
        raw = self.query_one("#urls", TextArea).text
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        self.dismiss(urls or None)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.action_queue()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
```

- [ ] **Step 4: Run the modal tests**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -q
```

Expected: 13 passed.

- [ ] **Step 5: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1839 tests.

- [ ] **Step 6: Commit**

```bash
git add dl/tui/modals.py tests/test_modals.py
git commit -m "Queue with ctrl+s, and let down leave the box from its last line"
```

---

### Task 4: Say so on screen

The part that actually answers the report. Every capability above already existed in some form; none of it was written anywhere.

**Files:**
- Modify: `dl/tui/modals.py` — a `Static` hint in each `compose`
- Modify: `dl/tui/chrome.py:68-80`
- Modify: `dl/tui/ytflow.py:44-55`
- Modify: `tests/test_modals.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `modals.MOVE_HINT`, `modals.ADD_HINT`, `modals.LIMIT_HINT`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_modals.py`:

```python
from dl.tui import modals as modals_module


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
        assert screen.query_one("#add-hint", Static).renderable
```

- [ ] **Step 2: Run them and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -k hint -q
```

Expected: FAIL with `AttributeError: module 'dl.tui.modals' has no attribute 'MOVE_HINT'`.

- [ ] **Step 3: Add the hint text**

In `dl/tui/modals.py`, beside `ARROWS`:

```python
MOVE_HINT = "↑↓ move    ⏎ choose    esc cancel"
ADD_HINT = "↑↓ move    ctrl+s queue    esc cancel"
LIMIT_HINT = "↑↓ move    ⏎ apply    esc cancel"
```

Add `Static` to the widget imports if it is not already there.

- [ ] **Step 4: Put one in each modal**

As the last child of each `Vertical`:

- `AddUrlModal`: `yield Static(ADD_HINT, id="add-hint")`
- `SpeedLimitModal`: `yield Static(LIMIT_HINT, id="limit-hint")`
- `DeleteModal`: `yield Static(MOVE_HINT, id="delete-hint")`
- `DuplicateModal`: `yield Static(MOVE_HINT, id="duplicate-hint")`
- `ConfirmModal`: `yield Static(MOVE_HINT, id="confirm-hint")`

- [ ] **Step 5: Style them in both apps**

These modals are pushed by two different apps, so the rule is needed twice.

In `dl/tui/chrome.py`, after the existing `#add-box Label, ...` rule:

```css
#add-hint, #limit-hint, #delete-hint, #duplicate-hint, #confirm-hint {
    height: 1; padding-top: 1; text-style: dim;
}
```

In `dl/tui/ytflow.py`, inside the app's `CSS`, add the identical rule.

- [ ] **Step 6: Run the modal tests**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_modals.py -q
```

Expected: 16 passed.

- [ ] **Step 7: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1842 tests. A modal's rendered height changed, so any test asserting on modal layout will surface here.

- [ ] **Step 8: See it**

```bash
dl
```

Press `a`. The box should show `↑↓ move    ctrl+s queue    esc cancel` beneath the Queue button. Press `↓` — the button highlights. Press `↑` — focus returns to the text. Paste a URL and press `ctrl+s` — it queues without touching the mouse. Then press `d` on a download and check the delete dialog moves under `↑`/`↓` too.

- [ ] **Step 9: Commit**

```bash
git add dl/tui/modals.py dl/tui/chrome.py dl/tui/ytflow.py tests/test_modals.py
git commit -m "Tell people which keys a dialog answers to"
```

---

## Verification

```bash
~/.local/share/dl/venv/bin/python -m pytest -q          # exit 0, ~1842 tests
grep -c "\*ARROWS" dl/tui/modals.py                       # 5, one per modal
```

The second matters: a modal that inherits `ArrowKeys` but forgets to splice `ARROWS` compiles, runs, and silently ignores the arrow keys. That is the failure mode this whole plan was written around.
