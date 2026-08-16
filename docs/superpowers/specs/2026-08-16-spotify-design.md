# Spotify support — design

Date: 2026-08-16
Status: approved, not yet planned

## The problem

`dl <a Spotify link>` does nothing useful today. No yt-dlp extractor matches
it — 0 of the 1751 installed — so the URL falls through to the plain aria2c
path and saves Spotify's HTML page as a file.

## What is and is not possible

Spotify's audio is protected by Widevine DRM. No login unlocks it: the
official Web API has no endpoint that returns a full track, with or without
OAuth. The only way to obtain the audio itself is to capture and decrypt the
protected stream, which is circumvention and gets accounts banned.

So firelink does not download Spotify's audio, and this design does not
pretend otherwise. It uses Spotify for **what a track is** and YouTube for
**the recording**. The file you end up with is a YouTube rip carrying
Spotify's metadata.

This is worth stating in the README too, because a user who believes
otherwise will conclude the feature is broken when a 128 kbps file appears.

## What was measured

Verified against the live services on 2026-08-16, not assumed.

| Question | Result |
|---|---|
| Read a track's name without an API key | ✅ oEmbed and the embed page both work |
| Read a playlist's track list without a key | ✅ 50 entries with artist and duration |
| Read an album's track list | ✅ 10 entries |
| Find the recording on YouTube | ✅ `ytsearch5:` returned the correct take first, twice |

Two page shapes exist and they differ. A single track lives at
`props.pageProps.state.data.entity` with `title`, `artists[].name` and
`duration`. A playlist or album carries `entity.trackList[]`, whose entries use
`title`, `subtitle` (the artist) and `duration`. Both must be parsed.

### The matching evidence

Searching `ytsearch5:<artist> <title>` and comparing each result's duration
against Spotify's:

| Track | Top result | What sat below it |
|---|---|---|
| A 214s pop single | 214s, artist's own channel | a 65s advert, a 560s radio segment, a re-upload |
| A 183s rap single | 183s, artist's own channel | a remix, a 3658s upload, a 256s edit |

The top hit was correct both times. Taking it blindly would still be wrong
eventually — an advert and a 61-minute upload were two rows away. Duration is
the single best discriminator, and channel identity is the tiebreaker.

### The truncation hazard

The embed JSON carries **no track-count or total field**. Two 50-track
playlists returned 50 entries each, which proves nothing either way about a
longer one. If a 200-track playlist truncates, firelink cannot detect it from
the response and would report a complete success over a third of the album.

This is the single most dangerous failure mode in the feature, because it is
silent and the result looks right.

## Scope

`dl <spotify track | album | playlist URL>` resolves to tracks, matches each to
YouTube, downloads through the existing pipeline, and writes tags.

Deliberately excluded: OAuth login for private playlists and liked songs,
lyrics and `.lrc` files, playlist sync, podcasts, and anything touching a
Spotify account. Those are a possible stage two and none of them are needed
for the feature to be useful.

## The design

### 1. Resolver in front of the existing pipeline

A Spotify URL becomes a list of YouTube URLs with metadata attached, and then
enters the pipeline that already exists. `ytjob` downloads it, the dashboard
shows it, `duplicates` catches a re-download, retry and history work
unchanged.

Rejected: a parallel Spotify pipeline with its own job type and queue. It
would re-implement `ytjob`, `ytqueue` and the dashboard integration — roughly
900 working lines — to gain nothing.

Rejected: a thin shim that resolves to YouTube URLs and feeds them to the add
flow as if pasted. It is the smallest change, but the Spotify metadata is
discarded at the handoff, so album and track number are lost and the artist
becomes whatever the uploader called themselves. Tags are the reason the
feature exists.

### 2. Modules

| Module | Does | Depends on |
|---|---|---|
| `dl/spotify.py` | recognise a Spotify URL, fetch its tracks | stdlib |
| `dl/spotmatch.py` | score a YouTube candidate against a track | nothing |
| `dl/tagging.py` | write tags and cover art to the finished file | `mutagen` |
| `dl/tui/matchscreen.py` | review the doubtful matches | Textual |

`spotmatch.py` is pure by design — duration, channel and title in, a score
out. No network and no screen. The part most likely to be wrong is therefore
the part easiest to test exhaustively.

One new dependency, `mutagen`. Pure Python, no build step, one added
`resource` block in the formula.

### 3. Flow

```
  spotify url
       │
       ▼
  spotify.py ──── track list ────┐   title, artist, album,
   (embed, or API if key set)    │   track no., duration, cover url
       │                         │
       │ exactly 50? warn        │
       ▼                         ▼
  for each track:  ytsearch5 ──► spotmatch.score()
                                     │
                    ┌────────────────┴────────────────┐
                    │ confident                doubtful│
                    ▼                                  ▼
              queue silently                  matchscreen.py
                    │                          (review upfront)
                    └──────────────┬───────────────────┘
                                   ▼
                          existing ytjob pipeline
                                   │
                                   ▼
                            tagging.py → the audio category
```

