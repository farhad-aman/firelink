"""Tab completion for every shell Homebrew installs it for."""

import shutil
import subprocess

import pytest

from firelink import completion
from firelink import __main__ as entry


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_every_command_is_offered(shell):
    text = completion.script(shell)
    for name in completion.COMMANDS:
        assert name in text


def test_the_completion_list_names_every_real_subcommand():
    """A command added to the CLI and not here would never complete."""
    assert entry.SUBCOMMANDS <= set(completion.COMMANDS)


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_the_script_parses_in_its_shell(shell, tmp_path):
    binary = shutil.which(shell)
    if binary is None:
        pytest.skip(f"{shell} is not installed")
    target = tmp_path / f"firelink.{shell}"
    target.write_text(completion.script(shell))
    flag = "--no-execute" if shell == "fish" else "-n"
    done = subprocess.run([binary, flag, str(target)], capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr


def test_bash_completes_subcommands_and_flags(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    target = tmp_path / "firelink.bash"
    target.write_text(completion.script("bash"))
    probe = (
        f"source {target}; COMP_WORDS=(firelink hi); COMP_CWORD=1; _firelink; echo \"${{COMPREPLY[@]}}\"; "
        f"COMP_WORDS=(firelink history --f); COMP_CWORD=2; _firelink; echo \"${{COMPREPLY[@]}}\""
    )
    said = subprocess.run([bash, "-c", probe], capture_output=True, text=True, timeout=20).stdout.splitlines()
    assert said[0] == "history"
    assert said[1] == "--failed"


def test_the_completion_command_prints_the_script(capsys):
    assert entry.main(["completion", "zsh"]) == 0
    assert capsys.readouterr().out.startswith("#compdef firelink")


def test_an_unknown_shell_is_refused(capsys):
    assert entry.main(["completion", "tcsh"]) == 1
    assert "zsh, bash or fish" in capsys.readouterr().err
