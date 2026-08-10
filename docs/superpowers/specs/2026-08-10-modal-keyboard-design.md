# Keyboard-operable modals — design

Date: 2026-08-10
Status: approved, not yet planned

## The problem

Reported from use: adding a download opens a box that fills itself from the
clipboard, and then appears to need a mouse click on **Queue** to go anywhere.
The same for the delete dialog — the letter shortcuts are printed on the
buttons, but `↑`/`↓` and `⏎` do nothing recognisable.

Supporting a mouse is good. Requiring one, in a terminal download manager
driven entirely by the keyboard everywhere else, is not.

## What is actually wrong

Measured against Textual 8.2.8 rather than assumed. Every one of these modals
is **already** keyboard-operable:

| Modal | Keys | Result |
|---|---|---|
| Add downloads | `tab` `⏎` | queues the URL |
| Confirm | `⏎` alone | Yes |
| Confirm | `tab` `⏎` | No |
| Delete | `tab` `⏎` | delete from disk |

`Button` binds `⏎` to `press` itself, and `TextArea`'s `tab_behavior` already
defaults to `focus`, so `tab` escapes the text box.

So no capability is missing. What is missing is any way to find out. Nothing on
screen mentions `tab`, and `↑`/`↓` — the keys a person actually reaches for —
do nothing at all. The mouse is not required; it is merely the only thing the
dialog advertises.

**This reframes the work.** It is a discoverability fix with a small navigation
addition, not new keyboard support.

It also exposes a hazard. In the delete dialog `tab` `⏎` lands on **"Delete
file from disk too"**, the destructive choice. Anyone who discovers `tab` by
accident finds it on a file they cared enough about to be deleting carefully.

## Scope

All five button-bearing modals in `dl/tui/modals.py`: `AddUrlModal`,
`SpeedLimitModal`, `DeleteModal`, `DuplicateModal`, `ConfirmModal`.

Deliberately excluded: `PickerScreen`, `PlaylistScreen` and the settings
`FormScreen`, which own their navigation already, and `YouTubeOptionsScreen`,
which is the pattern being copied rather than changed.

## The design

### 1. `↑`/`↓` move focus

A small shared mixin binds them to Textual's `focus_previous` and `focus_next`.
All five modals inherit it. `⏎` needs no change, because `Button` already binds
it. Every existing letter shortcut — `l`, `d`, `s`, `r`, `o` — is untouched, as
is `tab`.

The mixin lives at the top of `dl/tui/modals.py`, beside the modals that use
it. It is a handful of lines and has no consumer elsewhere; a separate module
would be a file to open for no reason.

### 2. `ctrl+s` submits the Add box

Chosen over `⏎` and over `shift+⏎`: terminals frequently cannot distinguish
`shift+⏎` or `ctrl+⏎` from plain `⏎`, which would silently make a second URL
impossible to type on the machines where it fails. `ctrl+`letter is reliable
everywhere.

`⏎` keeps inserting newlines, so several URLs still work.

`↓` moves from the text area to the Queue button **only when the cursor is on
the last line**; otherwise it moves the cursor. For the ordinary one-line paste
that means `↓` reaches the button immediately, and multi-line editing is
unaffected.

### 3. A hint line on every modal

This is the part that fixes the reported complaint. `YouTubeOptionsScreen`
already carries one:

```
↑↓ field    ←→ change    ⏎ continue    esc cancel
```

The modals adopt the same idea:

- Add: `↑↓ move    ctrl+s queue    esc cancel`
- Speed limit: `↑↓ move    ⏎ apply    esc cancel`
- Delete, Duplicate, Confirm: `↑↓ move    ⏎ choose    esc cancel`

The letters already printed on the buttons stay where they are.

### 4. The safe option keeps first focus

`DeleteModal` already composes "Remove from list only" first, so focus starts
there. Nothing changes; the hint line simply makes the ordering visible instead
of something learned by pressing keys on a real file.

## Testing

Pilot tests per modal:

- `↓` then `⏎` activates the second button; `↑` returns to the first
- `ctrl+s` submits the Add box from inside the text area, without a focus change
- `↓` inside a multi-line Add box moves the cursor while lines remain below it,
  and only moves focus from the last line
- the hint line is present and names `↑↓`

The four behaviours measured above become regression tests. They work today and
must keep working — a fix that quietly broke `tab` `⏎` would be a poor trade.

## Not doing

Changing what `tab` does, renaming or removing any letter shortcut, restyling
the modals, or touching the picker, playlist and settings screens.
