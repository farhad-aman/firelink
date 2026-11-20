"""A global speed limit, set by hand or by the time of day."""

import pytest

from firelink import cli, config, schedule
from firelink.rpc import Aria2Unreachable


def _at(hour: int, minute: int = 0) -> int:
    return hour * 60 + minute


NIGHT_AND_DAY = (
    schedule.Window(_at(1), _at(7), "0"),
    schedule.Window(_at(7), _at(1), "2M"),
)


class Daemon:
    def __init__(self):
        self.options = []

    def change_global_option(self, options):
        self.options.append(options)
        return "OK"


def _cfg(windows=()):
    return config.replace(config.defaults(), schedule=tuple(windows))


def test_the_window_holding_the_minute_gives_the_rate():
    assert schedule.window_rate(NIGHT_AND_DAY, _at(3)) == "0"
    assert schedule.window_rate(NIGHT_AND_DAY, _at(12)) == "2M"


def test_a_window_past_midnight_holds_both_sides_of_it():
    assert schedule.window_rate(NIGHT_AND_DAY, _at(23, 30)) == "2M"
    assert schedule.window_rate(NIGHT_AND_DAY, _at(0, 30)) == "2M"


def test_a_minute_outside_every_window_has_no_rate():
    only_night = (schedule.Window(_at(1), _at(7), "0"),)
    assert schedule.window_rate(only_night, _at(12)) is None


def test_the_config_reads_a_schedule(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[schedule]\n"01:00-07:00" = "off"\n"07:00-01:00" = "2m"\n')
    cfg = config.load(path)
    assert cfg.schedule == NIGHT_AND_DAY


@pytest.mark.parametrize(
    "line",
    ['"1am-7am" = "2M"', '"01:00-07:00" = "fast"', '"25:00-07:00" = "2M"', '"01:00-01:00" = "2M"'],
)
def test_a_schedule_the_daemon_could_not_follow_is_a_config_problem(tmp_path, line):
    path = tmp_path / "config.toml"
    path.write_text(f"[schedule]\n{line}\n")
    assert config.problem(path) != ""


def test_a_limit_set_by_hand_wins_over_the_schedule(tmp_path):
    schedule.set_override(tmp_path, "500K")
    rate, source = schedule.effective(tmp_path, _cfg(NIGHT_AND_DAY), _at(3))
    assert rate == "500K"
    assert "firelink limit" in source


def test_without_a_hand_set_limit_the_schedule_decides(tmp_path):
    rate, source = schedule.effective(tmp_path, _cfg(NIGHT_AND_DAY), _at(12))
    assert rate == "2M"
    assert "07:00-01:00" in source


def test_with_neither_there_is_no_limit(tmp_path):
    assert schedule.effective(tmp_path, _cfg(), _at(12))[0] == "0"


def test_a_tick_applies_a_changed_rate_once(tmp_path):
    aria2 = Daemon()
    last = schedule.tick(tmp_path, _cfg(NIGHT_AND_DAY), aria2, "", _at(12))
    again = schedule.tick(tmp_path, _cfg(NIGHT_AND_DAY), aria2, last, _at(12, 1))
    assert aria2.options == [{"max-overall-download-limit": "2M"}]
    assert again == "2M"


def test_limit_sets_the_rate_and_applies_it_to_a_running_daemon(tmp_path, capsys):
    aria2 = Daemon()
    kept = []
    assert cli.cmd_limit(["2m"], _cfg(), tmp_path, client=aria2, keep=lambda: kept.append(1)) == 0
    assert aria2.options == [{"max-overall-download-limit": "2M"}]
    assert schedule.read_override(tmp_path) == "2M"
    assert kept == [1]
    assert "2M" in capsys.readouterr().out


def test_limit_off_is_an_explicit_no_limit(tmp_path):
    aria2 = Daemon()
    cli.cmd_limit(["off"], _cfg(NIGHT_AND_DAY), tmp_path, client=aria2, keep=lambda: None)
    assert schedule.read_override(tmp_path) == "0"
    assert aria2.options[-1] == {"max-overall-download-limit": "0"}


def test_limit_auto_hands_back_to_the_schedule(tmp_path):
    schedule.set_override(tmp_path, "500K")
    aria2 = Daemon()
    cli.cmd_limit(["auto"], _cfg(NIGHT_AND_DAY), tmp_path, client=aria2, keep=lambda: None, minute=_at(12))
    assert schedule.read_override(tmp_path) == ""
    assert aria2.options[-1] == {"max-overall-download-limit": "2M"}


def test_limit_with_no_daemon_running_is_kept_for_when_one_starts(tmp_path):
    assert cli.cmd_limit(["1M"], _cfg(), tmp_path, client=None, keep=lambda: None) == 0
    assert schedule.read_override(tmp_path) == "1M"


def test_a_daemon_that_vanishes_while_setting_still_keeps_the_setting(tmp_path):
    class Gone:
        def change_global_option(self, options):
            raise Aria2Unreachable("refused")

    assert cli.cmd_limit(["1M"], _cfg(), tmp_path, client=Gone(), keep=lambda: None) == 0
    assert schedule.read_override(tmp_path) == "1M"


def test_a_bad_rate_is_refused(tmp_path, capsys):
    assert cli.cmd_limit(["fast"], _cfg(), tmp_path, client=None, keep=lambda: None) == 1
    assert "fast" in capsys.readouterr().err


def test_limit_with_no_argument_shows_the_rate_and_where_it_comes_from(tmp_path, capsys):
    cli.cmd_limit([], _cfg(NIGHT_AND_DAY), tmp_path, client=None, keep=lambda: None, minute=_at(12))
    out = capsys.readouterr().out
    assert "2M" in out and "07:00-01:00" in out


def test_the_keeper_is_started_with_a_new_daemon_only_when_there_is_something_to_keep(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(schedule, "spawn_keeper", lambda state, config_file: started.append(state))
    schedule.start_if_needed(_cfg(), tmp_path, tmp_path / "config.toml")
    assert started == []
    schedule.start_if_needed(_cfg(NIGHT_AND_DAY), tmp_path, tmp_path / "config.toml")
    assert started == [tmp_path]
