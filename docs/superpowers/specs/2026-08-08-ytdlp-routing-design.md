# yt-dlp routing — design

Date: 2026-08-08
Status: approved, not yet planned

## The problem

firelink decides between two download paths — yt-dlp for streaming sites,
aria2 for everything else — by testing a URL's hostname against a six-entry
frozenset in `dl/youtube.py`:

```python
_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com",
                    "music.youtube.com", "youtu.be", "www.youtu.be"})
```

Every other site yt-dlp supports is unreachable. Adding one means editing that
set, and the set has to be maintained forever as sites appear and disappear.

yt-dlp already answers this question for 1751 extractors. It can be asked
instead.

## What this is not

Two things came up while designing this and are deliberately out of scope.

**Format probing for the options screen.** The quality ladder (2160→360),
audio bitrates and subtitle languages assume YouTube. They are meaningless for
a SoundCloud track and wrong for a photo. Fixing that means asking yt-dlp what
renditions a specific URL actually offers, which is a network round trip and a
rebuilt screen. Separate spec.

**Telegram.** yt-dlp ships exactly one Telegram extractor, `telegram:embed`,
whose whole pattern is `https?://t\.me/(?P<channel_id>[^/]+)/(?P<id>\d+)` — a
single post in a public channel. Private channels, groups, saved messages, DMs,
invite links, the web client and `tg://` links all resolve to nothing. Real
Telegram support means MTProto (Telethon or Pyrogram), an api_id/api_hash, a
phone login and a session file. It shares nothing with the yt-dlp path.
Separate project.

## Findings that shape the design

These were measured against yt-dlp 2026.07.04, not assumed.

**Extractors declare their return type.** Of 1751: 1121 `video`, 404
`playlist`, 117 `any`, 109 unset. So 87% state statically whether a URL means
one item or many.

**Extractors declare nothing about media kind.** The full set of useful class
attributes is `IE_NAME`, `IE_DESC`, `_VALID_URL`, `_RETURN_TYPE`, `_WORKING`,
`_NETRC_MACHINE`, `age_limit`. SoundCloud reports `_RETURN_TYPE: "video"`,
identical to YouTube, because yt-dlp means "one media item" by it. There is no
way to know from a declaration that a site is audio-only. This is why format
probing is a separate project rather than a detail of this one.

**Two URL shapes break naive delegation.**

1. `youtube.com/watch?v=X&list=Y&index=4` resolves to `youtube:tab` with
   return type `any` — not `youtube`/`video`. Delegating to yt-dlp would queue
   an entire playlist when the user copied one video while watching it inside
   one. `playlist.is_collection()` already gets this right and is more accurate
   here than yt-dlp itself.

2. `youtu.be/dQw4w9WgXcQ?list=PLxyz` matches **no extractor at all**.
   `suitable()` returns nothing for every one of the 1751. Remove `?list=` and
   it matches `youtube`/`video` normally. Asking yt-dlp would route a YouTube
   link to aria2, which would download an HTML page.

Both mean the existing YouTube handling must survive as an override, not be
replaced.

**Cost.** Importing yt_dlp and building all 1751 extractor classes takes
~192 ms; matching a URL costs ~17 ms on first touch. Paid once per process.

## Architecture

### Routing: three tiers, first match wins

```
1. known host          -> yt-dlp path       instant
2. file-shaped URL     -> aria2 path        instant
3. ask yt-dlp          -> whatever it says  ~200 ms, once per process
```

Tier 1 holds YouTube hosts only, and exists for correctness rather than speed:
it is the backstop for finding 2, where tier 3 answers wrongly. Both findings
are YouTube-specific, so no other site needs an entry. Keeping it at YouTube
means there is no host list to maintain — which is the point of the project.

Tier 2 short-circuits URLs ending in a known file extension, magnets and
`.torrent` links. Without it every plain `dl https://example.com/ubuntu.iso`
pays 200 ms to be told "not mine" — the common case subsidising the rare one.
`dl/routing.py` already holds extension tables to reuse.

Tier 3 imports `yt_dlp` lazily, on first miss, and caches the extractor list
for the life of the process.

### Collection detection

```
is_youtube(url)              -> existing rules, unchanged
_RETURN_TYPE == "playlist"   -> collection
_RETURN_TYPE == "video"      -> single
otherwise ("any" / unset)    -> probe; entry count decides
```

