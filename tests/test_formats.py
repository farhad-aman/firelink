from dl import formats

# A real Instagram reel: one audio format, three renditions stripped of
# metadata, and nine video formats reporting abr as 0 rather than None.
INSTAGRAM = {
    "title": "Video by tinkertwist",
    "formats": [
        {"format_id": "dash-a", "ext": "m4a", "height": None, "abr": 59.135, "vcodec": "none"},
        {"format_id": "1", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "2", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "3", "ext": "mp4", "height": None, "abr": None, "vcodec": None},
        {"format_id": "dash-b", "ext": "mp4", "height": 640, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-c", "ext": "mp4", "height": 960, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-d", "ext": "mp4", "height": 1280, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-e", "ext": "mp4", "height": 1280, "abr": 0, "vcodec": "vp09"},
        {"format_id": "dash-f", "ext": "mp4", "height": 1920, "abr": 0, "vcodec": "vp09"},
    ],
}

# A real SoundCloud track: audio only, no heights anywhere.
SOUNDCLOUD = {
    "title": "Houston We Have a Podcast",
    "formats": [
        {"format_id": "hls_mp3", "ext": "mp3", "height": None, "abr": 128, "vcodec": "none"},
        {"format_id": "hls_aac", "ext": "m4a", "height": None, "abr": 96, "vcodec": "none"},
        {"format_id": "hls_opus", "ext": "m4a", "height": None, "abr": 96, "vcodec": "none"},
    ],
}

# What a yt-dlp without yt-dlp-ejs returns for YouTube: storyboards only.
STORYBOARDS = {
    "title": "Some Video",
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "height": 180, "abr": None, "vcodec": "images"},
        {"format_id": "sb1", "ext": "mhtml", "height": 90, "abr": None, "vcodec": "images"},
    ],
}


def test_heights_come_back_largest_first():
    assert formats.parse(INSTAGRAM).heights == (1920, 1280, 960, 640)


def test_repeated_heights_appear_once():
    assert formats.parse(INSTAGRAM).heights.count(1280) == 1


def test_a_zero_bitrate_is_not_offered():
    """Video formats report abr as 0, not None. Without a truthiness check
    the screen would offer "0 kbps" as a quality."""
    assert 0 not in formats.parse(INSTAGRAM).bitrates
    assert formats.parse(INSTAGRAM).bitrates == (59,)


def test_a_track_with_no_video_has_no_heights():
    assert formats.parse(SOUNDCLOUD).heights == ()
    assert formats.parse(SOUNDCLOUD).bitrates == (128, 96)


def test_audio_only_is_bitrates_without_heights():
    assert formats.parse(SOUNDCLOUD).audio_only is True
    assert formats.parse(INSTAGRAM).audio_only is False


def test_containers_come_from_formats_that_describe_something():
    """The renditions named 1, 2 and 3 carry no height and no bitrate, so
    they describe nothing and shape nothing."""
    assert set(formats.parse(SOUNDCLOUD).containers) == {"mp3", "m4a"}
    assert set(formats.parse(INSTAGRAM).containers) == {"m4a", "mp4"}


def test_storyboards_offer_nothing():
    """mhtml storyboards carry a height but no bitrate and no real stream.
    A yt-dlp missing yt-dlp-ejs returns only these for YouTube."""
    offer = formats.parse(STORYBOARDS)
    assert offer.empty is True
    assert offer.heights == ()


def test_an_empty_offer_is_not_audio_only():
    """Knowing nothing is different from knowing there is no video."""
    offer = formats.parse(STORYBOARDS)
    assert offer.empty is True
    assert offer.audio_only is False


def test_subtitles_are_listed_when_present():
    info = dict(SOUNDCLOUD, subtitles={"en": [{}], "fa": [{}]})
    assert set(formats.parse(info).subtitles) == {"en", "fa"}


def test_a_result_without_a_subtitles_key_has_none():
    """Instagram omits the key entirely rather than sending an empty one."""
    assert formats.parse(INSTAGRAM).subtitles == ()


def test_a_result_with_no_formats_is_empty():
    assert formats.parse({"title": "x"}).empty is True


def test_usable_needs_a_height_or_a_bitrate():
    assert formats.usable({"height": 720, "abr": 0}) is True
    assert formats.usable({"height": None, "abr": 128}) is True
    assert formats.usable({"height": None, "abr": None}) is False
    assert formats.usable({"height": None, "abr": 0}) is False
