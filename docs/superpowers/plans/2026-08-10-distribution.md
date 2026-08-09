# Distribution via a Homebrew tap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A friend on macOS installs firelink with `brew install farhad-aman/tap/firelink` and updates it with their ordinary `brew upgrade`.

**Architecture:** A Homebrew tap holds one formula that declares `aria2`, `ffmpeg` and `python@3.13` as dependencies and builds firelink into a sealed virtualenv containing every Python dependency, yt-dlp included. Releases are git tags; a GitHub Action rewrites the formula's `url`, `sha256` and resource blocks so no formula field is ever edited by hand. Inside firelink, three messages that hardcode `make install` become install-aware, and a new `dl --version` makes bug reports answerable.

**Tech Stack:** Homebrew formula (Ruby), `Language::Python::Virtualenv`, GitHub Actions on `macos-latest`, setuptools ≥77 (PEP 639), pytest.

**Spec:** `docs/superpowers/specs/2026-08-10-distribution-design.md`

## Global Constraints

- Target is **macOS with Homebrew only**. No Linux, Windows, or brew-less path.
- `requires-python = ">=3.11"`; the formula pins `python@3.13`.
- `build-system.requires = ["setuptools>=77"]` — PEP 639 `license-files` needs it. Already done.
- **`yt_dlp` must be importable inside firelink's own environment.** `dl/ytdlp.py:25` and `:90` import it as a library. If it is not importable, `_load()` returns `[]` and every non-YouTube URL silently routes to aria2, which then saves an HTML page. Nothing raises. No packaging change may break this.
- `pyproject.toml`'s `version` must equal the git tag, minus the leading `v`.
- **Write no comments.** Per the repo's standing instruction, code is self-explanatory through naming; comments only for non-obvious *why*. Match each file's existing density. Test docstrings explaining *why a test exists* are established style in this repo and are welcome.
- Baseline is **1812 tests passing**. Run with `~/.local/share/dl/venv/bin/python -m pytest`. Every task ends green.
- Work happens on the `distribution` branch, already created, holding commit `0123ba9`.

---

### Task 1: A module that knows how firelink was installed

Three separate messages currently hardcode `make install` as the remedy. They need one shared answer, and `dl --version` needs the same module's third function. Put installation facts in one place rather than scattering `sys.prefix` checks.

**Files:**
- Create: `dl/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `install.by_homebrew() -> bool`
  - `install.update_command() -> str` — `"brew upgrade firelink"` or `"make install"`
  - `install.version() -> str` — distribution version, or `"unknown"`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_install.py`:

```python
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
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_install.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'dl.install'`.

- [ ] **Step 3: Write the module**

Create `dl/install.py`:

```python
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
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_install.py -q
```

Expected: 6 passed.

- [ ] **Step 5: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1818 tests.

- [ ] **Step 6: Commit**

```bash
git add dl/install.py tests/test_install.py
git commit -m "Let firelink find out how it was installed"
```

---

### Task 2: Point every remedy at the right command

Three messages send the reader to `make install`. For a tapped copy that names a directory they do not have, and two of the three fire exactly when something has already gone wrong.

**Files:**
- Modify: `dl/ytdlp.py:106-115` (`staleness_advice`) and its imports
- Modify: `dl/__main__.py:93-100` (`_run_youtube`) and its imports
- Modify: `tests/test_ytdlp.py:216-222`
- Modify: `tests/test_main.py:212-220`

**Interfaces:**
- Consumes: `install.update_command() -> str` from Task 1.
- Produces: no new names.

- [ ] **Step 1: Rewrite the two existing tests so they fail**

In `tests/test_ytdlp.py`, replace the body of `test_a_stale_yt_dlp_says_how_to_update` (lines 216-222) with:

