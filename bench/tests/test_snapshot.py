import pytest
from pathlib import Path
from bench import snapshot


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """Build a fake project root with the three files snapshot copies."""
    for name in ("algorithms.py", "pieceClasses.py", "layout.py"):
        (tmp_path / name).write_text(f"# {name}\nVERSION = 1\n", encoding="utf-8")
    monkeypatch.setattr(snapshot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(snapshot, "SNAPSHOTS_DIR", tmp_path / "bench/snapshots")
    return tmp_path


def test_freeze_creates_snapshot(tmp_repo):
    out = snapshot.freeze("v1")
    assert out == tmp_repo / "bench/snapshots/v1"
    for name in ("algorithms.py", "pieceClasses.py", "layout.py"):
        assert (out / name).exists()
        assert (out / name).read_text(encoding="utf-8") == f"# {name}\nVERSION = 1\n"


def test_freeze_named_tag_refuses_overwrite(tmp_repo):
    snapshot.freeze("v1")
    with pytest.raises(FileExistsError):
        snapshot.freeze("v1")


def test_freeze_HEAD_overwrites(tmp_repo):
    snapshot.freeze("HEAD")
    # Modify and re-freeze HEAD — must succeed and reflect the change
    (tmp_repo / "algorithms.py").write_text("VERSION = 2\n", encoding="utf-8")
    snapshot.freeze("HEAD")
    out = tmp_repo / "bench/snapshots/HEAD/algorithms.py"
    assert out.read_text(encoding="utf-8") == "VERSION = 2\n"


def test_resolve_returns_dir(tmp_repo):
    snapshot.freeze("v1")
    assert snapshot.resolve("v1") == tmp_repo / "bench/snapshots/v1"


def test_resolve_missing_raises(tmp_repo):
    with pytest.raises(FileNotFoundError):
        snapshot.resolve("never_frozen")
