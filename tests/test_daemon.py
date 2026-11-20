import stat

import pytest

from firelink import config, daemon


@pytest.fixture
def cfg():
    return config.defaults()


def test_read_secret_creates_file_with_0600(tmp_path):
    secret = daemon.read_secret(tmp_path)
    target = tmp_path / "rpc.secret"
    assert len(secret) >= 32
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_read_secret_is_stable_across_calls(tmp_path):
    assert daemon.read_secret(tmp_path) == daemon.read_secret(tmp_path)


def test_read_port_defaults_to_the_one_port(tmp_path):
    assert daemon.read_port(tmp_path) == daemon.PORT


def test_write_then_read_port(tmp_path):
    daemon.write_port(tmp_path, 6815)
    assert daemon.read_port(tmp_path) == 6815


def test_read_port_ignores_garbage(tmp_path):
    (tmp_path / "port").write_text("not-a-port")
    assert daemon.read_port(tmp_path) == daemon.PORT


def test_hook_shims_are_executable_and_exec_the_venv(tmp_path):
    complete, error = daemon.write_hook_shims(tmp_path, "/opt/venv/bin/python")
    for path, mode in [(complete, "complete"), (error, "error")]:
        body = path.read_text()
        assert body.startswith("#!/bin/sh")
        assert "/opt/venv/bin/python" in body
        assert f"-m firelink.hook {mode}" in body
        assert '"$@"' in body
        assert stat.S_IMODE(path.stat().st_mode) == 0o755


def test_hook_shims_pass_the_state_dir_as_an_argument(tmp_path):
    """Not through the environment: nothing there can move firelink's state, so the
    daemon has to tell its own hook where it keeps things."""
    complete, _ = daemon.write_hook_shims(tmp_path, "/opt/venv/bin/python")
    body = complete.read_text()
    assert f"--state {tmp_path}" in body
    assert "DL_STATE_DIR" not in body


def test_hook_shims_pass_the_config_file_as_an_argument(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "custom.toml")
    complete, _ = daemon.write_hook_shims(tmp_path, "/opt/venv/bin/python")
    body = complete.read_text()
    assert f"--config {tmp_path / 'custom.toml'}" in body
    assert "DL_CONFIG_FILE" not in body


def test_hook_shims_use_the_real_config_file_by_default(tmp_path):
    complete, _ = daemon.write_hook_shims(tmp_path, "/opt/venv/bin/python")
    assert f"--config {config.CONFIG_FILE}" in complete.read_text()


def test_hook_shims_are_rewritten_when_python_moves(tmp_path):
    daemon.write_hook_shims(tmp_path, "/old/python")
    complete, _ = daemon.write_hook_shims(tmp_path, "/new/python")
    assert "/new/python" in complete.read_text()
    assert "/old/python" not in complete.read_text()


def test_generation_starts_at_zero_and_increments(tmp_path):
    assert daemon.read_generation(tmp_path) == 0
    assert daemon.bump_generation(tmp_path) == 1
    assert daemon.bump_generation(tmp_path) == 2
    assert daemon.read_generation(tmp_path) == 2


def test_generation_ignores_corrupt_file(tmp_path):
    (tmp_path / "generation").write_text("garbage")
    assert daemon.read_generation(tmp_path) == 0


def test_aria2_args_include_rpc_secret_and_localhost(tmp_path, cfg):
    args = daemon.aria2_args(cfg, tmp_path, 6810, "abc")
    assert "--enable-rpc" in args
    assert "--rpc-secret=abc" in args
    assert "--rpc-listen-port=6810" in args
    assert "--rpc-listen-all=false" in args


def test_aria2_args_never_use_stop_with_process(tmp_path, cfg):
    assert not any("stop-with-process" in a for a in daemon.aria2_args(cfg, tmp_path, 6810, "x"))


def test_aria2_args_never_force_save(tmp_path, cfg):
    """--force-save keeps the .aria2 control file after a download completes."""
    assert not any("force-save" in a for a in daemon.aria2_args(cfg, tmp_path, 6810, "x"))