```python
def test_a_stale_yt_dlp_says_how_to_update(monkeypatch):
    """A silent stale copy shows up as sites mysteriously breaking, so the
    advice has to name the command that actually works for this install."""
    from dl import install

    monkeypatch.setattr(ytdlp, "age_days", lambda: 200)
    monkeypatch.setattr(install, "update_command", lambda: "brew upgrade firelink")
    advice = ytdlp.staleness_advice()
    assert "brew upgrade firelink" in advice
    assert "200" in advice


def test_a_stale_yt_dlp_in_a_clone_says_make(monkeypatch):
    from dl import install

    monkeypatch.setattr(ytdlp, "age_days", lambda: 200)
    monkeypatch.setattr(install, "update_command", lambda: "make install")
    assert "make install" in ytdlp.staleness_advice()
```

In `tests/test_main.py`, replace lines 219-220 of `test_missing_yt_dlp_is_reported_plainly` with:

```python
    assert entry.install.update_command() in err
```

- [ ] **Step 2: Run those tests and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_ytdlp.py -k stale tests/test_main.py -k missing_yt_dlp -q
```

Expected: FAIL — `staleness_advice` still returns the literal `make install`, and `entry.install` does not exist.

- [ ] **Step 3: Make `staleness_advice` ask**

In `dl/ytdlp.py`, add `install` to the existing relative import on line 6:

```python
from . import install, routing, torrent
```

Replace `staleness_advice` (lines 106-115) with:

```python
def staleness_advice() -> str:
    """Said only when it is old enough to be the reason a site broke.

    firelink installs its own yt-dlp, so the copy on PATH is not the one that
    matters and the remedy depends on how firelink itself arrived.
    """
    days = age_days()
    if days is None or days < STALE_DAYS:
        return ""
    return f"yt-dlp is {days} days old — sites break silently; run `{install.update_command()}`"
```

- [ ] **Step 4: Make the missing-yt-dlp message ask**

In `dl/__main__.py`, add `install` to the import on line 5:

```python
from . import checksum, cli, config, daemon, install, routing, ytdlp
```

Replace line 96 with:

```python
        print(f"dl: yt-dlp not found — run `{install.update_command()}`", file=sys.stderr)
```

- [ ] **Step 5: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1819 tests.

- [ ] **Step 6: Commit**

```bash
git add dl/ytdlp.py dl/__main__.py tests/test_ytdlp.py tests/test_main.py
git commit -m "Name the remedy that fits how firelink was installed"
```

---

### Task 3: `dl --version`

The first question of every bug report a friend files, and today neither party can answer it.

**Files:**
- Modify: `dl/__main__.py:10-30` (`USAGE`) and `:110-113` (`_run`)
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: `install.version() -> str` from Task 1.
- Produces: `dl --version` prints `dl <version>` and returns 0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`:

```python
def test_the_version_flag_prints_the_version(monkeypatch, capsys):
    monkeypatch.setattr(entry.install, "version", lambda: "0.2.0")
    assert entry.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "dl 0.2.0"


def test_the_version_flag_beats_a_url(monkeypatch, capsys):
    """--version is asked in isolation; nothing should queue behind it."""
    monkeypatch.setattr(entry.install, "version", lambda: "0.2.0")
    assert entry.main(["--version", "https://e.com/a.iso"]) == 0
    assert "0.2.0" in capsys.readouterr().out


def test_the_version_flag_is_documented():
    assert "--version" in entry.USAGE
```

- [ ] **Step 2: Run them and watch them fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_main.py -k version -q
```

Expected: FAIL — `--version` is parsed as an unrecognised argument, so `main` returns 1.

- [ ] **Step 3: Handle the flag before anything else**

In `dl/__main__.py`, insert into `_run` immediately after the help check (after line 113):

```python
    if args and args[0] == "--version":
        print(f"dl {install.version()}")
        return 0
```

- [ ] **Step 4: Document it in `USAGE`**

In the `USAGE` string, add a line directly below `  dl                       open the TUI`:

```
  dl --version             print the installed version
