import pytest

from dl import spotmatch
from dl.spotify import Track

SUPERHERO = Track(title="Superhero", artists=("Metro Boomin", "Future"), duration=183)
ASTLEY = Track(title="Never Gonna Give You Up", artists=("Rick Astley",), duration=214)


def candidate(title, uploader, duration, url="https://y.test/1"):
    return spotmatch.Candidate(url=url, title=title, uploader=uploader, duration=duration)


def test_the_right_take_on_the_artists_own_channel_is_confident():
    got = spotmatch.score(ASTLEY, candidate("Never Gonna Give You Up", "Rick Astley", 214))
    assert got is not None
    assert got.confident is True


def test_a_topic_upload_scores_above_the_same_length_elsewhere():
    """Topic channels are the label's own audio rather than a music video,
    so they are the take worth having when both lengths match."""
    topic = spotmatch.score(ASTLEY, candidate("Never Gonna Give You Up", "Rick Astley - Topic", 214))
    other = spotmatch.score(ASTLEY, candidate("Never Gonna Give You Up", "Amazing Lyrics", 214))
    assert topic.points > other.points


def test_an_advert_of_the_wrong_length_is_rejected_outright():
    """65 seconds against 214 — this was two rows below the correct result
    in a real search."""
    assert spotmatch.score(ASTLEY, candidate("InsurAAAnce & Rick Astley", "CSAA", 65)) is None


def test_an_hour_long_upload_is_rejected_outright():
    assert spotmatch.score(SUPERHERO, candidate("Superhero", "Arda", 3658)) is None


def test_a_twenty_second_difference_is_rejected():
    assert spotmatch.score(ASTLEY, candidate("Never Gonna Give You Up", "BBC", 234)) is None


def test_a_close_but_inexact_length_survives_without_confidence():
    got = spotmatch.score(SUPERHERO, candidate("Superhero", "Metro Boomin", 189))
    assert got is not None
    assert got.confident is False


def test_a_karaoke_take_is_pushed_below_the_real_one():
    real = spotmatch.score(SUPERHERO, candidate("Superhero", "Metro Boomin", 183))
    fake = spotmatch.score(SUPERHERO, candidate("Superhero (karaoke)", "Metro Boomin", 183))
    assert fake.points < real.points


def test_a_junk_word_never_makes_a_match_confident():
    """Same channel, same length to the second — only the word differs. It
    still must not download unattended."""
    got = spotmatch.score(SUPERHERO, candidate("Superhero (sped up)", "Metro Boomin", 183))
    assert got.confident is False


def test_a_word_spotify_uses_itself_is_not_junk():
    """A track genuinely called a remix must not be penalised for it."""
    track = Track(title="Superhero (Remix)", artists=("Metro Boomin",), duration=183)
    got = spotmatch.score(track, candidate("Superhero (Remix)", "Metro Boomin - Topic", 183))
    assert got.confident is True


def test_a_title_about_a_different_song_scores_below_the_right_one():
    right = spotmatch.score(SUPERHERO, candidate("Superhero", "Metro Boomin", 183))
    wrong = spotmatch.score(SUPERHERO, candidate("Creepin", "Metro Boomin", 183))
    assert wrong.points < right.points


def test_ranking_puts_the_best_first_and_drops_the_rejected():
    found = spotmatch.rank(
        ASTLEY,
        [
            candidate("InsurAAAnce", "CSAA", 65, "https://y.test/ad"),
            candidate("Never Gonna Give You Up", "Rick Astley - Topic", 214, "https://y.test/ok"),
            candidate("Never Gonna Give You Up", "Amazing Lyrics", 214, "https://y.test/mid"),
        ],
    )
    assert [s.candidate.url for s in found] == ["https://y.test/ok", "https://y.test/mid"]


def test_best_of_nothing_usable_is_nothing():
    assert spotmatch.best(ASTLEY, [candidate("advert", "CSAA", 65)]) is None
    assert spotmatch.best(ASTLEY, []) is None


def test_a_candidate_with_no_duration_is_rejected_rather_than_guessed():
    """A flat listing reports NA for some entries. Guessing is how the wrong
    file arrives with nothing to have caught it."""
    assert spotmatch.score(ASTLEY, candidate("Never Gonna Give You Up", "Rick Astley", 0)) is None


def test_the_search_command_asks_for_a_flat_listing_of_five():
    argv = spotmatch.search_command("Rick Astley Never Gonna", 5, "", "")
    assert argv[-1] == "ytsearch5:Rick Astley Never Gonna"
    assert "--flat-playlist" in argv, "extracting each result would take minutes"
    assert "--skip-download" in argv


def test_the_search_command_carries_the_proxy_and_cookies_when_set():
    argv = spotmatch.search_command("q", 5, "http://127.0.0.1:2080", "chrome")
    assert "--proxy" in argv and "http://127.0.0.1:2080" in argv
    assert "--cookies-from-browser" in argv and "chrome" in argv


def test_the_search_command_omits_them_when_unset():
    argv = spotmatch.search_command("q", 5, "", "")
    assert "--proxy" not in argv
    assert "--cookies-from-browser" not in argv


def test_candidates_are_read_back_off_the_printed_lines():
    output = (
        "https://y.test/1\t214\tRick Astley\tNever Gonna Give You Up\n"
        "https://y.test/2\t65\tCSAA\tInsurAAAnce\n"
    )
    found = spotmatch.parse_candidates(output)
    assert [c.url for c in found] == ["https://y.test/1", "https://y.test/2"]
    assert found[0].duration == 214
    assert found[0].uploader == "Rick Astley"
    assert found[0].title == "Never Gonna Give You Up"


def test_a_title_holding_a_tab_survives_being_read_back():
    """The title is last on the line so its own tabs cannot shift the fields
    before it, which is the same reason playlist.py puts the title last."""
    found = spotmatch.parse_candidates("https://y.test/1\t200\tUp\tA\tB\n")
    assert found[0].title == "A\tB"


def test_a_line_yt_dlp_could_not_fill_in_is_dropped():
    found = spotmatch.parse_candidates(
        "https://y.test/1\tNA\tUp\tTitle\nhttps://y.test/2\t200\tUp\tTitle\n"
    )
    assert [c.url for c in found] == ["https://y.test/2"]


def test_junk_output_yields_nothing_rather_than_raising():
    assert spotmatch.parse_candidates("some warning line\n") == []
    assert spotmatch.parse_candidates("") == []


def test_a_rate_limit_is_raised_rather_than_read_as_no_results(monkeypatch):
    """Flattening this into "nothing found" would skip every remaining track
    of a playlist for a reason that has nothing to do with the tracks."""

    class Done:
        stdout = ""
        stderr = "ERROR: unable to download: HTTP Error 429: Too Many Requests"

    monkeypatch.setattr(spotmatch.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(spotmatch.Throttled):
        spotmatch.find(ASTLEY)


def test_a_genuine_absence_of_results_is_not_a_throttle(monkeypatch):
    class Done:
        stdout = ""
        stderr = "WARNING: unable to extract something harmless"

    monkeypatch.setattr(spotmatch.subprocess, "run", lambda *a, **k: Done())
    assert spotmatch.find(ASTLEY) == []
