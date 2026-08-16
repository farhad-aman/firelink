from dl import spotresolve
from dl.spotmatch import Candidate
from dl.spotify import Track

A = Track(title="A", artists=("X",), duration=200)
B = Track(title="B", artists=("X",), duration=300)


def good(track):
    return [Candidate(f"https://y.test/{track.title}", track.title, "X - Topic", track.duration)]


def test_every_track_comes_back_in_the_order_it_went_in():
    """A playlist's order is the album's order — resolving concurrently must
    not shuffle it, or the track numbers stop meaning anything."""
    found = spotresolve.resolve([A, B], finder=good)
    assert [m.track.title for m in found] == ["A", "B"]


def test_a_clean_match_is_confident_and_picks_the_winner():
    match = spotresolve.resolve([A], finder=good)[0]
    assert match.confident is True
    assert match.pick.candidate.url == "https://y.test/A"


def test_a_track_with_nothing_usable_is_kept_with_no_choices():
    """Dropping it would lose the name, and the summary has to say which
    track was skipped."""
    match = spotresolve.resolve([A], finder=lambda t: [])[0]
    assert match.choices == []
    assert match.pick is None
    assert match.confident is False


def test_a_doubtful_match_is_not_confident_but_still_offers_choices():
    def close(track):
        return [Candidate("https://y.test/x", track.title, "Someone Else", track.duration + 4)]

    match = spotresolve.resolve([A], finder=close)[0]
    assert match.confident is False
    assert len(match.choices) == 1


def test_a_finder_that_raises_does_not_kill_the_batch():
    """One bad track never stops the rest — the same rule parse_entries
    follows for a private video in a playlist."""

    def flaky(track):
        if track.title == "A":
            raise OSError("broken pipe")
        return good(track)

    found = spotresolve.resolve([A, B], finder=flaky)
    assert len(found) == 2
    assert found[0].choices == []
    assert found[1].confident is True


def test_a_throttle_is_waited_out_and_retried_rather_than_skipped():
    """The track is fine; the pace is not. Skipping it would lose a track to
    a problem that fixes itself in a second."""
    from dl.spotmatch import Throttled

    tries = []

    def throttled_once(track):
        tries.append(track.title)
        if len(tries) == 1:
            raise Throttled("429")
        return good(track)

    found = spotresolve.resolve([A], finder=throttled_once, backoff=0)
    assert len(tries) == 2
    assert found[0].confident is True


def test_a_throttle_that_never_clears_gives_up_without_hanging():
    from dl.spotmatch import Throttled

    def always(track):
        raise Throttled("429")

    found = spotresolve.resolve([A], finder=always, backoff=0)
    assert found[0].choices == []


def test_progress_is_reported_once_per_track():
    seen = []
    spotresolve.resolve([A, B], finder=good, progress=lambda done, total: seen.append((done, total)))
    assert sorted(seen) == [(1, 2), (2, 2)]


def test_an_empty_listing_resolves_to_nothing_without_starting_workers():
    assert spotresolve.resolve([], finder=good) == []