```

- [ ] **Step 5: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1822 tests.

- [ ] **Step 6: Verify by hand, because this one is user-facing**

```bash
~/.local/share/dl/venv/bin/python -m dl --version
```

Expected: `dl 0.1.0` — the version currently in `pyproject.toml`.

- [ ] **Step 7: Commit**

```bash
git add dl/__main__.py tests/test_main.py
git commit -m "Answer which version this is"
```

---

### Task 4: A console script, and the version the tag will carry

`virtualenv_install_with_resources` builds a formula's executables from the package's console scripts. Without one the formula needs a hand-written shim.

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_packaging.py` (create)

**Interfaces:**
- Consumes: `main(argv=None) -> int`, already at `dl/__main__.py:80`.
- Produces: a `dl` console script entry point; project version `0.2.0`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_packaging.py -q
```

Expected: FAIL with `KeyError: 'scripts'`. The other two pass already.

- [ ] **Step 3: Declare the script and bump the version**

In `pyproject.toml`, change `version = "0.1.0"` to `version = "0.2.0"`, and add after the `[project.optional-dependencies]` block:

```toml
[project.scripts]
dl = "dl.__main__:main"
```

- [ ] **Step 4: Run the tests**

```bash
~/.local/share/dl/venv/bin/python -m pytest tests/test_packaging.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Prove the entry point actually builds**

```bash
~/.local/share/dl/venv/bin/python -m pip install -q -e . && \
  ~/.local/share/dl/venv/bin/dl --version
```

Expected: `dl 0.2.0`. This is the step that proves the console script works — the pyproject test only proves it was declared.

- [ ] **Step 6: Run the whole suite**

```bash
~/.local/share/dl/venv/bin/python -m pytest -q
```

Expected: exit 0, 1825 tests.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests/test_packaging.py
git commit -m "Declare a dl command so a formula needs no shim"
```

---

### Task 5: The tap, the formula, and the resource question

This task resolves the spec's one unverified assumption. It is deliberately not split: the fallback only becomes necessary if the first command fails, and that is not known until it is run.

**Files:**
- Create: `~/src/homebrew-tap/Formula/firelink.rb` (a new repository)
- Create: `scripts/formula_resources.py` in firelink, **only if Step 4 fails**

**Interfaces:**
- Consumes: the `dl` console script and version `0.2.0` from Task 4.
- Produces: a working `Formula/firelink.rb`, and a proven command sequence for regenerating resource blocks that Task 7 will encode.

- [ ] **Step 1: Publish a release candidate to build the formula against**

A `sha256` cannot be computed until a tarball exists, and a tarball needs a tag. But the branch should not merge before Task 6 has proved the packaging works — so tag a candidate on the branch and keep `v0.2.0` for the merge.

```bash
git push -u origin distribution
git tag v0.2.0-rc1 && git push --tags
```

Every command in this task that names `v0.2.0` uses `v0.2.0-rc1` instead, including the formula's `url`. The real `v0.2.0` is cut in Task 7 Step 4, after the branch has merged. Tasks 7 and 8 continue committing to `distribution`.

- [ ] **Step 2: Create the tap repository**

```bash
gh repo create farhad-aman/homebrew-tap --public \
  --description "Homebrew formulae by Farhad Aman" --clone
```

The `homebrew-` prefix is mandatory — it is what lets the tap be named `farhad-aman/tap`.

- [ ] **Step 3: Write the formula with no resources yet**

Create `Formula/firelink.rb` in the tap:

```ruby
class Firelink < Formula
  include Language::Python::Virtualenv

  desc "Terminal download manager over aria2c"
  homepage "https://github.com/farhad-aman/firelink"
  url "https://github.com/farhad-aman/firelink/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "PLACEHOLDER"
  license "MIT"

  depends_on "aria2"
  depends_on "ffmpeg"
  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/dl --version")
  end
