import argparse
import sys
from pathlib import Path

from . import checksum, cli, config, daemon, install, legacy, routing, spotify, ytdlp
from .config import CONFIG_FILE
from .rpc import Aria2Error, Aria2Unreachable
from .tui.preview import Request, run_preview

USAGE = """\
firelink — download manager

  firelink <url> [url...]        queue downloads
  firelink -f <file|->           queue URLs from a file or stdin
  firelink -d <dir> <url>        override the destination for this download
  firelink -p <url>              download through the sing-box proxy
  firelink -H "Key: Value"       extra request header (repeatable)
  firelink -c sha256=<hex>       verify the download against a checksum
  firelink <spotify url>         a track, album or playlist (audio from YouTube)
  firelink <magnet:…>            magnet link
  firelink file.torrent          torrent file, local or over http
  --no-preview                   queue and exit without attaching the live preview
  firelink                       open the TUI
  firelink --version             print the installed version

  firelink ls [name]             list downloads, optionally matching a name (--json)
  firelink history [n] [name]    list finished downloads (--failed, --json)
  firelink pause <gid|all>       firelink resume <gid|all>   firelink rm <gid>
  firelink watch                 queue URLs as you copy them
  firelink kill                  stop the daemon
  firelink kill --strays         find daemons older versions left behind
  firelink doctor                check the tools, config, proxy and daemon
"""

SUBCOMMANDS = {"ls", "history", "pause", "resume", "rm", "watch", "kill", "doctor", "help"}

# Flags each subcommand understands. Anything else is a mistake worth saying so
# about rather than dropping: `firelink ls --failed` used to filter nothing, quietly.
SUBCOMMAND_FLAGS = {
    "kill": {"--strays"},
    "history": {"--failed", "--json"},
    "ls": {"--json"},
}


class ArgError(Exception):
    """A bad command line. Carries the message firelink should print."""


class _Parser(argparse.ArgumentParser):
    """argparse that reports rather than exits.

    The stock parser calls sys.exit(2) from inside error(), which would bypass
    main()'s return codes and print a usage block firelink does not own.
    """

    def error(self, message: str):
        raise ArgError(message)

    def exit(self, status: int = 0, message: str | None = None):
        raise ArgError(message or "")


def _add_parser() -> _Parser:
    parser = _Parser(prog="firelink", add_help=False)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("-d", "--dir", dest="directory")
    parser.add_argument("-f", "--file", dest="url_file")
    parser.add_argument("-p", "--proxy", action="store_true")
    parser.add_argument("-H", dest="headers", action="append", default=[])
    parser.add_argument("-c", "--checksum", dest="digest")
    parser.add_argument("--no-preview", dest="preview", action="store_false", default=True)
    return parser


