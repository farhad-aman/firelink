import sys

from dl import install


def test_a_cellar_prefix_is_a_homebrew_install(monkeypatch):
    """Homebrew builds into $(brew --prefix)/Cellar/firelink/<version>/libexec,
    so the Cellar segment is what separates a tapped copy from a venv one."""
    monkeypatch.setattr(sys, "prefix", "/opt/homebrew/Cellar/firelink/0.2.0/libexec")
    assert install.by_homebrew() is True


def test_a_venv_prefix_is_not_a_homebrew_install(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "/Users/someone/.local/share/dl/venv")
    assert install.by_homebrew() is False


def test_homebrew_is_told_to_upgrade_through_brew(monkeypatch):
    monkeypatch.setattr(install, "by_homebrew", lambda: True)
    assert install.update_command() == "brew upgrade firelink"


def test_a_source_install_is_told_to_make(monkeypatch):
    """There is no clone to run make in when brew installed it, and no brew
    formula to upgrade when a clone did."""
    monkeypatch.setattr(install, "by_homebrew", lambda: False)
    assert install.update_command() == "make install"


def test_the_version_comes_from_package_metadata():
    assert install.version() != ""


def test_a_package_without_metadata_reports_unknown(monkeypatch):
    """Running out of a checkout with nothing pip-installed. Saying "unknown"
    beats raising in the middle of `dl --version`."""
    from importlib import metadata

    def missing(_name):
        raise metadata.PackageNotFoundError("firelink")

    monkeypatch.setattr(install, "_distribution_version", missing)
    assert install.version() == "unknown"
