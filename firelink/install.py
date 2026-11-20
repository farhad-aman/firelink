import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version


def by_homebrew() -> bool:
    """Whether this firelink came from the tap rather than from a clone.

    Homebrew builds into <prefix>/Cellar/firelink/<version>/libexec, and the
    remedy for a stale copy differs completely between the two.
    """
    return "/Cellar/" in sys.prefix


def update_command() -> str:
    return "brew upgrade firelink" if by_homebrew() else "make install"


def version() -> str:
    try:
        return _distribution_version("firelink")
    except PackageNotFoundError:
        return "unknown"