The probe is `playlist.expand()`, which already exists and already returns
entries. More than one entry means a collection. This adds no new machinery,
and firelink already probes single YouTube videos for title and size, so the
wait is consistent with what the tool does today rather than new.

### PlaylistScreen: two modes on one threshold

The threshold is `cfg.newest` (default 100), which is already a setting and
already exposed in the settings screen. `PlaylistScreen.offers_newest` is
already `count > newest` — the same comparison.

| collection size | screen |
|---|---|
| `count <= cfg.newest` | checkbox list of titles; `a` all, `n` none, space toggles, ⏎ queues |
| `count > cfg.newest` | today's count chooser, unchanged |

Titles are free: the flat listing already carries them, `parse_entries()`
already puts them in `Entry.title`, and `_open_collection` already uses them to
name spawned jobs. The screen simply has not displayed them.

Sizes remain unavailable. A flat listing has none and getting them means
extracting every entry — the original constraint, still true.

The count chooser stays for the case it was built for: a channel holding
thousands, where a checkbox list is not a usable interface.

### Two facts worth surfacing

**`_WORKING`** is False for 137 of 1751 extractors, including `instagram:user`
and three TikTok variants. Warn before queueing rather than failing a minute
later.

**yt-dlp staleness.** Owning yt-dlp as a dependency means `brew upgrade` no
longer updates it, and a stale yt-dlp breaks sites silently. Surface the
installed version's age when it exceeds ~60 days, pointing at `make install`.
Without this, the packaging decision quietly trades away the update path.

## Components

| File | Change |
|---|---|
| `dl/youtube.py` → `dl/ytdlp.py` | rename; `is_youtube()` → `handles()`; add `extractor_for()`, `return_type()`, `working()` |
| `dl/playlist.py` | `is_collection()` gains tiered logic; YouTube branch untouched |
| `dl/tui/playlistscreen.py` | second mode: checkbox list under the threshold |
| `dl/tui/ytadd.py` | consume a selection rather than a count |
| 6 call sites | `youtube.is_youtube` → `ytdlp.handles` |
| `pyproject.toml` | add `yt-dlp` dependency |

`build_args()`, the job runner, progress parsing, pausing and cancellation are
unchanged. They were already site-agnostic — that is why this project is small.

## Data flow

```
url
 ├─ tier 1 known host ─────────────┐
 ├─ tier 2 file-shaped ── aria2    │
 └─ tier 3 ask yt-dlp ─────────────┤
                                   ▼
                          is it a collection?
                           ├─ no  → options → destination → probe → spawn
                           └─ yes → expand (flat listing)
                                     ├─ ≤ newest → checkbox list
                                     └─ > newest → count chooser
                                          → options once → destination once
                                          → one job per entry
```

Options and destination are asked once per collection and reused, as today.

## Error handling

- **yt_dlp import fails** (not installed, broken venv) — tier 3 returns "not
  mine" and the URL goes to aria2. Degrades to roughly today's behaviour rather
  than crashing. Surface it once, not per URL.
- **Extractor marked broken** — warn, let the user proceed anyway. yt-dlp's
  `_WORKING` flag lags reality in both directions.
- **Probe fails or times out** for an `any` URL — treat as a single item and
  let the download report the real error. Better than refusing to queue.
- **Empty collection** — existing `ListingFailed` path, unchanged.
- **Every entry unavailable** — existing message, unchanged.

## Testing

Offline unit tests, with extractor lookups faked so nothing touches the
network:

- tier ordering, including a named regression test for each finding:
  `watch?v=X&list=Y` must stay a single video; `youtu.be/ID?list=` must route
  to yt-dlp
- collection classification for each return type, and the probe fallback for
  `any`
- the file-extension short-circuit, including magnets and `.torrent`
- threshold behaviour exactly at `cfg.newest`, and either side of it
- checkbox selection: all, none, partial, and cancel

Then real runs, because every real bug in this project so far came from actual
use rather than the suite: an Instagram post, a SoundCloud set, an Aparat
video, and a YouTube playlist to confirm no regression.

## Resolved during review

**Tier 1 stays YouTube-only.** The alternative was to add Instagram, TikTok,
SoundCloud and the rest so they skip the ~200 ms import. Rejected: that
reintroduces the maintained host list this project exists to delete, and the
saving is once per process on sites that need a network round trip anyway.
Tier 1 is justified only by the two findings, both of which are YouTube's.