def _check_flags(command: str, rest: list[str]) -> None:
    allowed = SUBCOMMAND_FLAGS.get(command, set())
    for arg in rest:
        if arg.startswith("-") and arg not in allowed:
            raise ArgError(f"unrecognized argument for {command}: {arg}")


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(list(argv if argv is not None else sys.argv[1:]))
    except ArgError as exc:
        print(f"firelink: {exc}\n\n{USAGE}", file=sys.stderr)
        return 1
    except (Aria2Error, Aria2Unreachable, legacy.LegacyInUse) as exc:
        print(f"firelink: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _run_youtube(cfg, urls: list[str], proxy: bool, interactive: bool) -> int:
    """YouTube needs yt-dlp: aria2 cannot resolve a watch page into streams."""
    if not ytdlp.available():
        print(f"firelink: yt-dlp not found — run `{install.update_command()}`", file=sys.stderr)
        return 1
    if not interactive:
        print("firelink: YouTube downloads need a terminal to choose quality", file=sys.stderr)
        return 1

    from .tui.ytflow import run_youtube

    lines, cancelled = run_youtube(cfg, urls, proxy)
    for line in lines:
        print(line)
    return 130 if cancelled else 0


def _run_spotify(cfg, urls: list[str], interactive: bool) -> int:
    """Spotify needs yt-dlp: the audio is fetched from YouTube, not Spotify."""
    if not ytdlp.available():
        print(f"firelink: yt-dlp not found — run `{install.update_command()}`", file=sys.stderr)
        return 1
    if not interactive:
        print("firelink: Spotify downloads need a terminal to confirm matches", file=sys.stderr)
        return 1

    from .tui.spotapp import run_spotify

    lines, cancelled = run_spotify(cfg, urls)
    for line in lines:
        print(line)
    return 130 if cancelled else 0


def _run(args: list[str]) -> int:
    if args and args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    if args and args[0] == "--version":
        print(f"firelink {install.version()}")
        return 0

    command = args[0] if args and args[0] in SUBCOMMANDS else None
    preview, proxy, headers = True, False, []
    explicit_dir: Path | None = None
    urls: list[str] = []
    digest = ""

    if command is not None:
        _check_flags(command, args[1:])
    else:
        opts = _add_parser().parse_args(args)
        preview, proxy, headers = opts.preview, opts.proxy, opts.headers
        if opts.digest:
            # Checked here, because aria2 refuses a bad one with "we
            # encountered a problem" and no word on which part was wrong.
            try:
                digest = checksum.normalise(opts.digest)
            except checksum.Invalid as exc:
                raise ArgError(f"--checksum: {exc}") from None
        explicit_dir = Path(opts.directory).expanduser() if opts.directory else None
        if opts.url_file:
            try:
                urls = cli.read_url_file(opts.url_file)
            except OSError as exc:
                raise ArgError(str(exc)) from None
        urls += list(opts.urls)

    legacy.adopt(
        legacy.LEGACY_CONFIG_DIR, legacy.LEGACY_STATE_DIR, config.CONFIG_DIR, config.STATE_DIR
    )
    if not CONFIG_FILE.exists():
        config.write_default(CONFIG_FILE)
    cfg = config.load(CONFIG_FILE)

    if command == "kill" and "--strays" in args:
        # Starting a daemon in order to list the ones that should not exist
        # would be a poor answer to the question.
        return cli.cmd_strays(config.STATE_DIR)

    if command == "doctor":
        from . import doctor

        return doctor.cmd_doctor(cfg, config.STATE_DIR, CONFIG_FILE)

    if command == "history":
        # Reading a file needs no daemon, and starting one to print it would be
        # a slow surprise for a command that only looks at the past.
        return cli.cmd_history(cfg, config.STATE_DIR / "history.jsonl", args[1:])

    try:
        client = daemon.ensure_running(cfg)
    except daemon.Aria2Missing as exc:
        print(f"firelink: {exc}", file=sys.stderr)
        return 1
    except daemon.DaemonStartFailed as exc:
        print(f"firelink: {exc}", file=sys.stderr)
        return 1

    if command == "ls":
        query = " ".join(a for a in args[1:] if not a.startswith("-"))
        return cli.cmd_ls(
            cfg,
            client,
            use_color=sys.stdout.isatty(),
            query=query,
            as_json="--json" in args,
        )
    if command == "pause":
        return cli.cmd_pause(args[1] if len(args) > 1 else "all", client)
    if command == "resume":
        return cli.cmd_resume(args[1] if len(args) > 1 else "all", client)
    if command == "rm":
        if len(args) < 2:
            print("firelink: rm needs a gid", file=sys.stderr)
            return 1
        return cli.cmd_rm(args[1], client)
    if command == "kill":
        return cli.cmd_kill(client, config.STATE_DIR)
    if command == "watch":
        from . import watch

        return watch.run(cfg, client)

    if urls:
        # Split before ytdlp is asked: the audio comes from YouTube, but the
        # address that names the track is Spotify's and only this path reads it.
        songs = [u for u in urls if spotify.is_spotify(u)]
        urls = [u for u in urls if u not in songs]
        if songs:
            rc = _run_spotify(cfg, songs, preview and sys.stdout.isatty())
            if rc or not urls:
                return rc
        tube = [u for u in urls if ytdlp.handles(u)]
        urls = [u for u in urls if u not in tube]
        if tube:
            rc = _run_youtube(cfg, tube, proxy, preview and sys.stdout.isatty())
            if rc or not urls:
                return rc

    if urls:
        daemon.bump_generation(config.STATE_DIR)
        interactive = preview and sys.stdout.isatty()
        if not interactive:
            rc, _gids = cli.cmd_add(
                urls, cfg, client, explicit_dir, proxy=proxy, headers=headers, digest=digest
            )
            return rc

        if not all(cli.looks_like_url(u) for u in urls):
            rc, gids = cli.cmd_add(
                urls, cfg, client, explicit_dir, proxy=proxy, headers=headers, digest=digest
            )
            if gids:
                lines, _cancelled = run_preview(cfg, client, gids=gids)
                for line in lines:
                    print(line)
            return rc

        pending = []
        for url in urls:
            name = routing.filename_from_url(url)
            resolved = routing.resolve(url, name, cfg)
            where = explicit_dir if explicit_dir is not None else resolved.path
            pending.append(Request(url, name or url, where, resolved.category))

        outcome = {"rc": 0}

        def queue(chosen, decisions=None):
            rc, gids = cli.cmd_add(
                urls, cfg, client, explicit_dir, chosen or None, proxy,
                decisions or None, headers, digest,
            )
            outcome["rc"] = rc
            return gids

        lines, cancelled = run_preview(
            cfg, client, pending=pending, queue=queue, pick_paths=explicit_dir is None
        )
        for line in lines:
            print(line)
        return 130 if cancelled else outcome["rc"]

    if not sys.stdout.isatty():
        print("firelink: not a terminal — try `firelink ls`", file=sys.stderr)
        return 1

    from .tui.app import run_tui

    return run_tui(cfg, client)


if __name__ == "__main__":
    raise SystemExit(main())
