"""Writers in separate processes must not lose each other's lines."""

import json
import subprocess
import sys
import time
from pathlib import Path

from firelink import history, started


def _append_from_another_process(log: Path, name: str) -> subprocess.Popen:
    code = (
        "import sys; from pathlib import Path; from firelink import history; "
        "history.append({'ts': 2, 'name': sys.argv[2]}, Path(sys.argv[1]))"
    )
    return subprocess.Popen([sys.executable, "-c", code, str(log), name])


def test_a_line_appended_during_a_removal_survives_it(tmp_path, monkeypatch):
    log = tmp_path / "history.jsonl"
    history.append({"ts": 1, "name": "old"}, log)
    history.append({"ts": 1, "name": "doomed"}, log)
    writer: list[subprocess.Popen] = []
    real_write = Path.write_text

    def slow_write(self, data, *args, **kwargs):
        if self.name.endswith(".tmp") and not writer:
            writer.append(_append_from_another_process(log, "arrived"))
            time.sleep(0.5)
        return real_write(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", slow_write)
    assert history.remove_entry(log, {"ts": 1, "name": "doomed"}) is True
    writer[0].wait(timeout=10)
    names = [json.loads(line)["name"] for line in log.read_text().splitlines()]
    assert names == ["old", "arrived"]


def test_a_start_time_recorded_during_a_prune_survives_it(tmp_path, monkeypatch):
    started.record(tmp_path, "live", when=1)
    started.record(tmp_path, "gone", when=1)
    writer: list[subprocess.Popen] = []
    real_write = Path.write_text

    def slow_write(self, data, *args, **kwargs):
        if self.name.endswith(".tmp") and not writer:
            code = (
                "import sys; from pathlib import Path; from firelink import started; "
                "started.record(Path(sys.argv[1]), 'new', when=2)"
            )
            writer.append(subprocess.Popen([sys.executable, "-c", code, str(tmp_path)]))
            time.sleep(0.5)
        return real_write(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", slow_write)
    started.prune(tmp_path, ["live", "new"])
    writer[0].wait(timeout=10)
    assert set(started.load(tmp_path)) == {"live", "new"}
