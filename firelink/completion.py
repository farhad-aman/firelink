SHELLS = ("zsh", "bash", "fish")

COMMANDS = {
    "ls": "list downloads",
    "history": "list finished downloads",
    "pause": "pause a download, or all",
    "resume": "resume a download, or all",
    "rm": "remove a download",
    "watch": "queue URLs as you copy them",
    "kill": "stop the daemon",
    "doctor": "check the tools, config, proxy and daemon",
    "limit": "set or show the global speed limit",
    "completion": "print a shell completion script",
    "help": "show usage",
}

COMMAND_FLAGS = {
    "history": {"--failed": "only failed downloads", "--json": "print JSON"},
    "ls": {"--json": "print JSON"},
    "kill": {"--strays": "find daemons older versions left behind"},
}

COMMAND_VALUES = {
    "completion": SHELLS,
    "pause": ("all",),
    "resume": ("all",),
    "limit": ("off", "auto"),
}

# (short, long, help, takes): takes is "dir", "file", "text" or "".
ADD_FLAGS = (
    ("d", "dir", "destination folder for this download", "dir"),
    ("f", "file", "queue URLs from a file, or - for stdin", "file"),
    ("p", "proxy", "download through the proxy", ""),
    ("H", "", "extra request header, Key: Value", "text"),
    ("c", "checksum", "verify against a checksum, sha256=<hex>", "text"),
    ("", "no-preview", "queue and exit without the live preview", ""),
    ("", "version", "print the installed version", ""),
    ("h", "help", "show usage", ""),
)


def script(shell: str) -> str:
    return {"zsh": _zsh, "bash": _bash, "fish": _fish}[shell]()


def _zsh_quote(text: str) -> str:
    return text.replace("'", "'\\''").replace(":", "\\:").replace("[", "\\[").replace("]", "\\]")


def _zsh() -> str:
    commands = "\n".join(f"    '{name}:{_zsh_quote(about)}'" for name, about in COMMANDS.items())
    action = {"dir": ":folder:_files -/", "file": ":file:_files", "text": ":value:"}
    flags = []
    for short, long, about, takes in ADD_FLAGS:
        tail = f"[{_zsh_quote(about)}]{action.get(takes, '')}"
        if short and long:
            flags.append(f"    '(-{short} --{long})'{{-{short},--{long}}}'{tail}'")
        else:
            flags.append(f"    '{'-' + short if short else '--' + long}{tail}'")
    cases = []
    for name, known in COMMAND_FLAGS.items():
        listed = " ".join(f"'{flag}[{_zsh_quote(about)}]'" for flag, about in known.items())
        cases.append(f"        {name}) _arguments {listed} '*: :' ;;")
    for name, values in COMMAND_VALUES.items():
        cases.append(f"        {name}) _values '{name}' {' '.join(values)} ;;")
    flag_lines = " \\\n".join(flags)
    case_lines = "\n".join(cases)
    return f"""#compdef firelink

_firelink() {{
  local curcontext="$curcontext" state line
  local -a commands
  commands=(
{commands}
  )
  _arguments -C \\
{flag_lines} \\
    '1: :->first' \\
    '*:: :->rest'
  case $state in
    first)
      _describe -t commands 'firelink command' commands
      _files
      ;;
    rest)
      case $line[1] in
{case_lines}
        *) _files ;;
      esac
      ;;
  esac
}}

_firelink "$@"
"""


def _bash() -> str:
    words = " ".join(list(COMMANDS) + [f"--{long}" for _s, long, _a, _t in ADD_FLAGS if long])
    words += " " + " ".join(f"-{short}" for short, _l, _a, _t in ADD_FLAGS if short)
    cases = []
    for name, known in COMMAND_FLAGS.items():
        cases.append(f'    {name}) COMPREPLY=($(compgen -W "{" ".join(known)}" -- "$cur")) ;;')
    for name, values in COMMAND_VALUES.items():
        cases.append(f'    {name}) COMPREPLY=($(compgen -W "{" ".join(values)}" -- "$cur")) ;;')
    case_lines = "\n".join(cases)
    return f"""# bash completion for firelink

_firelink() {{
  local cur="${{COMP_WORDS[COMP_CWORD]}}"
  local prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  case "$prev" in
    -d|--dir) COMPREPLY=($(compgen -d -- "$cur")); return ;;
    -f|--file) COMPREPLY=($(compgen -f -- "$cur")); return ;;
  esac
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=($(compgen -W "{words}" -- "$cur"))
    return
  fi
  case "${{COMP_WORDS[1]}}" in
{case_lines}
  esac
}}

complete -o default -F _firelink firelink
"""


def _fish_quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _fish() -> str:
    lines = ["# fish completion for firelink", ""]
    for name, about in COMMANDS.items():
        lines.append(f"complete -c firelink -n __fish_use_subcommand -a {name} -d {_fish_quote(about)}")
    for short, long, about, takes in ADD_FLAGS:
        parts = ["complete -c firelink -n __fish_use_subcommand"]
        if short:
            parts.append(f"-s {short}")
        if long:
            parts.append(f"-l {long}")
        if takes == "dir":
            parts.append("-x -a '(__fish_complete_directories)'")
        elif takes == "file":
            parts.append("-r -F")
        elif takes == "text":
            parts.append("-x")
        parts.append(f"-d {_fish_quote(about)}")
        lines.append(" ".join(parts))
    for name, known in COMMAND_FLAGS.items():
        for flag, about in known.items():
            lines.append(
                f"complete -c firelink -n '__fish_seen_subcommand_from {name}' "
                f"-l {flag.lstrip('-')} -d {_fish_quote(about)}"
            )
    for name, values in COMMAND_VALUES.items():
        lines.append(
            f"complete -c firelink -n '__fish_seen_subcommand_from {name}' -x -a '{' '.join(values)}'"
        )
    return "\n".join(lines) + "\n"
