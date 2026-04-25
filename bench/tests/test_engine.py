import textwrap
from pathlib import Path
import pytest

from bench import engine


@pytest.fixture
def two_snapshots(tmp_path):
    """Build two trivial 'engine' snapshots, both with VERSION constant."""
    a = tmp_path / "v1"
    b = tmp_path / "v2"
    for d, version in [(a, 1), (b, 2)]:
        d.mkdir()
        (d / "algorithms.py").write_text(textwrap.dedent(f"""
            VERSION = {version}
            STATE = {{}}
            def bump(key):
                STATE[key] = STATE.get(key, 0) + 1
                return STATE[key]
        """), encoding="utf-8")
        # snapshot must contain pieceClasses.py and layout.py too — copy stubs
        (d / "pieceClasses.py").write_text("# stub", encoding="utf-8")
        (d / "layout.py").write_text("# stub", encoding="utf-8")
    return a, b


def test_load_two_snapshots_isolated(two_snapshots):
    a_dir, b_dir = two_snapshots
    eng_a = engine.load("v1", a_dir)
    eng_b = engine.load("v2", b_dir)

    assert eng_a.VERSION == 1
    assert eng_b.VERSION == 2

    # State mutations must not bleed across modules
    eng_a.bump("x")
    eng_a.bump("x")
    eng_b.bump("x")
    assert eng_a.STATE["x"] == 2
    assert eng_b.STATE["x"] == 1


def test_load_returns_module_with_correct_name(two_snapshots):
    a_dir, _ = two_snapshots
    eng = engine.load("v1", a_dir)
    assert eng.__name__ == "bench_engine_v1"