end
```

Fill the real checksum:

```bash
curl -fsSL https://github.com/farhad-aman/firelink/archive/refs/tags/v0.2.0.tar.gz -o /tmp/fl.tar.gz
shasum -a 256 /tmp/fl.tar.gz
```

Replace `PLACEHOLDER` with that hex string, then commit and push the tap.

- [ ] **Step 4: Answer the open question**

```bash
brew tap farhad-aman/tap
brew update-python-resources firelink
```

Expected on success: the formula gains a `resource` block per Python dependency, each with `url` and `sha256`. Inspect it and confirm **`yt-dlp` is among them** — that is the constraint the whole design turns on.

If the command fails because firelink is not on PyPI, go to Step 5. If it succeeds, skip Step 5 and record the exact command for Task 7.

- [ ] **Step 5: Fallback — generate the blocks from the dependency list**

Only if Step 4 failed. Create `scripts/formula_resources.py` in firelink:

```python
import hashlib
import json
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

BLOCK = '  resource "{name}" do\n    url "{url}"\n    sha256 "{sha}"\n  end\n'


def requirements() -> list[str]:
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    return project["dependencies"]


def resolved(specs: list[str]) -> dict[str, str]:
    with subprocess.Popen(
        [sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
         "--report", "-", "--ignore-installed", *specs],
        stdout=subprocess.PIPE,
        text=True,
    ) as proc:
        report = json.load(proc.stdout)
    found = {}
    for item in report["install"]:
        meta = item["metadata"]
        found[meta["name"]] = f"{meta['name']}=={meta['version']}"
    return found


def sdist(pinned: str) -> tuple[str, str]:
    name, version = pinned.split("==")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json") as body:
        data = json.load(body)
    for entry in data["urls"]:
        if entry["packagetype"] == "sdist":
            return entry["url"], entry["digests"]["sha256"]
    raise SystemExit(f"no sdist for {pinned}")


