# Format probing for the options screen — design

Date: 2026-08-08
Status: approved, not yet planned
Follows: 2026-08-08-ytdlp-routing-design.md (this is the "project B" that
spec deferred)

## The problem

The options screen offers a fixed ladder — 2160, 1440, 1080, 720, 480, 360 —
plus audio bitrates, subtitle languages and containers. That shape came from
YouTube and is right for YouTube. It is wrong everywhere else firelink can now
reach.

Measured today against the real sites:

| URL | formats | heights offered | audio |
|---|---|---|---|
| Instagram reel | 13 | 1920, 1280, 960, 640 | 59 kbps |
| SoundCloud track | 3 | **none** | 128, 96 kbps |

A SoundCloud track has no video ladder at all, so every video row on that
screen is a control that does nothing. Instagram's real heights are 1920 and
960 — numbers the fixed ladder does not contain.

Nothing breaks today: yt-dlp ignores a video selector on an audio-only track.
The screen is merely dishonest.

## Why the earlier answer was wrong

The routing spec recorded a decision to "probe when the screen opens", on an
estimate of 1–3 seconds. Measured, the probe takes **8–12 seconds** through the
proxy — YouTube took 12.3s. Blocking the screen on that would put a spinner in
front of every single download.

The decision was retaken with the real number: the screen opens immediately and
refines itself when the probe lands.

## Architecture

Three pieces, one of them new.

**`dl/formats.py`** (new) runs `yt-dlp -J` and reduces the result to what is on
offer. The subprocess call and the parsing are separate functions so the
parsing can be tested without a network.

**`dl/tui/ytoptions.py`** accepts an optional `Offer` and narrows its rows to
it. Given no offer it behaves exactly as it does today, which is also what
happens when the probe fails.

**`dl/tui/ytadd.py`** starts the probe in a worker as it pushes the screen, and
delivers the result if the screen is still open.

The screen never waits on the network. It starts with today's defaults and
learns more later.

### The data

```python
@dataclass(frozen=True)
class Offer:
    heights: tuple[int, ...]       # descending; empty means audio-only
    bitrates: tuple[int, ...]      # descending
    containers: tuple[str, ...]
    subtitles: tuple[str, ...]     # language codes actually available
```

Derived from `yt-dlp -J`:

- `heights` — distinct truthy `height` across formats, descending
- `bitrates` — distinct rounded `abr`, descending
- `containers` — distinct `ext`, storyboards excluded
- `subtitles` — keys of the `subtitles` object

**Storyboard formats are discarded**: `ext == "mhtml"`, or an entry carrying
neither a height nor an `abr`. This is not hypothetical tidying. A yt-dlp
without `yt-dlp-ejs` returns *only* storyboards for YouTube — the regression
fixed in `b156523` — and an `Offer` built from those would advertise a menu of
nothing. Discarding them means such a result yields an empty `Offer`, which is
treated as no information and leaves the screen static.

### How the screen narrows

| Probe result | Screen |
|---|---|
| none yet, or failed | today's static lists, unchanged |
| `heights` empty | video row hidden; audio containers only; subtitle rows hidden |
| `heights` present | video choices become `best` + those heights + `none` |
| `subtitles` empty | subtitle rows hidden |

**Narrowing must not overrule a choice already made.** The probe can land after
the user has changed a value. The rule: keep the current selection when it is
still available; snap to the nearest available value only when it is not. The
probe refines the menu, never the decision.

### Collections

Options are asked once for a whole collection, so the probe runs on the **first
entry only** — one request, not one per video. Entries in a collection almost
always share a format profile, and where they do not, yt-dlp's `height<=N`
selector already falls back to the next available rendition.

The known limitation, accepted: a mixed collection is shaped by whatever its
first entry happens to be.

## Error handling

- **Probe fails, times out, or returns unparseable output** — the screen stays
  static and says nothing. This is an enhancement; announcing its failure would
  be worse than the behaviour it is enhancing.
- **Probe lands after the screen closed** — discarded.
- **Empty offer** (no heights *and* no bitrates) — treated as no information,
  not as "audio-only". Only an offer carrying bitrates and no heights means
  audio-only.

`probe()` returns `None` when the subprocess failed, timed out, or produced
output that would not parse; it returns an `Offer` whenever the output parsed,
even an empty one. The screen treats both the same way — stay static — so the
distinction exists for tests and logging rather than behaviour.
- **Timeout** — reuses `cfg.probe_timeout`, the setting that already governs how
  long firelink waits for a site to describe something.

## Components

| File | Change |
|---|---|
| `dl/formats.py` | **new** — `Offer`, `parse(info: dict) -> Offer`, `probe(url, proxy, cookies_from, timeout) -> Offer \| None`, `probe_command(...)` |
| `dl/tui/ytoptions.py` | accept `offer`, narrow `options_for` and `visible_fields`, preserve selection, repaint on arrival |
| `dl/tui/ytadd.py` | start the probe worker alongside the options screen; deliver to the live screen |

`dl/youtube.py` is untouched: `build_args` already emits whatever selector the
choices describe, and narrowing the menu does not change how a choice becomes
an argument.

## Data flow

```
options screen pushed ─┬─> screen visible immediately (static lists)
                       └─> worker: yt-dlp -J on the url
                                   (first entry, for a collection)
                              │  8–12s
                              ▼
                        parse -> Offer
                              │
                     screen still open?
                       ├─ no  -> discard
                       └─ yes -> narrow rows, keep valid selections, repaint
```

## Testing

Parsing is tested against the JSON shapes captured from real sites today —
Instagram's 13 formats and SoundCloud's 3 — so the fixtures are observed rather
than imagined. Storyboard-only input gets its own case, standing in for the
YouTube regression.

Screen tests cover: no offer, audio-only offer, video offer, a selection
preserved across narrowing, a selection snapped when its value disappears, and
an offer arriving after the screen closed.

Then real runs against a SoundCloud track and an Instagram reel. Every genuine
defect in this project has come from real use rather than the suite — including
the YouTube breakage found an hour before this spec was written, which 1773
passing tests did not notice.

## Not in scope

**Merging with the existing probe.** firelink already runs a separate
`--simulate` probe for title and size after the destination is chosen. The
`-J` call here could supply both and save a round trip. Merging them reshuffles
the add flow for a gain nobody asked for, so the two stay separate.

**Per-item probing for collections.** One probe, first entry, as above.