Resolution is one search per track, so a long playlist takes minutes before
anything downloads. It runs in a worker with a progress line — `matched 47 of
183…` — and is cancellable, the way `_open_collection` already handles a slow
channel listing.

Searches run at a bounded concurrency of four rather than a fixed delay: it
keeps a long playlist to a few minutes without looking like a scraper. On a
throttle response the batch backs off and retries that track rather than
failing it.

### 4. Scoring

| Signal | Weight | Why |
|---|---|---|
| Uploader is `<artist> - Topic` | highest | Label-uploaded Art Tracks are the album audio, not a music video |
| Uploader is the artist's own channel | high | Official, but may be a video edit of a different length |
| Duration within 2s | high | The best discriminator by a wide margin |
| Title token overlap | medium | Finds the right song under a messy title |
| Title adds `live`, `remix`, `cover`, `sped up`, `karaoke`, `instrumental` where Spotify's does not | strong penalty | How a karaoke track ends up in a library |

**Hard reject** at a duration difference above 15 seconds. That alone
eliminates every wrong candidate the probe turned up.

**Confident** means duration within 2s *and* a Topic or official channel.
Everything else goes to review. Both probed tracks would have passed silently.

### 5. Review upfront, then download unattended

The review screen lists only the doubtful tracks. When everything matches
cleanly it never appears, so a single track stays one keypress.

Keys follow the existing modals: `↑↓` move, `⏎` accept the highlighted take,
`→` cycle to that track's next candidate, `s` skip the track, `a` accept every
remaining suggestion, `esc` cancel the batch.

### 6. Playlists without a key, correctly

No key by default. Tracks, albums and short playlists work with zero setup,
which matters because firelink is installed by people who did not write it.

When a playlist returns exactly 50 entries, firelink says the list may be
truncated and names the setting that fixes it. A free Spotify client ID and
secret switches `spotify.py` to the Web API, which paginates properly and
returns the whole thing. They live in config as:

```toml
[spotify]
client_id     = ""
client_secret = ""
```

Both empty is the default and the supported state, not a half-configured one.

Guessing at 50 will occasionally warn about a playlist that genuinely holds
50. A false warning costs a sentence; a silent truncation costs a third of an
album, so the trade is the right way round.

### 7. Output

m4a, copied rather than re-encoded — YouTube Music serves AAC natively, so
converting would only lose quality against an already-lossy source. Tags come
from Spotify: title, artist, album, track number and embedded cover art.

Files are named `<artist> - <title>.m4a`, with characters illegal in a
filename replaced. Multiple artists join with `, ` as Spotify writes them.
That name is what `duplicates` compares, so re-running a playlist recognises
what it already has.

Files land in the existing `audio` category, which already routes `m4a` to
`~/Downloads/Music`. No new category.

## Error handling

One bad track never kills the batch. Failures are collected and reported at
the end, the way `parse_entries` already counts unavailable videos instead of
aborting.

| Failure | Behaviour |
|---|---|
| No candidate survives the 15s reject | Track skipped, named in the summary. Never a wrong file. |
| Playlist returns exactly 50 | Warn before downloading; name the API-key setting. |
| Spotify page shape changed | Fail loudly — "could not read Spotify's page". Never an empty list presented as success. |
| Cover art fetch fails | Download and tags proceed without it. Not fatal. |
| Matched video age-gated or region-blocked | Existing `ytjob` error path, shown as a failed row. |
| Private playlist, no key | "this playlist is private — an API key is needed to read it" |
| YouTube throttles rapid searches | Searches are paced; a throttle backs off rather than failing the batch. |

`spotify.py` reads a page Spotify never promised to keep stable. It will break
eventually. The design's job is to make the break loud and cheap to fix — one
module, one parse function, an explicit error — rather than silent and wrong.

## Testing

`spotmatch.py` gets the heaviest coverage, table-driven, seeded with the real
candidates the probe returned. The advert, the 3658s upload and the correct
take become permanent fixtures. A regression there is the one that puts junk
in a library.

`spotify.py` gets saved HTML fixtures for both page shapes. Fixture tests
prove the parser works; they cannot prove Spotify has not changed, so a
network test marked opt-in exists for when something smells wrong.

`tagging.py` writes a real file to a temp directory and reads the tags back.
`matchscreen.py` gets pilot tests shaped like `tests/test_modals.py`.

The `conftest.py` guard already prevents any of this reaching the real
history.

## Not doing

Spotify audio, account login, lyrics, sync, podcasts, or a second job type.
