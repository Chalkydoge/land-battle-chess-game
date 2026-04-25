import json
import subprocess
import sys
from pathlib import Path
import pytest


REPO = Path(__file__).resolve().parents[2]
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def _run(*args, **kwargs):
    return subprocess.run(
        [str(PYTHON), "-m", "bench.cli", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        **kwargs,
    )


def test_cli_help():
    r = _run("--help")
    assert r.returncode == 0
    assert "freeze" in r.stdout
    assert "match" in r.stdout
    assert "summary" in r.stdout


def test_cli_freeze_creates_snapshot():
    r = _run("freeze", "v1_test_cli")
    try:
        assert r.returncode == 0, r.stderr
        snap = REPO / "bench/snapshots/v1_test_cli"
        assert snap.is_dir()
        assert (snap / "algorithms.py").exists()
    finally:
        import shutil
        snap = REPO / "bench/snapshots/v1_test_cli"
        if snap.exists():
            shutil.rmtree(snap)


def test_cli_match_smoke(tmp_path):
    """End-to-end: freeze, then match HEAD vs HEAD with tiny budget."""
    out = tmp_path / "result.json"
    r = _run("match",
             "--baseline", "HEAD",
             "--candidate", "HEAD",
             "--tc", "0.05",
             "--max-plies", "20",
             "--max-games", "2",
             "--workers", "1",
             "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    data = json.loads(out.read_text())
    assert "summary" in data
    assert data["summary"]["total"] >= 2


def test_cli_summary_prints(tmp_path):
    """Reading back a result file works."""
    out = tmp_path / "result.json"
    _run("match",
         "--baseline", "HEAD", "--candidate", "HEAD",
         "--tc", "0.05", "--max-plies", "20",
         "--max-games", "2", "--workers", "1",
         "--out", str(out))
    r = _run("summary", str(out))
    assert r.returncode == 0
    assert "Elo" in r.stdout or "elo" in r.stdout
