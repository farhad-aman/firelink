import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def held(target: Path) -> Generator[None]:
    """Hold an exclusive lock on target for the duration of the block.

    The dashboard, the watcher, aria2's hooks and every yt-dlp supervisor are
    separate processes writing the same few files. A read-modify-write that
    one of them interleaves with another loses the other's write. The kernel
    drops the lock if the holder dies, so a crash cannot leave it stuck.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def beside(path: Path) -> Path:
    return path.with_name(path.name + ".lock")
