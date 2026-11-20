import fcntl
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


class _Holding:
    def __init__(self) -> None:
        self.within = threading.RLock()
        self.depth = 0
        self.handle: IO[str] | None = None


_holdings: dict[str, _Holding] = {}
_registry = threading.Lock()


@contextmanager
def held(target: Path) -> Generator[None]:
    """Hold an exclusive lock on target for the duration of the block.

    The dashboard, the watcher, aria2's hooks and every yt-dlp supervisor are
    separate processes writing the same few files. A read-modify-write that
    one of them interleaves with another loses the other's write. The kernel
    drops the lock if the holder dies, so a crash cannot leave it stuck.

    Re-entrant within a process: flock belongs to an open file, so a nested
    hold through a second open would wait on the first for ever.
    """
    with _registry:
        holding = _holdings.setdefault(str(target), _Holding())
    with holding.within:
        if holding.depth == 0:
            target.parent.mkdir(parents=True, exist_ok=True)
            holding.handle = open(target, "a")
            fcntl.flock(holding.handle, fcntl.LOCK_EX)
        holding.depth += 1
        try:
            yield
        finally:
            holding.depth -= 1
            if holding.depth == 0 and holding.handle is not None:
                fcntl.flock(holding.handle, fcntl.LOCK_UN)
                holding.handle.close()
                holding.handle = None


def beside(path: Path) -> Path:
    return path.with_name(path.name + ".lock")
