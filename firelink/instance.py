import os
from pathlib import Path

from .daemon import alive
from .filelock import beside, held

LOCK = "firelink.lock"


def _read(state: Path) -> int:
    try:
        return int((state / LOCK).read_text().strip())
    except (OSError, ValueError):
        return 0


def holder(state: Path) -> int:
    """The pid of the running dashboard, or 0.

    A lock left behind by a crash names a pid that is gone, and must not keep
    the dashboard shut for good.
    """
    pid = _read(state)
    return pid if alive(pid) else 0


def acquire(state: Path, pid: int | None = None) -> bool:
    """Claim the dashboard, or report that someone else holds it.

    O_EXCL rather than read-then-write: two `firelink` started together both saw an
    empty lock and both went on to take it.
    """
    mine = os.getpid() if pid is None else pid
    state.mkdir(parents=True, exist_ok=True)
    target = state / LOCK
    # Between one starter's create and its pid write, another read an empty
    # lock as abandoned and took it; two taking over one stale lock could
    # both win. Deciding under a kernel lock leaves no such gap.
    with held(beside(target)):
        return _claim(state, target, mine)


def _claim(state: Path, target: Path, mine: int) -> bool:
    while True:
        try:
            handle = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            running = holder(state)
            if running and running != mine:
                return False
            # Ours already, or left by a process that is gone. Claiming it by
            # unlinking first keeps the exclusive create as the only way in.
            try:
                target.unlink()
            except OSError:
                return False
            continue
        except OSError:
            return False
        with os.fdopen(handle, "w") as fh:
            fh.write(str(mine))
        return True


def release(state: Path, pid: int | None = None) -> None:
    mine = os.getpid() if pid is None else pid
    if _read(state) == mine:
        (state / LOCK).unlink(missing_ok=True)
