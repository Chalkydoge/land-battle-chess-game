"""Freeze working-copy engine files into bench/snapshots/<tag>/."""

import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS_DIR = REPO_ROOT / "bench" / "snapshots"
ENGINE_FILES = ("algorithms.py", "pieceClasses.py", "layout.py")
HEAD_TAG = "HEAD"


def freeze(tag):
    """Copy current algorithms.py + pieceClasses.py + layout.py to
    bench/snapshots/<tag>/.

    HEAD is reserved and always overwrites; any other tag refuses to overwrite
    an existing snapshot (raises FileExistsError).
    """
    dest = SNAPSHOTS_DIR / tag
    if dest.exists() and tag != HEAD_TAG:
        raise FileExistsError(
            f"snapshot '{tag}' already exists at {dest}; "
            "delete it manually or pick a different tag"
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name in ENGINE_FILES:
        src = REPO_ROOT / name
        if not src.exists():
            raise FileNotFoundError(f"expected source file missing: {src}")
        shutil.copy2(src, dest / name)
    return dest


def resolve(tag):
    """Return the snapshot directory for a tag; raise if missing."""
    dest = SNAPSHOTS_DIR / tag
    if not dest.is_dir():
        raise FileNotFoundError(
            f"no snapshot '{tag}' at {dest}; "
            f"run `python -m bench.cli freeze {tag}` first"
        )
    return dest
