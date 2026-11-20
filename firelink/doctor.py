import datetime
import os
import shutil
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import config, daemon, install, theme, ytdlp, ytjob

YTDLP_STALE_DAYS = 60

_MARK = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
_PLAIN = {"ok": "[ok]  ", "warn": "[warn]", "fail": "[fail]"}


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    detail: str
    fix: str = ""


def _aria2_version() -> str:
    try:
        said = subprocess.run(
            ["aria2c", "--version"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    first = said.splitlines()[0] if said else ""
    return first.split()[-1] if first else ""


def check_aria2(
    which: Callable[[str], str | None] = shutil.which,
    version: Callable[[], str] = _aria2_version,
) -> Check:
    if which("aria2c") is None:
        return Check("aria2", "fail", "not found — nothing can download", "brew install aria2")
    return Check("aria2", "ok", version() or "installed")


def check_ytdlp(found: str, today: datetime.date, update: str) -> Check:
    if not found:
        return Check("yt-dlp", "warn", "not installed — YouTube and Spotify links will not work", update)
    try:
        released = datetime.datetime.strptime(found[:10], "%Y.%m.%d").date()
    except ValueError:
        return Check("yt-dlp", "ok", found)
    age = (today - released).days
    if age > YTDLP_STALE_DAYS:
        return Check(
            "yt-dlp", "warn", f"{found} is {age} days old — sites change and old copies break", update
        )
    return Check("yt-dlp", "ok", found)


def check_ffmpeg(
    which: Callable[[str], str | None] = shutil.which,
    libass: Callable[[], bool] = ytjob.burn_in_available,
) -> Check:
    if which("ffmpeg") is None:
        return Check("ffmpeg", "warn", "not found — YouTube downloads above 360p need it", "brew install ffmpeg")
    if not libass():
        return Check(
            "ffmpeg",
            "warn",
            "built without libass — hard subtitles cannot be burned in",
            "brew install homebrew-ffmpeg/ffmpeg/ffmpeg",
        )
    return Check("ffmpeg", "ok", "installed, with subtitle burn-in")


def check_deno(which: Callable[[str], str | None] = shutil.which) -> Check:
    if which("deno") is None:
        return Check(
            "deno", "warn", "not found — yt-dlp needs it to read some YouTube pages", "brew install deno"
        )
    return Check("deno", "ok", "installed")


def check_config(path: Path) -> Check:
    if not path.exists():
        return Check("config", "ok", f"{path} not written yet — defaults in use")
    trouble = config.problem(path)
    if trouble:
        return Check("config", "fail", f"{path}: {trouble} — running on defaults", "fix the file, or move it aside")
    return Check("config", "ok", str(path))


def _creatable(path: Path) -> bool:
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            return False
        probe = probe.parent
    return probe.is_dir() and os.access(probe, os.W_OK)


def check_folders(cfg: config.Config) -> Check:
    folders = {cfg.general.default_dir, *(c.dir for c in cfg.categories.values())}
    blocked = sorted(str(f) for f in folders if not _creatable(f))
    if blocked:
        return Check("folders", "fail", "cannot write to " + ", ".join(blocked), "fix the permissions or the config")
    return Check("folders", "ok", f"{len(folders)} download folders writable")


def check_proxy(
    cfg: config.Config,
    connect: Callable[..., object] = socket.create_connection,
) -> Check:
    if not cfg.proxy:
        return Check("proxy", "ok", "none configured")
    parts = urlsplit(cfg.proxy)
    host, port = parts.hostname or "", parts.port or 0
    if not host or not port:
        return Check("proxy", "fail", f"{cfg.proxy} is not host:port", "set [proxy] url in the config")
    try:
        connection = connect((host, port), timeout=2)
    except OSError as exc:
        return Check(
            "proxy",
            "warn",
            f"{host}:{port} is not answering ({exc}) — `-p` and proxied domains will fail",
            "start the proxy, or change [proxy] url",
        )
    close = getattr(connection, "close", None)
    if close is not None:
        close()
    return Check("proxy", "ok", f"{host}:{port} answers")


def check_daemon(status: str) -> Check:
    if status == "ours":
        return Check("daemon", "ok", f"running on port {daemon.PORT}")
    if status == "foreign":
        return Check(
            "daemon",
            "fail",
            f"port {daemon.PORT} is held by another program",
            "stop it, or run `firelink kill --strays` to see what is listening",
        )
    return Check("daemon", "ok", "not running — starts when something is queued")


def check_strays(found: list[tuple[int, int]]) -> Check:
    if found:
        listed = ", ".join(f"pid {pid} on port {port}" for pid, port in found)
        return Check("strays", "warn", f"aria2 daemons firelink cannot reach: {listed}", "firelink kill --strays")
    return Check("strays", "ok", "none")


def _installs() -> list[str]:
    seen: list[str] = []
    for folder in os.get_exec_path():
        candidate = Path(folder) / "firelink"
        if candidate.is_file() and os.access(candidate, os.X_OK) and str(candidate) not in seen:
            seen.append(str(candidate))
    return seen


def check_installs(found: list[str]) -> Check:
    if len(found) > 1:
        return Check(
            "install",
            "warn",
            f"{len(found)} copies on PATH; {found[0]} answers and hides {', '.join(found[1:])}",
            "keep one: `brew uninstall firelink` or `make uninstall`",
        )
    return Check("install", "ok", found[0] if found else "running from source")


def run_checks(cfg: config.Config, state: Path, config_file: Path) -> list[Check]:
    secret = daemon.read_secret(state)
    return [
        check_aria2(),
        check_ytdlp(ytdlp.installed_version(), datetime.date.today(), install.update_command()),
        check_ffmpeg(),
        check_deno(),
        check_config(config_file),
        check_folders(cfg),
        check_proxy(cfg),
        check_daemon(daemon.port_status(daemon.PORT, secret)),
        check_strays(daemon.strays(state)),
        check_installs(_installs()),
    ]


def report(checks: list[Check], icons: bool) -> list[str]:
    lines = []
    for found in checks:
        mark = _MARK[found.level] if icons else _PLAIN[found.level]
        lines.append(f"  {mark} {found.name:<8} {found.detail}")
        if found.fix:
            lines.append(f"       {theme.glyph('→', icons)} {found.fix}")
    return lines


def exit_code(checks: list[Check]) -> int:
    return 1 if any(found.level == "fail" for found in checks) else 0


def cmd_doctor(cfg: config.Config, state: Path, config_file: Path) -> int:
    checks = run_checks(cfg, state, config_file)
    for line in report(checks, theme.icons_on(cfg)):
        print(line)
    return exit_code(checks)
