"""An install from when the command was `dl` keeps its settings and history."""

from pathlib import Path

import pytest

from firelink import daemon, instance, legacy


@pytest.fixture
def dirs(tmp_path):
    return {
        "legacy_config": tmp_path / "config" / "dl",
        "legacy_state": tmp_path / "state" / "dl",
        "config_dir": tmp_path / "config" / "firelink",
        "state_dir": tmp_path / "state" / "firelink",
    }


def _seed(dirs: dict[str, Path]) -> None:
    dirs["legacy_config"].mkdir(parents=True)
    (dirs["legacy_config"] / "config.toml").write_text("[general]\n")
    dirs["legacy_state"].mkdir(parents=True)
    (dirs["legacy_state"] / "history.jsonl").write_text("{}\n")


def test_the_old_folders_move_to_the_new_names(dirs):
    _seed(dirs)
    legacy.adopt(**dirs)
    assert (dirs["config_dir"] / "config.toml").read_text() == "[general]\n"
    assert (dirs["state_dir"] / "history.jsonl").read_text() == "{}\n"
    assert not dirs["legacy_config"].exists()
    assert not dirs["legacy_state"].exists()


def test_nothing_happens_on_a_fresh_install(dirs):
    legacy.adopt(**dirs)
    assert not dirs["config_dir"].exists()
    assert not dirs["state_dir"].exists()


def test_new_folders_that_already_exist_are_never_overwritten(dirs):
    _seed(dirs)
    dirs["config_dir"].mkdir(parents=True)
    (dirs["config_dir"] / "config.toml").write_text("mine")
    dirs["state_dir"].mkdir(parents=True)
    legacy.adopt(**dirs)
    assert (dirs["config_dir"] / "config.toml").read_text() == "mine"
    assert not (dirs["state_dir"] / "history.jsonl").exists()
    assert dirs["legacy_state"].exists()


def test_an_open_old_window_stops_the_move(dirs, other_pid):
    _seed(dirs)
    instance.acquire(dirs["legacy_state"], pid=other_pid)
    with pytest.raises(legacy.LegacyInUse, match=str(other_pid)):
        legacy.adopt(**dirs)
    assert dirs["legacy_state"].exists()
    assert not dirs["state_dir"].exists()


def test_the_old_daemon_is_stopped_before_its_folder_moves(dirs, monkeypatch, other_pid):
    """SIGTERM lets aria2 save its session, so the new daemon resumes the queue
    from the moved folder instead of the old one writing to a path that is gone."""
    _seed(dirs)
    daemon.write_pid(dirs["legacy_state"], other_pid)
    stopped = []
    monkeypatch.setattr(
        daemon,
        "_terminate",
        lambda pid: stopped.append((pid, dirs["legacy_state"].exists())),
    )
    legacy.adopt(**dirs)
    assert stopped == [(other_pid, True)]
    assert daemon.read_pid(dirs["state_dir"]) == 0
