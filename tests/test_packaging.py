import pathlib
import tomllib

PYPROJECT = tomllib.loads(pathlib.Path("pyproject.toml").read_text())


def test_a_dl_command_is_declared():
    """Homebrew builds the formula's executables from console scripts. Without
    this entry point the formula would need a shim written by hand."""
    assert PYPROJECT["project"]["scripts"]["dl"] == "dl.__main__:main"


def test_the_licence_is_declared():
    assert PYPROJECT["project"]["license"] == "MIT"
    assert pathlib.Path("LICENSE").exists()


def test_setuptools_is_new_enough_for_pep_639():
    """license-files in [project] is PEP 639, understood from setuptools 77."""
    assert PYPROJECT["build-system"]["requires"] == ["setuptools>=77"]