def test_aria2_args_apply_config_limits(tmp_path, cfg):
    args = daemon.aria2_args(cfg, tmp_path, 6810, "x")
    assert "--max-concurrent-downloads=3" in args
    assert "--max-connection-per-server=16" in args
    assert "--split=16" in args
    assert "--min-split-size=1M" in args
    assert "--max-download-limit=0" in args


def test_aria2_args_set_session_and_hooks(tmp_path, cfg):
    args = daemon.aria2_args(cfg, tmp_path, 6810, "x")
    assert f"--save-session={tmp_path / 'session'}" in args
    assert any(a.startswith("--on-download-complete=") for a in args)
    assert any(a.startswith("--on-download-error=") for a in args)
    assert "--auto-file-renaming=true" in args
    assert "--allow-overwrite=false" in args


def test_aria2_args_restore_session_only_when_present(tmp_path, cfg):
    assert not any(a.startswith("--input-file=") for a in daemon.aria2_args(cfg, tmp_path, 6810, "x"))
    (tmp_path / "session").write_text("")
    assert f"--input-file={tmp_path / 'session'}" in daemon.aria2_args(cfg, tmp_path, 6810, "x")


def test_bindable_is_false_while_a_socket_holds_the_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        port = held.getsockname()[1]
        assert daemon._bindable(port) is False
    assert daemon._bindable(port) is True


def test_a_held_port_is_reported_rather_than_worked_around(tmp_path, cfg, monkeypatch):
    """firelink used to move to the next free port. That is how daemons nothing
    could reach ended up running beside the real one."""
    monkeypatch.setattr(daemon.shutil, "which", lambda _: "/usr/bin/aria2c")
    monkeypatch.setattr(daemon, "_probe", lambda port, secret: "free")
    monkeypatch.setattr(daemon, "_bindable", lambda port: False)

    spawned = []
    monkeypatch.setattr(daemon, "_spawn", lambda c, s, port, sec: spawned.append(port))
    with pytest.raises(daemon.DaemonStartFailed):
        daemon.ensure_running(cfg, tmp_path)
    assert spawned == []