def main() -> int:
    for name, pinned in sorted(resolved(requirements()).items()):
        if name == "firelink":
            continue
        url, sha = sdist(pinned)
        print(BLOCK.format(name=name, url=url, sha=sha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it and paste the output into the formula above `def install`:

```bash
~/.local/share/dl/venv/bin/python scripts/formula_resources.py
```

Commit the script to firelink with `git commit -m "Generate formula resources from the dependency list"`.

- [ ] **Step 6: Audit the formula**

```bash
brew audit --strict --new firelink
```

Fix whatever it names. Common findings: `desc` starting with an article, a missing `license`, resource ordering.

- [ ] **Step 7: Build it for real**

```bash
brew install --build-from-source farhad-aman/tap/firelink
```

Expected: aria2, ffmpeg and python@3.13 install as dependencies, and the build ends with a firelink keg.

- [ ] **Step 8: Run the formula's own test**

```bash
brew test firelink
```

Expected: PASS — `dl --version` prints `dl 0.2.0`, matching `version.to_s`.

- [ ] **Step 9: Commit the tap**

```bash
git -C ~/src/homebrew-tap add Formula/firelink.rb
git -C ~/src/homebrew-tap commit -m "Add firelink 0.2.0"
git -C ~/src/homebrew-tap push
```

---

### Task 6: Prove the packaging did not break routing

A green suite cannot show this. `_load()` swallows `ImportError` and returns `[]`, so a sealed virtualenv missing `yt_dlp` produces no error anywhere — non-YouTube URLs simply start going to aria2, which saves an HTML page named like a video.

**Files:** none. This is verification against the real installation.

**Interfaces:**
- Consumes: the brew-installed `dl` from Task 5.

- [ ] **Step 1: Confirm `dl` on PATH is the brew one**

```bash
which dl
```

Expected: `/opt/homebrew/bin/dl`. If it resolves to `~/.local/bin/dl` instead, the source shim is shadowing the formula — note it, since a friend will not have that shim, and continue using the absolute path `/opt/homebrew/bin/dl` for the rest of this task.

- [ ] **Step 2: Prove `yt_dlp` is importable inside the sealed virtualenv**

```bash
/opt/homebrew/opt/firelink/libexec/bin/python -c \
  "from dl import ytdlp; print(len(ytdlp._extractors()))"
```

Expected: a number in the low thousands. **`0` means the packaging broke routing** — the extractor list is empty and every non-YouTube URL will be mishandled. Stop and fix the formula before going further.

- [ ] **Step 3: Download something that is not YouTube**

```bash
/opt/homebrew/bin/dl "https://x.com/NASA/status/1491475671058681863"
```

Expected: the options screen appears offering 720/360/270 and an English subtitle track — the qualities probed live on 2026-08-10 — and the download completes as an mp4.

- [ ] **Step 4: Download from YouTube**

Use any YouTube URL. Expected: the options screen offers real qualities and the download completes. A failure of `Requested format is not available` means `yt-dlp-ejs` did not make it into the virtualenv, which is the 2026-08-08 regression returning; check that `yt-dlp[default]`'s extras produced resource blocks in the formula.

- [ ] **Step 5: Confirm the stale-advice path names brew**

```bash
/opt/homebrew/opt/firelink/libexec/bin/python -c \
  "from dl import install; print(install.update_command())"
```

Expected: `brew upgrade firelink`. This proves the Cellar detection works against a real keg rather than only against a monkeypatched `sys.prefix`.

---

### Task 7: Release automation

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: the resource-regeneration command proven in Task 5 Step 4 or Step 5.
- Produces: a tag push updates the tap unattended.

- [ ] **Step 1: Create the PAT**

At github.com/settings/personal-access-tokens, create a fine-grained token scoped to `farhad-aman/homebrew-tap` with **Contents: Read and write**. Add it to the firelink repository as a secret named `TAP_TOKEN`:

```bash
gh secret set TAP_TOKEN --repo farhad-aman/firelink
```

This step cannot be automated; the workflow cannot write to the tap without it.

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/release.yml`:

```yaml
name: release

on:
  push:
    tags: ["v*"]

jobs:
  tap:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - name: Refuse a tag that disagrees with pyproject
        run: |
          tag="${GITHUB_REF_NAME#v}"
          declared=$(python3 -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")
          if [ "$tag" != "$declared" ]; then
            echo "tag $tag does not match pyproject version $declared" >&2
            exit 1
          fi

      - name: Checksum the release tarball
        id: tarball
        run: |
          url="https://github.com/${GITHUB_REPOSITORY}/archive/refs/tags/${GITHUB_REF_NAME}.tar.gz"
          curl -fsSL "$url" -o source.tar.gz
          echo "url=$url" >> "$GITHUB_OUTPUT"
          echo "sha256=$(shasum -a 256 source.tar.gz | cut -d' ' -f1)" >> "$GITHUB_OUTPUT"

      - uses: actions/checkout@v4
        with:
          repository: farhad-aman/homebrew-tap
          token: ${{ secrets.TAP_TOKEN }}
          path: tap

      - name: Point the formula at the new tag
        run: |
          formula=tap/Formula/firelink.rb
          sed -i '' -E "s|^  url \".*\"|  url \"${{ steps.tarball.outputs.url }}\"|" "$formula"
          sed -i '' -E "s|^  sha256 \".*\"|  sha256 \"${{ steps.tarball.outputs.sha256 }}\"|" "$formula"

      - name: Regenerate the Python resources
        run: |
          brew tap farhad-aman/tap
          cp tap/Formula/firelink.rb "$(brew --repository farhad-aman/tap)/Formula/firelink.rb"
          brew update-python-resources firelink
          cp "$(brew --repository farhad-aman/tap)/Formula/firelink.rb" tap/Formula/firelink.rb

      - name: Push the formula
        run: |
          cd tap
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add Formula/firelink.rb
          git commit -m "firelink ${GITHUB_REF_NAME#v}"
          git push
```

If Task 5 needed the fallback script, replace the entire `Regenerate the Python resources` step with:

```yaml
      - name: Regenerate the Python resources
        run: |
          python3 scripts/formula_resources.py > /tmp/resources.rb
          python3 - <<'PY'
          import pathlib, re
          formula = pathlib.Path("tap/Formula/firelink.rb")
          blocks = pathlib.Path("/tmp/resources.rb").read_text()
          text = re.sub(r"(  resource .*?\n  end\n)+", "", formula.read_text(), flags=re.S)
          formula.write_text(text.replace("  def install", blocks + "  def install"))
          PY
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "Publish a tag to the tap without touching the formula"
```

- [ ] **Step 4: Check the workflow is well-formed before trusting a tag to it**

```bash
~/.local/share/dl/venv/bin/python -c \
  "import yaml,pathlib;yaml.safe_load(pathlib.Path('.github/workflows/release.yml').read_text());print('parses')"
```

Expected: `parses`. If PyYAML is absent, `gh workflow list` after pushing serves the same purpose — GitHub rejects a malformed workflow.

The workflow is not fired here. It runs for real in Task 9, once the README is done and the branch can merge.

- [ ] **Step 5: Record the manual sequence**

Add a short `## Releasing` section to `README.md` listing the six steps the workflow performs, so a release is still possible when the Action is broken. Commit it with the README work in Task 8.

---

### Task 8: A README that leads with the easy path

**Files:**
- Modify: `README.md:11-25`

**Interfaces:** none.

- [ ] **Step 1: Replace the install section**

Replace lines 11-25 of `README.md` with the following (the outer fence below is four backticks so the nested ones survive — write only what is inside it):

````markdown
## Install

```bash
brew install farhad-aman/tap/firelink
```

That brings `aria2` and `ffmpeg` with it. The command is `dl`.

```bash
brew upgrade firelink    # or just `brew upgrade`, it rides along
brew uninstall firelink
```

### From source

```bash
brew install aria2 ffmpeg
git clone https://github.com/farhad-aman/firelink.git
cd firelink && make install
```

That creates a private venv at `~/.local/share/dl/venv` and writes a `dl` shim
to `~/.local/bin/dl`. System Python is untouched.

```bash
make test        # run the suite
make uninstall   # remove venv and shim
```
````

Note the source path now names `ffmpeg` too, which the old text omitted entirely — it was discovered by users when a YouTube merge failed.

- [ ] **Step 2: Fix the two stale remedies elsewhere in the README**

Search for other references that assume a clone:

```bash
grep -n "make install" README.md
```

Every hit outside the "From source" section should read `brew upgrade firelink` or name both paths.

- [ ] **Step 3: Add the `## Releasing` section from Task 7 Step 5**

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Lead with the install a friend can actually follow"
```

---

---

### Task 9: Merge and cut the first real release

Task 6 has proved the packaging, Task 8 has fixed the documentation, so the branch can land and carry a genuine tag through the workflow.

**Files:** none.

**Interfaces:**
- Consumes: the workflow from Task 7 and the `TAP_TOKEN` secret.

- [ ] **Step 1: Merge the branch**

```bash
git push
gh pr create --fill --base main && gh pr merge --merge
git checkout main && git pull
```

- [ ] **Step 2: Tag the release and watch the workflow**

```bash
git tag v0.2.0 && git push --tags
gh run watch
```

Expected: the run goes green and the tap gains a commit named `firelink 0.2.0`, replacing the hand-built `v0.2.0-rc1` formula from Task 5.

- [ ] **Step 3: Prove the whole design from a user's side**

```bash
brew update && brew upgrade firelink && dl --version
```

Expected: `dl 0.2.0`. This is a version reaching a machine through nothing but `brew upgrade` — the thing the entire plan exists to make true.

- [ ] **Step 4: Delete the candidate tag**

```bash
git tag -d v0.2.0-rc1 && git push origin :refs/tags/v0.2.0-rc1
```

- [ ] **Step 5: Send a friend one line**

```
brew install farhad-aman/tap/firelink
```

If they need anything else, this plan did not finish.

---

## Verification

Run at the end of the whole plan:

```bash
~/.local/share/dl/venv/bin/python -m pytest -q               # exit 0, ~1825 tests
brew audit --strict firelink                                  # clean
brew test firelink                                            # pass
grep -rn "make install" dl/ | grep -v "^dl/install.py"        # no hits
```

The last one matters: `dl/install.py` is the one place allowed to name a remedy, and the grep proves no other module hardcodes one behind Task 2's change.
