import asyncio
import inspect
import subprocess
import sys

import pytest

from dl import config


@pytest.fixture
def other_pid():
    """A pid that is certainly alive and certainly not this process.

    os.getpid() + 1 was a guess. When nothing happens to hold that number the
    lock names a dead process, every "a second instance is refused" test takes
    the stale-takeover path instead, and the suite fails on machines where the
    guess does not land.
    """
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        yield proc.pid
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def pytest_pyfunc_call(pyfuncitem):
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
        if name in pyfuncitem.funcargs
    }
    asyncio.run(pyfuncitem.obj(**kwargs))
    return True


@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Point the state directory at tmp_path for every test.

    The dashboard reads yt-dlp job files straight off disk, so without this a
    test run sees the real ~/.local/state/dl and whatever is queued there.
    """
    from dl import config as config_module
    from dl import daemon, hook, watch
    from dl.tui import app as app_module
    from dl.tui import preview, ytadd, ytflow

    # Every module that binds the name, not just one: `from .config import
    # STATE_DIR` takes a copy, so patching the source leaves the copies pointing
    # at the real directory — which is how a test run came to take the lock off
    # a dashboard someone had open.
    where = tmp_path / "state"
    for module in (config_module, daemon, hook, watch, app_module, preview, ytadd, ytflow):
        monkeypatch.setattr(module, "STATE_DIR", where, raising=False)


@pytest.fixture(autouse=True)
def guard_the_real_history():
    """Name the test that writes into the real state directory.

    isolate_state redirects STATE_DIR, but monkeypatch does not survive a
    process boundary and the daemon listens on a fixed port, so a test can
    still reach the dashboard's own daemon and have its hooks record there.
    That has happened: six rows for a URL that exists nowhere but this suite.

    A download finishing in another window during a run trips this too. That
    is rare, and worth it for naming the culprit the one time it is not.
    """
    from pathlib import Path

    log = Path.home() / ".local" / "state" / "dl" / "history.jsonl"
    before = log.stat().st_size if log.exists() else -1
    yield
    after = log.stat().st_size if log.exists() else -1
    if after != before:
        pytest.fail(f"this test wrote to the real history at {log}")


@pytest.fixture(autouse=True)
def no_format_probe(monkeypatch):
    """Never let the options screen ask a real site what it offers.

    The probe runs in a worker as the screen opens, so every test that opens
    one would otherwise spawn yt-dlp and wait on the network. A test that
    wants an offer patches this again for itself.
    """
    from dl import formats

    monkeypatch.setattr(formats, "probe", lambda *a, **k: None)


@pytest.fixture
def sandbox_cfg(tmp_path):
    """Defaults with every destination redirected under tmp_path.

    Anything that calls mkdir on a resolved path must use this, so a test run
    never creates directories in the real home.
    """
    base = tmp_path / "dest"
    base_defaults = config.defaults()
    cats = {
        name: config.Category(name, base / name, cat.ext, cat.icon, cat.hue)
        for name, cat in base_defaults.categories.items()
    }
    general = config.replace(base_defaults.general, default_dir=base / "other")
    return config.Config(general, base_defaults.limits, cats, dict(base_defaults.domains))