def test_a_spawn_that_never_answers_fails_on_the_one_port(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(daemon.shutil, "which", lambda _: "/usr/bin/aria2c")
    monkeypatch.setattr(daemon, "_probe", lambda port, secret: "free")
    monkeypatch.setattr(daemon, "_bindable", lambda port: True)

    spawned = []
    monkeypatch.setattr(daemon, "_spawn", lambda c, s, port, sec: spawned.append(port))
    monkeypatch.setattr(daemon, "_await_rpc", lambda port, sec, t: False)

    with pytest.raises(daemon.DaemonStartFailed):
        daemon.ensure_running(cfg, tmp_path)
    assert spawned == [daemon.PORT]


def test_ensure_running_without_binary_raises(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(daemon.shutil, "which", lambda _: None)
    with pytest.raises(daemon.Aria2Missing):
        daemon.ensure_running(cfg, tmp_path)


def test_spawn_env_drops_ambient_proxy_settings(monkeypatch):
    """A shell with `vpn -p` active would otherwise proxy every download, and the
    daemon outlives the shell that spawned it. -p alone decides proxying."""
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:2080")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:2080")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:2080")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = daemon.spawn_env()

    assert env["PATH"] == "/usr/bin"
    assert not [k for k in env if "proxy" in k.lower()]


def test_corrupt_session_is_quarantined(tmp_path):
    session = tmp_path / "session"
    session.write_text("junk")
    kept = daemon.quarantine_session(tmp_path)
    assert not session.exists()
    assert kept is not None and kept.read_text() == "junk"
    assert kept.name.startswith("session.bad")


def test_a_second_quarantine_keeps_the_first(tmp_path):
    """The first session.bad holds the original queue. A later failed start
    overwrote it with a session that held nothing."""
    (tmp_path / "session").write_text("the real queue")
    first = daemon.quarantine_session(tmp_path)
    (tmp_path / "session").write_text("empty")
    second = daemon.quarantine_session(tmp_path)
    assert first != second
    assert first.read_text() == "the real queue"


def test_a_failed_start_says_where_the_queue_went_and_shows_this_starts_output(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(daemon.shutil, "which", lambda _: "/usr/bin/aria2c")
    monkeypatch.setattr(daemon, "_probe", lambda port, secret: "free")
    monkeypatch.setattr(daemon, "_bindable", lambda port: True)
    (tmp_path / "session").write_text("queue")
    (tmp_path / "aria2.log").write_text("an error from last week\n")

    def spawn(c, state, port, sec):
        (state / "spawn.log").write_text("We encountered a problem while processing the option '--min-split-size'\n")

    monkeypatch.setattr(daemon, "_spawn", spawn)
    monkeypatch.setattr(daemon, "_await_rpc", lambda port, sec, t: False)
    with pytest.raises(daemon.DaemonStartFailed) as exc:
        daemon.ensure_running(cfg, tmp_path)
    said = str(exc.value)
    assert "--min-split-size" in said
    assert "last week" not in said
    assert "session.bad" in said


def test_aria2_args_never_set_a_global_rate_limit(tmp_path, cfg):
    """Limits are per-download; a daemon-wide cap would throttle everything."""
    args = daemon.aria2_args(cfg, tmp_path, 6810, "x")
    assert not any("max-overall-download-limit" in a for a in args)


def _block(uri, gid):
    return f"{uri}\t\n gid={gid}\n dir=/tmp\n continue=true\n"


def test_a_failed_download_is_not_brought_back_by_the_next_start(tmp_path):
    """aria2 saves failed downloads in the session. Each start re-added them,
    they failed again, and a "Download failed" banner appeared every time."""
    from firelink import history

    (tmp_path / "session").write_text(_block("https://e.com/a.iso", "aaaa") + _block("https://e.com/b.iso", "bbbb"))
    history.append({"ts": 1, "name": "a.iso", "url": "https://e.com/a.iso", "status": "error", "gid": "aaaa"}, tmp_path / "history.jsonl")
    daemon.prune_failed(tmp_path)
    left = (tmp_path / "session").read_text()
    assert "a.iso" not in left
    assert "gid=bbbb" in left


def test_a_url_that_failed_before_gids_were_recorded_is_dropped_once(tmp_path):
    from firelink import history

    (tmp_path / "session").write_text(_block("https://e.com/a.iso", "aaaa"))
    history.append({"ts": 1, "name": "a.iso", "url": "https://e.com/a.iso", "status": "error"}, tmp_path / "history.jsonl")
    daemon.prune_failed(tmp_path)
    assert "a.iso" not in (tmp_path / "session").read_text()


def test_a_url_that_failed_then_was_queued_again_is_kept(tmp_path):
    """The same address added again after a failure is a new download."""
    from firelink import history

    (tmp_path / "session").write_text(_block("https://e.com/a.iso", "new1"))
    log = tmp_path / "history.jsonl"
    history.append({"ts": 1, "url": "https://e.com/a.iso", "status": "error", "gid": "old1"}, log)
    daemon.prune_failed(tmp_path)
    assert "gid=new1" in (tmp_path / "session").read_text()


def test_starting_the_daemon_prunes_the_session_first(tmp_path, cfg, monkeypatch):
    from firelink import history

    (tmp_path / "session").write_text(_block("https://e.com/a.iso", "aaaa"))
    history.append({"ts": 1, "url": "https://e.com/a.iso", "status": "error", "gid": "aaaa"}, tmp_path / "history.jsonl")
    monkeypatch.setattr(daemon.subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 7})())
    daemon._spawn(cfg, tmp_path, daemon.PORT, "s")
    assert "a.iso" not in (tmp_path / "session").read_text()
