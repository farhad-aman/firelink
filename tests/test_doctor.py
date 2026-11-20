"""`firelink doctor` names what is wrong and how to fix it."""

import datetime

from firelink import config, doctor

TODAY = datetime.date(2026, 11, 20)


def test_a_missing_aria2_fails_with_the_install_command():
    found = doctor.check_aria2(which=lambda name: None, version=lambda: "")
    assert found.level == "fail"
    assert found.fix == "brew install aria2"


def test_a_present_aria2_reports_its_version():
    found = doctor.check_aria2(which=lambda name: "/opt/homebrew/bin/aria2c", version=lambda: "1.37.0")
    assert found.level == "ok"
    assert "1.37.0" in found.detail


def test_an_old_yt_dlp_is_a_warning_with_the_update_command():
    """A stale yt-dlp shows up as sites breaking for no visible reason."""
    found = doctor.check_ytdlp("2026.01.02", today=TODAY, update="brew upgrade firelink")
    assert found.level == "warn"
    assert "322 days" in found.detail
    assert found.fix == "brew upgrade firelink"


def test_a_recent_yt_dlp_is_fine():
    assert doctor.check_ytdlp("2026.11.01", today=TODAY, update="x").level == "ok"


def test_a_yt_dlp_with_an_unreadable_version_is_not_called_old():
    assert doctor.check_ytdlp("nightly", today=TODAY, update="x").level == "ok"


def test_no_ffmpeg_warns_since_only_youtube_needs_it():
    found = doctor.check_ffmpeg(which=lambda name: None, libass=lambda: False)
    assert found.level == "warn"
    assert found.fix == "brew install ffmpeg"


def test_ffmpeg_without_libass_names_the_build_that_can_burn_subtitles():
    found = doctor.check_ffmpeg(which=lambda name: "/opt/homebrew/bin/ffmpeg", libass=lambda: False)
    assert found.level == "warn"
    assert "homebrew-ffmpeg/ffmpeg/ffmpeg" in found.fix


def test_a_broken_config_is_reported_with_its_error(tmp_path):
    broken = tmp_path / "config.toml"
    broken.write_text("[general\n")
    found = doctor.check_config(broken)
    assert found.level == "fail"
    assert str(broken) in found.detail


def test_a_good_config_is_fine(tmp_path):
    good = tmp_path / "config.toml"
    config.write_default(good)
    assert doctor.check_config(good).level == "ok"


def test_a_proxy_that_does_not_answer_is_a_warning():
    def refuse(address, timeout):
        raise OSError("Connection refused")

    found = doctor.check_proxy(config.defaults(), connect=refuse)
    assert found.level == "warn"
    assert "127.0.0.1:2080" in found.detail


def test_a_proxy_that_answers_is_fine():
    class Socket:
        def close(self):
            pass

    found = doctor.check_proxy(config.defaults(), connect=lambda address, timeout: Socket())
    assert found.level == "ok"


def test_a_port_held_by_another_program_fails():
    found = doctor.check_daemon("foreign")
    assert found.level == "fail"
    assert "6810" in found.detail


def test_a_stopped_daemon_is_normal():
    assert doctor.check_daemon("free").level == "ok"


def test_stray_daemons_point_at_the_command_that_stops_them():
    found = doctor.check_strays([(123, 6811)])
    assert found.level == "warn"
    assert found.fix == "firelink kill --strays"


def test_two_installs_on_path_are_named():
    """Homebrew's copy shadows the source shim and edits appear to do nothing."""
    found = doctor.check_installs(["/opt/homebrew/bin/firelink", "/Users/me/.local/bin/firelink"])
    assert found.level == "warn"
    assert "/Users/me/.local/bin/firelink" in found.detail


def test_an_unwritable_download_folder_fails(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        base = config.defaults()
        cfg = config.replace(
            base,
            general=config.replace(base.general, default_dir=locked / "Downloads"),
            categories={},
        )
        found = doctor.check_folders(cfg)
        assert found.level == "fail"
        assert str(locked / "Downloads") in found.detail
    finally:
        locked.chmod(0o700)


def test_the_report_exits_non_zero_only_on_a_failure():
    ok = doctor.Check("aria2", "ok", "1.37.0")
    warn = doctor.Check("ffmpeg", "warn", "missing", "brew install ffmpeg")
    fail = doctor.Check("config", "fail", "broken")
    assert doctor.exit_code([ok, warn]) == 0
    assert doctor.exit_code([ok, fail]) == 1


def test_the_report_shows_each_fix_under_its_check():
    lines = doctor.report([doctor.Check("ffmpeg", "warn", "missing", "brew install ffmpeg")], icons=False)
    assert "ffmpeg" in lines[0] and "missing" in lines[0]
    assert "brew install ffmpeg" in lines[1]
