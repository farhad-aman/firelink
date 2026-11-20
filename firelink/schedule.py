import fcntl
import subprocess
import sys
import time
from pathlib import Path

from . import config, daemon
from .config import Config, Window
from .rpc import Aria2, Aria2Error, Aria2Unreachable

OVERRIDE = "limit"
KEEPER_LOCK = "schedule.lock"
TICK = 30.0
# The keeper starts beside a daemon that may not answer yet, and outlives it
# by this long at most once it stops answering.
GIVE_UP = 90.0

__all__ = ["Window"]


def window_rate(windows: tuple[Window, ...], minute: int) -> str | None:
    for window in windows:
        if window.start < window.end:
            inside = window.start <= minute < window.end
        else:
            inside = minute >= window.start or minute < window.end
        if inside:
            return window.rate
    return None


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def now_minute() -> int:
    local = time.localtime()
    return local.tm_hour * 60 + local.tm_min


def read_override(state: Path) -> str:
    try:
        return (state / OVERRIDE).read_text().strip()
    except OSError:
        return ""


def set_override(state: Path, rate: str) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / OVERRIDE).write_text(rate)


def clear_override(state: Path) -> None:
    (state / OVERRIDE).unlink(missing_ok=True)


def effective(state: Path, cfg: Config, minute: int) -> tuple[str, str]:
    """The global limit that applies now, and why."""
    by_hand = read_override(state)
    if by_hand:
        return by_hand, "set by `firelink limit` — `firelink limit auto` hands back to the schedule"
    for window in cfg.schedule:
        if window_rate((window,), minute) is not None:
            return window.rate, f"schedule {_clock(window.start)}-{_clock(window.end)}"
    return "0", "no schedule" if not cfg.schedule else "outside every schedule window"


def apply(client, rate: str) -> None:
    client.change_global_option({"max-overall-download-limit": rate})


def tick(state: Path, cfg: Config, client, last: str, minute: int) -> str:
    rate, _why = effective(state, cfg, minute)
    if rate != last:
        apply(client, rate)
    return rate


def needed(cfg: Config, state: Path) -> bool:
    return bool(cfg.schedule) or bool(read_override(state))


def spawn_keeper(state: Path, config_file: Path) -> None:
    subprocess.Popen(
        [sys.executable, "-m", "firelink.schedule", str(state), str(config_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_if_needed(cfg: Config, state: Path, config_file: Path) -> None:
    if needed(cfg, state):
        spawn_keeper(state, config_file)


def _hold(state: Path):
    """The keeper's lock for as long as it runs, or None when one already is."""
    state.mkdir(parents=True, exist_ok=True)
    handle = open(state / KEEPER_LOCK, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def keep(state: Path, config_file: Path) -> int:
    """Apply the limit the time of day calls for, for as long as the daemon
    lives. There is no scheduler otherwise: nothing runs while nothing is
    downloading."""
    held = _hold(state)
    if held is None:
        return 0
    last = ""
    lost_since: float | None = None
    with held:
        while True:
            cfg = config.load(config_file)
            client = Aria2("127.0.0.1", daemon.read_port(state), daemon.read_secret(state), timeout=2.0)
            try:
                last = tick(state, cfg, client, last, now_minute())
                lost_since = None
            except (Aria2Error, Aria2Unreachable):
                last = ""
                lost_since = lost_since or time.monotonic()
                if time.monotonic() - lost_since > GIVE_UP:
                    return 0
            if not needed(cfg, state):
                # The schedule was taken out of the config: leave no limit
                # behind that nothing will ever lift.
                if last not in ("", "0"):
                    try:
                        apply(client, "0")
                    except (Aria2Error, Aria2Unreachable):
                        pass
                return 0
            time.sleep(TICK)


if __name__ == "__main__":
    raise SystemExit(keep(Path(sys.argv[1]), Path(sys.argv[2])))
