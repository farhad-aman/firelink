from pathlib import Path

from . import daemon, instance

LEGACY_CONFIG_DIR = Path.home() / ".config" / "dl"
LEGACY_STATE_DIR = Path.home() / ".local" / "state" / "dl"


class LegacyInUse(Exception):
    pass


def adopt(legacy_config: Path, legacy_state: Path, config_dir: Path, state_dir: Path) -> None:
    """Move the folders an install from before 0.5, when the command was `dl`,
    left behind. A folder already at the new name always wins."""
    if legacy_state.is_dir() and not state_dir.exists():
        running = instance.holder(legacy_state)
        if running:
            raise LegacyInUse(
                f"an old `dl` window is open (pid {running}) — close it, then run firelink again"
            )
        old_daemon = daemon.read_pid(legacy_state)
        if daemon.alive(old_daemon):
            daemon._terminate(old_daemon)
        daemon.clear_pid(legacy_state)
        _move(legacy_state, state_dir)
    if legacy_config.is_dir() and not config_dir.exists():
        _move(legacy_config, config_dir)


def _move(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
