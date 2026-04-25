# AI Strength Benchmark Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `bench/` Python package that quantifies whether changes to `algorithms.py` make the open-info AI stronger via paired self-play + SPRT decision.

**Architecture:** A multiprocessing tournament runner that loads two snapshots of `algorithms.py` via `importlib`, plays paired games (same opening, swapped colors), and applies SPRT to decide accept/reject early. Each worker process pre-loads both engine modules to amortize import cost.

**Tech Stack:** Python 3.11 stdlib (`multiprocessing`, `importlib.util`, `argparse`, `dataclasses`, `pathlib`), `pytest` for tests. No new runtime dependencies.

**Reference spec:** `docs/superpowers/specs/2026-04-25-ai-strength-benchmark-harness-design.md`

---

## File Structure

**New files:**
- `layout.py` — extracted seedable layout (shared with `app.py`)
- `requirements-dev.txt` — adds `pytest`
- `bench/__init__.py` — package marker
- `bench/snapshot.py` — copy `algorithms.py + pieceClasses.py + layout.py` to `bench/snapshots/<tag>/`
- `bench/engine.py` — load engine module from a snapshot dir via `importlib`
- `bench/stats.py` — Elo + SPRT (pure math, easy to TDD)
- `bench/game.py` — `play_one_game()` single-game runner
- `bench/match.py` — multiprocessing pool + paired openings + tally
- `bench/cli.py` — `argparse` entry: `freeze` / `match` / `summary`
- `bench/tests/__init__.py`
- `bench/tests/test_snapshot.py`
- `bench/tests/test_engine.py`
- `bench/tests/test_stats.py`
- `bench/tests/test_game.py`
- `bench/tests/test_match.py`
- `bench/tests/test_cli.py`
- `bench/.gitignore` — ignore `snapshots/*/` contents and `results/*.json`

**Modified files:**
- `algorithms.py:1257-1292` — add `time_limit_override=None` parameter to `_root_search`
- `app.py:5-247` — replace inline `make_pieces` / `CAMP_POSITIONS_*` / `HQ_POSITIONS_*` / `random_layout_for_side` / `init_board` with imports from `layout.py`

**File responsibilities:**

| File | Owns |
|---|---|
| `layout.py` | Cell-position constants, piece factory, seedable random layout, `build_initial_board(rng)` |
| `bench/snapshot.py` | Filesystem operations on `bench/snapshots/<tag>/` |
| `bench/engine.py` | `importlib`-based loading of an engine snapshot as a module |
| `bench/stats.py` | `Tally` class, `elo()`, `sprt()` — pure functions, no I/O |
| `bench/game.py` | One game; the loop applying moves and detecting termination |
| `bench/match.py` | Scheduling N paired games via `Pool`, aggregating results |
| `bench/cli.py` | argparse, JSON I/O, calls into other modules |

---

## Task 1: Add pytest dev dependency and bench skeleton

**Files:**
- Create: `requirements-dev.txt`
- Create: `bench/__init__.py`
- Create: `bench/tests/__init__.py`
- Create: `bench/.gitignore`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest>=7.0,<9.0
```

- [ ] **Step 2: Install pytest in the venv**

Run: `.venv/Scripts/python -m pip install -r requirements-dev.txt`
Expected: `Successfully installed pytest-...`

- [ ] **Step 3: Create empty package files**

`bench/__init__.py` content:
```python
"""AI strength benchmark harness — see docs/superpowers/specs/2026-04-25-ai-strength-benchmark-harness-design.md."""
```

`bench/tests/__init__.py`: empty file (zero bytes).

- [ ] **Step 4: Create `bench/.gitignore`**

```
snapshots/*/
!snapshots/.gitkeep
results/*.json
__pycache__/
```

Then create the empty `bench/snapshots/.gitkeep` file (zero bytes) so the directory is tracked but its contents are not.

- [ ] **Step 5: Verify pytest discovers the empty test package**

Run: `.venv/Scripts/python -m pytest bench/tests/ -q`
Expected: `no tests ran in 0.0Xs` (exit code 5 — "no tests collected" — is OK at this stage).

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt bench/__init__.py bench/tests/__init__.py bench/.gitignore bench/snapshots/.gitkeep
git commit -m "bench: package skeleton + pytest dev dep"
```

---

## Task 2: Extract `layout.py` with seedable RNG

**Files:**
- Create: `layout.py`
- Modify: `app.py:5-247` (remove the moved code, replace with imports)

The goal: bench needs to construct identical opening boards across paired games. Currently `app.random_layout_for_side` calls module-level `random.choice/shuffle`, so it can't be seeded. We extract it into `layout.py` with an `rng` parameter that defaults to the module-level `random`.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_layout.py`:

```python
import random
import layout


def test_same_seed_same_layout():
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    placement_a = layout.random_layout_for_side("A", rng_a)
    placement_b = layout.random_layout_for_side("A", rng_b)
    # Same seed → identical positions and identical piece classes/orders
    assert sorted(placement_a.keys()) == sorted(placement_b.keys())
    for pos in placement_a:
        pa = placement_a[pos]
        pb = placement_b[pos]
        assert type(pa) is type(pb)
        assert pa.order == pb.order


def test_different_seeds_differ():
    placement_a = layout.random_layout_for_side("A", random.Random(1))
    placement_b = layout.random_layout_for_side("A", random.Random(2))
    # Extremely unlikely two different seeds produce identical placement
    differs = any(
        type(placement_a[pos]) is not type(placement_b.get(pos))
        for pos in placement_a
    )
    assert differs


def test_build_initial_board_deterministic():
    board_a = layout.build_initial_board(random.Random(7))
    board_b = layout.build_initial_board(random.Random(7))
    for r in range(12):
        for c in range(5):
            pa = board_a[r][c].piece
            pb = board_b[r][c].piece
            if pa is None:
                assert pb is None
            else:
                assert type(pa) is type(pb)
                assert pa.side == pb.side
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest bench/tests/test_layout.py -v`
Expected: `ModuleNotFoundError: No module named 'layout'`

- [ ] **Step 3: Create `layout.py`**

Write `layout.py` with this complete content:

```python
"""Seedable layout & board init — shared between app.py (web) and bench/."""

import random as _random_module
from pieceClasses import (
    Mar, Gen, MGen, BGen, Col, Maj, Capt, Lt, Spr, Bomb, LMN, Flag,
    Post, Camp, Headquarters,
)


CAMP_POSITIONS_A = {(2, 1), (2, 3), (3, 2), (4, 1), (4, 3)}
CAMP_POSITIONS_B = {(7, 1), (7, 3), (8, 2), (9, 1), (9, 3)}
HQ_POSITIONS_A = {(0, 1), (0, 3)}
HQ_POSITIONS_B = {(11, 1), (11, 3)}


def make_pieces(side):
    """All 25 pieces for one side."""
    return [
        Mar(side), Gen(side), MGen(side), MGen(side),
        BGen(side), BGen(side), Col(side), Col(side),
        Maj(side), Maj(side), Capt(side), Capt(side), Capt(side),
        Lt(side), Lt(side), Lt(side), Spr(side), Spr(side), Spr(side),
        Bomb(side), Bomb(side), LMN(side), LMN(side), LMN(side),
        Flag(side),
    ]


def random_layout_for_side(side, rng=None):
    """Strategically-weighted random layout, seedable via `rng`.

    rng must be a random.Random instance (or None to use module random).
    """
    if rng is None:
        rng = _random_module

    if side == "A":
        camps = CAMP_POSITIONS_A
        hqs = HQ_POSITIONS_A
        back_rows = {0, 1}
        mid_rows = {2, 3}
        front_rows = {4, 5}
        front_row = 5
    else:
        camps = CAMP_POSITIONS_B
        hqs = HQ_POSITIONS_B
        back_rows = {10, 11}
        mid_rows = {8, 9}
        front_rows = {6, 7}
        front_row = 6

    all_rows = sorted(back_rows | mid_rows | front_rows)
    all_pos = [(r, c) for r in all_rows for c in range(5)
               if (r, c) not in camps and (r, c) not in hqs]
    hq_list = list(hqs)

    pieces = make_pieces(side)
    flag = [p for p in pieces if isinstance(p, Flag)][0]
    lmns = [p for p in pieces if isinstance(p, LMN)]
    bombs = [p for p in pieces if isinstance(p, Bomb)]
    marshal = [p for p in pieces if isinstance(p, Mar)][0]
    general = [p for p in pieces if isinstance(p, Gen)][0]
    mgens = [p for p in pieces if isinstance(p, MGen)]
    bgens = [p for p in pieces if isinstance(p, BGen)]
    sappers = [p for p in pieces if isinstance(p, Spr)]
    others = [p for p in pieces if isinstance(p, (Col, Maj, Capt, Lt))]
    rng.shuffle(others)

    placement = {}

    def available(zone_rows=None):
        return [p for p in all_pos + hq_list
                if p not in placement and
                (zone_rows is None or p[0] in zone_rows)]

    def place_in(piece, candidates):
        opts = [c for c in candidates if c not in placement]
        if not opts:
            opts = [p for p in all_pos + hq_list if p not in placement]
        pos = rng.choice(opts)
        placement[pos] = piece

    flag_pos = rng.choice(hq_list)
    placement[flag_pos] = flag
    fx, fy = flag_pos

    mine_candidates = [p for p in all_pos
                       if p[0] in back_rows and p not in placement]
    mine_candidates.sort(key=lambda p: abs(p[0] - fx) + abs(p[1] - fy))
    for i, lmn in enumerate(lmns):
        placement[mine_candidates[i]] = lmn

    bomb_back = [p for p in all_pos
                 if p[0] in back_rows and p not in placement]
    bomb_back.sort(key=lambda p: abs(p[0] - fx) + abs(p[1] - fy))
    if bomb_back:
        placement[bomb_back[0]] = bombs[0]
    else:
        place_in(bombs[0], available(mid_rows))

    bomb_mid = [p for p in all_pos
                if p[0] in mid_rows and p not in placement]
    rng.shuffle(bomb_mid)
    if bomb_mid:
        placement[bomb_mid[0]] = bombs[1]
    else:
        place_in(bombs[1], [p for p in available() if p[0] != front_row])

    mid_spots = available(mid_rows)
    rng.shuffle(mid_spots)
    for piece in [marshal, general]:
        if mid_spots:
            placement[mid_spots.pop()] = piece
        else:
            place_in(piece, available(back_rows))

    front_spots = available(front_rows)
    rng.shuffle(front_spots)
    for piece in mgens + bgens:
        if front_spots:
            placement[front_spots.pop()] = piece
        else:
            place_in(piece, available(mid_rows))

    rail_spots = [p for p in available() if p[1] in (0, 4)]
    rng.shuffle(rail_spots)
    if rail_spots:
        placement[rail_spots[0]] = sappers[0]
        remaining_sappers = sappers[1:]
    else:
        remaining_sappers = sappers

    fill_pieces = others + remaining_sappers
    rng.shuffle(fill_pieces)
    fill_spots = available()
    rng.shuffle(fill_spots)
    for i, piece in enumerate(fill_pieces):
        placement[fill_spots[i]] = piece

    return placement


def build_initial_board(rng=None):
    """Build a 12x5 board populated with a seeded random layout for both sides."""
    if rng is None:
        rng = _random_module
    board = []
    for r in range(12):
        row = []
        for c in range(5):
            if (r, c) in HQ_POSITIONS_A or (r, c) in HQ_POSITIONS_B:
                row.append(Headquarters(r, c))
            elif (r, c) in CAMP_POSITIONS_A or (r, c) in CAMP_POSITIONS_B:
                row.append(Camp(r, c))
            else:
                row.append(Post(r, c))
        board.append(row)
    for side in ("A", "B"):
        for (r, c), piece in random_layout_for_side(side, rng).items():
            board[r][c].piece = piece
    return board
```

- [ ] **Step 4: Run the test to verify layout works**

Run: `.venv/Scripts/python -m pytest bench/tests/test_layout.py -v`
Expected: `3 passed`

- [ ] **Step 5: Update `app.py` to use `layout.py`**

In `app.py`, find lines around 5-247 covering imports, constants, `make_pieces`, `random_layout_for_side`, and the start of `init_board`. Make these edits:

a) Add this line near the existing imports (alongside `import copy`, `import random`):
```python
import layout
```

b) Replace the four constants `CAMP_POSITIONS_A`, `CAMP_POSITIONS_B`, `HQ_POSITIONS_A`, `HQ_POSITIONS_B` (lines 61-64) with:
```python
from layout import (
    CAMP_POSITIONS_A, CAMP_POSITIONS_B,
    HQ_POSITIONS_A, HQ_POSITIONS_B,
)
```

c) Delete the entire `make_pieces` function (lines 46-55) — `app.py` no longer calls it directly.

d) Delete the entire `random_layout_for_side` function (lines 67-191).

e) Replace the body of `init_board` (lines 194-220) with:
```python
def init_board(randomize=True):
    """Create the 12x5 board. If randomize, generate random legal layouts."""
    if randomize:
        return layout.build_initial_board()
    # Default fixed layout (original) — keep for non-randomized debug
    board = []
    for r in range(12):
        row = []
        for c in range(5):
            if (r, c) in HQ_POSITIONS_A or (r, c) in HQ_POSITIONS_B:
                row.append(Headquarters(r, c))
            elif (r, c) in CAMP_POSITIONS_A or (r, c) in CAMP_POSITIONS_B:
                row.append(Camp(r, c))
            else:
                row.append(Post(r, c))
        board.append(row)
    default = _default_pieces()
    for (r, c), piece in default.items():
        board[r][c].piece = piece
    return board
```

f) The `Post`, `Camp`, `Headquarters` imports in `app.py` are still needed for the non-randomized branch — keep them.

- [ ] **Step 6: Smoke-test the web app still boots and produces a valid board**

Run:
```bash
.venv/Scripts/python -c "import app; b = app.init_board(randomize=True); assert len(b)==12 and len(b[0])==5; print('ok')"
```
Expected: `ok`

Run:
```bash
.venv/Scripts/python -c "import app; b = app.init_board(randomize=False); pieces=sum(1 for r in b for c in r if c.piece); print(f'pieces={pieces}'); assert pieces == 50, pieces"
```
Expected: `pieces=50`

- [ ] **Step 7: Commit**

```bash
git add layout.py app.py bench/tests/test_layout.py
git commit -m "layout: extract seedable layout module shared with bench"
```

---

## Task 3: Add `time_limit_override` to `_root_search`

**Files:**
- Modify: `algorithms.py:1257-1292`

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_time_override.py`:

```python
import time
import random
import layout
import algorithms


def test_time_override_caps_search():
    board = layout.build_initial_board(random.Random(99))
    # With a very short time budget, the search must return well within ~50ms
    # of the budget. Default profile ("fast") would allow up to 2 seconds.
    start = time.perf_counter()
    move, score = algorithms._root_search(
        board, "A", maxDepth=12,
        alpha=-10**9, beta=10**9,
        prev_move=None,
        time_limit_override=0.05,
    )
    elapsed = time.perf_counter() - start
    assert move is not None
    assert elapsed < 0.5, f"override ignored — took {elapsed:.2f}s"


def test_no_override_uses_profile():
    """Sanity: omitting time_limit_override falls back to profile time_limit."""
    board = layout.build_initial_board(random.Random(100))
    algorithms.set_search_profile("fast")  # 2s budget
    start = time.perf_counter()
    move, _ = algorithms._root_search(
        board, "A", maxDepth=12,
        alpha=-10**9, beta=10**9,
        prev_move=None,
    )
    elapsed = time.perf_counter() - start
    assert move is not None
    # Profile budget is 2.0s; allow generous slack.
    assert elapsed < 3.0, f"profile time budget violated — took {elapsed:.2f}s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest bench/tests/test_time_override.py::test_time_override_caps_search -v`
Expected: `TypeError: _root_search() got an unexpected keyword argument 'time_limit_override'`

- [ ] **Step 3: Add the parameter**

In `algorithms.py`, edit the `_root_search` function signature on line 1257 and the deadline assignment around line 1292.

Change line 1257 from:
```python
def _root_search(board, side, maxDepth, alpha, beta, prev_move=None):
```
to:
```python
def _root_search(board, side, maxDepth, alpha, beta, prev_move=None,
                 time_limit_override=None):
```

Change line 1292 from:
```python
    SEARCH_DEADLINE = time.perf_counter() + _profile_value("time_limit")
```
to:
```python
    _tl = time_limit_override if time_limit_override is not None \
          else _profile_value("time_limit")
    SEARCH_DEADLINE = time.perf_counter() + _tl
```

- [ ] **Step 4: Run the override test**

Run: `.venv/Scripts/python -m pytest bench/tests/test_time_override.py -v`
Expected: `2 passed`

- [ ] **Step 5: Smoke-test that web AI still works**

Run:
```bash
.venv/Scripts/python -c "import algorithms, app, time; b=app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(b, 6); print(f'move={m} time={time.perf_counter()-t:.2f}s'); assert m is not None"
```
Expected: a move printed, time < 3s.

- [ ] **Step 6: Commit**

```bash
git add algorithms.py bench/tests/test_time_override.py
git commit -m "algorithms: optional time_limit_override on _root_search"
```

---

## Task 4: Snapshot module — freeze working copy to `bench/snapshots/<tag>/`

**Files:**
- Create: `bench/snapshot.py`
- Create: `bench/tests/test_snapshot.py`

A snapshot is a directory containing immutable copies of `algorithms.py`, `pieceClasses.py`, and `layout.py` from a particular point in time. The tag `HEAD` is reserved — calling `freeze("HEAD")` always overwrites the existing `HEAD` snapshot. Any other tag refuses to overwrite.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_snapshot.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python -m pytest bench/tests/test_snapshot.py -v`
Expected: `ModuleNotFoundError: No module named 'bench.snapshot'`

- [ ] **Step 3: Implement `bench/snapshot.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_snapshot.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add bench/snapshot.py bench/tests/test_snapshot.py
git commit -m "bench: snapshot module — freeze engine files to versioned dirs"
```

---

## Task 5: Engine loader — load a snapshot as an isolated module

**Files:**
- Create: `bench/engine.py`
- Create: `bench/tests/test_engine.py`

Two snapshots must be loadable in the same process with isolated module-level globals (TT, ZOBRIST_HASH, etc). The mechanism: `importlib.util.spec_from_file_location` with a unique synthetic module name per snapshot.

A subtlety: the snapshot's `algorithms.py` does `from pieceClasses import *`. By default Python will resolve `pieceClasses` to whatever's first on `sys.path` — likely the repo-root `pieceClasses.py`. To pin the snapshot's own `pieceClasses.py`, we prepend the snapshot dir to `sys.path` while loading.

This means snapshots conceptually share `pieceClasses` (we use the first-imported one as a singleton). That's intentional — `Piece` classes are pure data containers and don't differ between versions. Tests verify two snapshots can coexist.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python -m pytest bench/tests/test_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'bench.engine'`

- [ ] **Step 3: Implement `bench/engine.py`**

```python
"""Load a snapshot's algorithms.py as an isolated module."""

import sys
import importlib.util
from pathlib import Path


def load(tag, snapshot_dir):
    """Load <snapshot_dir>/algorithms.py as module 'bench_engine_<tag>'.

    The snapshot dir is prepended to sys.path during loading so that
    `from pieceClasses import *` inside algorithms.py resolves to the
    snapshot's own pieceClasses.py.
    """
    snapshot_dir = Path(snapshot_dir)
    algo_path = snapshot_dir / "algorithms.py"
    if not algo_path.is_file():
        raise FileNotFoundError(f"missing algorithms.py in snapshot {snapshot_dir}")

    mod_name = f"bench_engine_{tag}"
    spec = importlib.util.spec_from_file_location(mod_name, algo_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build import spec for {algo_path}")
    module = importlib.util.module_from_spec(spec)

    sys.path.insert(0, str(snapshot_dir))
    try:
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(snapshot_dir))
        except ValueError:
            pass
    return module
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_engine.py -v`
Expected: `2 passed`

- [ ] **Step 5: End-to-end smoke: load real engine snapshot**

Run an inline test that combines snapshot + engine:

```bash
.venv/Scripts/python -c "
from bench import snapshot, engine
import random, layout
p = snapshot.freeze('HEAD')
eng = engine.load('HEAD', p)
board = layout.build_initial_board(random.Random(1))
move, score = eng._root_search(board, 'A', 6, -10**9, 10**9,
                                prev_move=None, time_limit_override=0.1)
print(f'move={move} score={score}')
assert move is not None
"
```
Expected: a move printed, no exceptions.

- [ ] **Step 6: Commit**

```bash
git add bench/engine.py bench/tests/test_engine.py
git commit -m "bench: engine loader with module-level isolation"
```

---

## Task 6: Stats — Tally, Elo, SPRT

**Files:**
- Create: `bench/stats.py`
- Create: `bench/tests/test_stats.py`

Pure math, easy to TDD with closed-form expected values.

- [ ] **Step 1: Write the failing tests**

Create `bench/tests/test_stats.py`:

```python
import math
from bench import stats


def test_tally_starts_zero():
    t = stats.Tally()
    assert t.W == 0 and t.D == 0 and t.L == 0
    assert t.total() == 0


def test_tally_record():
    t = stats.Tally()
    t.record("candidate")
    t.record("candidate")
    t.record("baseline")
    t.record("draw")
    assert t.W == 2 and t.L == 1 and t.D == 1
    assert t.total() == 4


def test_elo_balanced_returns_zero():
    # 50% score → Elo 0
    t = stats.Tally(W=50, D=0, L=50)
    elo, err = stats.elo(t)
    assert abs(elo) < 1e-6
    assert err > 0


def test_elo_perfect_returns_high_value():
    # All wins → very high Elo (capped or clipped)
    t = stats.Tally(W=10, D=0, L=0)
    elo, err = stats.elo(t)
    # Score=1 → log10(1/1 - 1) = -inf, so we expect a large finite cap
    assert elo > 700  # arbitrary high threshold below the cap


def test_elo_known_value():
    # 75% score → Elo = -400 * log10(1/0.75 - 1) ≈ +191
    t = stats.Tally(W=15, D=0, L=5)
    elo, _ = stats.elo(t)
    expected = -400.0 * math.log10(1.0 / 0.75 - 1.0)
    assert abs(elo - expected) < 0.5


def test_sprt_undecided_at_start():
    t = stats.Tally(W=1, D=0, L=1)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "undecided"
    assert -2.95 < decision.llr < 2.95


def test_sprt_accepts_strong_candidate():
    # 200 games, candidate dominant — should accept H1
    t = stats.Tally(W=140, D=20, L=40)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "accept_H1"
    assert decision.llr >= 2.94


def test_sprt_rejects_weak_candidate():
    # Strong negative — should accept H0 (reject H1)
    t = stats.Tally(W=40, D=20, L=140)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "accept_H0"
    assert decision.llr <= -2.94
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest bench/tests/test_stats.py -v`
Expected: `ModuleNotFoundError: No module named 'bench.stats'`

- [ ] **Step 3: Implement `bench/stats.py`**

```python
"""Elo + SPRT statistics for paired self-play."""

import math
from dataclasses import dataclass, field


@dataclass
class Tally:
    """Win/draw/loss counts from the candidate's perspective."""
    W: int = 0  # candidate wins
    D: int = 0
    L: int = 0  # candidate losses

    def record(self, winner):
        if winner == "candidate":
            self.W += 1
        elif winner == "baseline":
            self.L += 1
        elif winner == "draw":
            self.D += 1
        else:
            raise ValueError(f"unknown winner {winner!r}")

    def total(self):
        return self.W + self.D + self.L


@dataclass
class SprtDecision:
    decision: str   # "accept_H0" | "accept_H1" | "undecided"
    llr: float      # log-likelihood ratio
    upper: float    # upper LLR threshold
    lower: float    # lower LLR threshold


_ELO_CAP = 1200.0   # cap when score is 0% or 100% to avoid -inf / +inf


def _score_rate(t):
    n = t.total()
    if n == 0:
        return 0.5
    return (t.W + 0.5 * t.D) / n


def elo(t):
    """Return (elo_estimate, std_error) from a Tally.

    Formula:
      score = (W + D/2) / N
      elo   = -400 * log10(1/score - 1)
      err   ≈ 400 * sqrt(W*L + (W+L)*D/4) / (N * ln(10) * score * (1-score))
    """
    n = t.total()
    if n == 0:
        return 0.0, float("inf")
    score = _score_rate(t)
    if score <= 0.0:
        return -_ELO_CAP, float("inf")
    if score >= 1.0:
        return _ELO_CAP, float("inf")
    elo_est = -400.0 * math.log10(1.0 / score - 1.0)
    var_terms = t.W * t.L + (t.W + t.L) * t.D / 4.0
    if var_terms <= 0 or score in (0.0, 1.0):
        return elo_est, float("inf")
    err = 400.0 * math.sqrt(var_terms) / (n * math.log(10) * score * (1.0 - score))
    return elo_est, err


def _elo_to_score(elo_value):
    """Convert an Elo difference to expected score in [0, 1]."""
    return 1.0 / (1.0 + 10.0 ** (-elo_value / 400.0))


def sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05):
    """Sequential probability ratio test on win/draw/loss counts.

    H0: true Elo = elo0   (typically 0 — change is no improvement)
    H1: true Elo = elo1   (typically +10 — change is a real improvement)

    LLR is approximated by the standard formula used in computer chess:
    each W/D/L contributes log(p_H1 / p_H0) where p_X is the score under that
    hypothesis. The trinomial log-likelihood approximation:
        LLR ≈ W*log(p1/p0) + L*log((1-p1)/(1-p0)) + D*log(d1/d0)
    where p_i is the win-or-half-draw rate under H_i. We use the simpler
    BayesElo model: assume draw rate constant and use score-rate logistic.
    """
    n = t.total()
    upper = math.log((1.0 - beta) / alpha)
    lower = math.log(beta / (1.0 - alpha))

    if n == 0:
        return SprtDecision(decision="undecided", llr=0.0, upper=upper, lower=lower)

    p0 = _elo_to_score(elo0)
    p1 = _elo_to_score(elo1)

    # Treat draws as 0.5 wins, then a binomial likelihood on N "weighted wins":
    #   wins_eq = W + D/2
    #   losses_eq = L + D/2
    # Approx LLR for binomial test with success rates p0 vs p1.
    wins_eq = t.W + 0.5 * t.D
    losses_eq = t.L + 0.5 * t.D
    if not (0 < p0 < 1) or not (0 < p1 < 1):
        return SprtDecision(decision="undecided", llr=0.0, upper=upper, lower=lower)
    llr = (wins_eq * math.log(p1 / p0)
           + losses_eq * math.log((1.0 - p1) / (1.0 - p0)))

    if llr >= upper:
        decision = "accept_H1"
    elif llr <= lower:
        decision = "accept_H0"
    else:
        decision = "undecided"
    return SprtDecision(decision=decision, llr=llr, upper=upper, lower=lower)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_stats.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add bench/stats.py bench/tests/test_stats.py
git commit -m "bench: stats module — Tally, Elo, SPRT"
```

---

## Task 7: Single-game runner

**Files:**
- Create: `bench/game.py`
- Create: `bench/tests/test_game.py`

`play_one_game` takes pre-loaded engine modules (a dict keyed by `"candidate"`/`"baseline"`), a `sideA_owner`, a layout seed, time control, and ply limit. It runs the alternating-move loop and returns a `GameResult`.

Move application uses the *mover's* engine (so each engine applies its own moves). Termination is checked via either engine's `isOver()` (they share the same rules; pick the mover's). Flag-capture is detected by inspecting the move's destination piece *before* applying.

- [ ] **Step 1: Write the failing tests**

Create `bench/tests/test_game.py`:

```python
import random
import pytest
from bench import snapshot, engine, game


@pytest.fixture(scope="module")
def loaded_engines():
    snapshot.freeze("HEAD")
    eng = engine.load("HEAD_a", snapshot.resolve("HEAD"))
    eng2 = engine.load("HEAD_b", snapshot.resolve("HEAD"))
    return {"candidate": eng, "baseline": eng2}


def test_play_one_game_terminates(loaded_engines):
    result = game.play_one_game(
        engines=loaded_engines,
        sideA_owner="candidate",
        layout_seed=42,
        tc=0.05,
        max_plies=60,
    )
    assert result.winner in ("candidate", "baseline", "draw")
    assert 1 <= result.plies <= 60
    assert result.layout_seed == 42
    assert result.sideA_owner == "candidate"
    assert "candidate" in result.per_engine
    assert "baseline" in result.per_engine


def test_paired_game_uses_same_layout(loaded_engines):
    """Two games with the same seed must start from identical boards."""
    import layout
    rng_a = random.Random(7)
    rng_b = random.Random(7)
    board_a = layout.build_initial_board(rng_a)
    board_b = layout.build_initial_board(rng_b)
    for r in range(12):
        for c in range(5):
            pa = board_a[r][c].piece
            pb = board_b[r][c].piece
            if pa is None:
                assert pb is None
            else:
                assert type(pa) is type(pb) and pa.side == pb.side


def test_max_plies_forces_draw(loaded_engines):
    """A pathologically tiny ply cap must yield a draw."""
    result = game.play_one_game(
        engines=loaded_engines,
        sideA_owner="candidate",
        layout_seed=11,
        tc=0.05,
        max_plies=4,
    )
    # 4 plies is way too few to capture a flag from the random start
    assert result.winner == "draw"
    assert result.plies == 4
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest bench/tests/test_game.py -v`
Expected: `ModuleNotFoundError: No module named 'bench.game'`

- [ ] **Step 3: Implement `bench/game.py`**

```python
"""Single-game runner — drives two engine snapshots through one paired game."""

import random
import time
from dataclasses import dataclass, field

import layout


@dataclass
class GameResult:
    winner: str                       # "candidate" / "baseline" / "draw"
    plies: int
    layout_seed: int
    sideA_owner: str                  # "candidate" or "baseline"
    per_engine: dict = field(default_factory=dict)


_OTHER = {"candidate": "baseline", "baseline": "candidate"}


def _opponent(owner):
    return _OTHER[owner]


def play_one_game(engines, sideA_owner, layout_seed, tc, max_plies=300):
    """Play one game between engines["candidate"] and engines["baseline"].

    sideA_owner names which engine plays side "A" (always moves first).
    Returns a GameResult.
    """
    if sideA_owner not in ("candidate", "baseline"):
        raise ValueError(f"bad sideA_owner: {sideA_owner!r}")
    if not {"candidate", "baseline"}.issubset(engines):
        raise ValueError("engines dict must contain 'candidate' and 'baseline'")

    rng = random.Random(layout_seed)
    board = layout.build_initial_board(rng)

    side_to_owner = {
        "A": sideA_owner,
        "B": _opponent(sideA_owner),
    }

    metrics = {
        "candidate": {"nodes": 0, "depths": [], "move_times": []},
        "baseline":  {"nodes": 0, "depths": [], "move_times": []},
    }

    side = "A"
    prev_move = None
    plies = 0
    winner = "draw"

    while plies < max_plies:
        owner = side_to_owner[side]
        eng = engines[owner]

        start = time.perf_counter()
        move, _ = eng._root_search(
            board, side,
            999,
            -10 ** 9, 10 ** 9,
            prev_move=prev_move,
            time_limit_override=tc,
        )
        elapsed = time.perf_counter() - start

        if move is None:
            # No legal move for the current side — opponent wins.
            winner = _opponent(owner)
            break

        metrics[owner]["nodes"] += getattr(eng, "NODE_COUNT", 0)
        metrics[owner]["depths"].append(getattr(eng, "LAST_COMPLETED_DEPTH", 0))
        metrics[owner]["move_times"].append(elapsed)

        fr, fc, tr, tc_col = move
        target_piece = board[tr][tc_col].piece
        flag_captured = target_piece is not None and target_piece.order == 0

        eng.applyMove(board, fr, fc, tr, tc_col)
        plies += 1

        if flag_captured:
            winner = owner
            break

        # If isOver returned True after our move, the side-to-move-next has no
        # legal moves — they lose. Mover wins.
        if eng.isOver(board):
            winner = owner
            break

        side = "B" if side == "A" else "A"
        prev_move = move

    per_engine = {}
    for owner, m in metrics.items():
        depths = m["depths"]
        times = sorted(m["move_times"])
        if times:
            p50 = times[len(times) // 2]
            p95 = times[max(0, int(len(times) * 0.95) - 1)]
        else:
            p50 = p95 = 0.0
        per_engine[owner] = {
            "nodes": m["nodes"],
            "avg_depth": sum(depths) / len(depths) if depths else 0.0,
            "tpm_p50": p50,
            "tpm_p95": p95,
            "moves": len(depths),
        }

    return GameResult(
        winner=winner,
        plies=plies,
        layout_seed=layout_seed,
        sideA_owner=sideA_owner,
        per_engine=per_engine,
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_game.py -v`
Expected: `3 passed` (each game takes a few seconds at tc=0.05)

- [ ] **Step 5: Commit**

```bash
git add bench/game.py bench/tests/test_game.py
git commit -m "bench: single-game runner play_one_game()"
```

---

## Task 8: Match runner — multiprocessing pool + paired openings

**Files:**
- Create: `bench/match.py`
- Create: `bench/tests/test_match.py`

The match runner:
1. Pre-loads engines once per worker via `Pool` initializer.
2. Generates seeds; for each seed dispatches **two** jobs (one with `sideA_owner=candidate`, one with `sideA_owner=baseline`).
3. After each batch, updates `Tally` and runs SPRT; stops on accept/reject or `max_games` hit.

A single seed produces two game results. The seed namespace is a deterministic sequence (start at 0, increment by 1). For reproducibility, `match()` accepts an optional `seed_offset`.

- [ ] **Step 1: Write the failing tests**

Create `bench/tests/test_match.py`:

```python
from pathlib import Path
import pytest
from bench import snapshot, match


@pytest.fixture
def head_snapshot():
    snapshot.freeze("HEAD")
    return snapshot.resolve("HEAD")


def test_match_v1_vs_v1_runs(head_snapshot):
    """Smoke test: HEAD vs HEAD should run a small batch and finish."""
    result = match.run(
        baseline_dir=head_snapshot,
        candidate_dir=head_snapshot,
        tc=0.05,
        max_plies=40,
        max_games=4,
        workers=2,
        elo0=0.0,
        elo1=10.0,
        seed_offset=0,
    )
    assert result.tally.total() >= 4
    assert result.tally.total() <= 4 + 4   # may overshoot by a batch
    assert result.sprt.decision in ("undecided", "accept_H0", "accept_H1")
    assert result.wall_clock_seconds > 0


def test_match_records_per_game(head_snapshot):
    result = match.run(
        baseline_dir=head_snapshot,
        candidate_dir=head_snapshot,
        tc=0.05,
        max_plies=20,
        max_games=2,
        workers=2,
    )
    assert len(result.games) >= 2
    for g in result.games:
        assert g.winner in ("candidate", "baseline", "draw")
        assert g.layout_seed >= 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest bench/tests/test_match.py -v`
Expected: `ModuleNotFoundError: No module named 'bench.match'`

- [ ] **Step 3: Implement `bench/match.py`**

```python
"""Tournament runner — paired openings, multiprocessing, SPRT early-stop."""

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from pathlib import Path

from bench import engine, game, stats


# ---- Worker-process state -------------------------------------------------
# These globals live in each pool-worker process. The initializer populates
# them once, and _play_job uses them.

_WORKER_ENGINES = {}


def _init_worker(baseline_dir, candidate_dir):
    global _WORKER_ENGINES
    _WORKER_ENGINES = {
        "baseline":  engine.load("baseline",  Path(baseline_dir)),
        "candidate": engine.load("candidate", Path(candidate_dir)),
    }


def _play_job(args):
    seed, sideA_owner, tc, max_plies = args
    return game.play_one_game(
        engines=_WORKER_ENGINES,
        sideA_owner=sideA_owner,
        layout_seed=seed,
        tc=tc,
        max_plies=max_plies,
    )


# ---- Result objects -------------------------------------------------------

@dataclass
class MatchResult:
    tally: stats.Tally
    sprt: stats.SprtDecision
    games: list = field(default_factory=list)
    wall_clock_seconds: float = 0.0
    elo: float = 0.0
    elo_err: float = 0.0


def run(baseline_dir, candidate_dir, tc, max_plies, max_games, workers,
        elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05, seed_offset=0,
        progress_cb=None):
    """Run a paired-self-play match and return MatchResult.

    The candidate/baseline distinction is the experimenter's labeling: "is
    candidate stronger than baseline?". Both directories must already contain
    a snapshot (use bench.snapshot.freeze).
    """
    tally = stats.Tally()
    games = []
    start = time.perf_counter()

    ctx = mp.get_context("spawn")  # Windows-safe; isolates worker imports
    with ctx.Pool(
        processes=max(1, workers),
        initializer=_init_worker,
        initargs=(str(baseline_dir), str(candidate_dir)),
    ) as pool:

        next_seed = seed_offset
        while tally.total() < max_games:
            batch_seeds = [next_seed + i for i in range(max(1, workers))]
            next_seed += len(batch_seeds)
            jobs = []
            for s in batch_seeds:
                jobs.append((s, "candidate", tc, max_plies))
                jobs.append((s, "baseline",  tc, max_plies))
            for result in pool.imap_unordered(_play_job, jobs):
                tally.record(result.winner)
                games.append(result)
                if progress_cb:
                    progress_cb(tally, len(games))
            decision = stats.sprt(tally, elo0=elo0, elo1=elo1,
                                  alpha=alpha, beta=beta)
            if decision.decision != "undecided":
                break

    decision = stats.sprt(tally, elo0=elo0, elo1=elo1, alpha=alpha, beta=beta)
    elo_val, elo_err = stats.elo(tally)
    return MatchResult(
        tally=tally,
        sprt=decision,
        games=games,
        wall_clock_seconds=time.perf_counter() - start,
        elo=elo_val,
        elo_err=elo_err,
    )
```

- [ ] **Step 4: Run the match tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_match.py -v`
Expected: `2 passed` (each may take 30-90 seconds — these are real searches).

If multiprocessing throws `RuntimeError: An attempt has been made to start a new process before the current process has finished its bootstrapping phase` on Windows, ensure the test runner does not import bench.match at top level outside `if __name__ == "__main__"`. The current layout is fine because pytest is the entry point — the `spawn` context handles bootstrap correctly.

- [ ] **Step 5: Commit**

```bash
git add bench/match.py bench/tests/test_match.py
git commit -m "bench: tournament runner with paired openings + SPRT early-stop"
```

---

## Task 9: CLI

**Files:**
- Create: `bench/cli.py`
- Create: `bench/tests/test_cli.py`

CLI subcommands:
- `freeze <tag>` — wraps `snapshot.freeze`
- `match --baseline <tag> --candidate <tag> [opts]` — wraps `match.run`, writes JSON
- `summary <results.json>` — re-prints summary from a saved result

Special handling: `--candidate HEAD` triggers an automatic re-snapshot of the working copy before the match.

- [ ] **Step 1: Write the failing test**

Create `bench/tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path
import pytest


REPO = Path(__file__).resolve().parents[2]
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    # Fall back to current interpreter (e.g. CI without venv)
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


def test_cli_freeze_creates_snapshot(tmp_path):
    r = _run("freeze", "v1_test_cli")
    try:
        assert r.returncode == 0, r.stderr
        snap = REPO / "bench/snapshots/v1_test_cli"
        assert snap.is_dir()
        assert (snap / "algorithms.py").exists()
    finally:
        # Clean up
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


def test_cli_summary_prints():
    """Reading back a result file works."""
    # Reuse the file from the smoke test by running it again
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        _run("match",
             "--baseline", "HEAD", "--candidate", "HEAD",
             "--tc", "0.05", "--max-plies", "20",
             "--max-games", "2", "--workers", "1",
             "--out", str(out))
        r = _run("summary", str(out))
        assert r.returncode == 0
        assert "Elo" in r.stdout or "elo" in r.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest bench/tests/test_cli.py::test_cli_help -v`
Expected: `Error: No module named bench.cli` or similar.

- [ ] **Step 3: Implement `bench/cli.py`**

```python
"""Command-line entry: bench.cli freeze | match | summary."""

import argparse
import json
import multiprocessing as mp
import os
import sys
from datetime import date
from pathlib import Path

from bench import snapshot, match


def _cmd_freeze(args):
    out = snapshot.freeze(args.tag)
    print(f"frozen → {out}")
    return 0


def _resolve_or_freeze(tag):
    if tag == snapshot.HEAD_TAG:
        return snapshot.freeze(tag)
    return snapshot.resolve(tag)


def _cmd_match(args):
    baseline_dir = _resolve_or_freeze(args.baseline)
    candidate_dir = _resolve_or_freeze(args.candidate)
    print(f"baseline:  {baseline_dir}")
    print(f"candidate: {candidate_dir}")
    print(f"tc={args.tc}s  max_plies={args.max_plies}  max_games={args.max_games}  workers={args.workers}")

    def progress(tally, n_done):
        if n_done % max(1, args.workers * 2) == 0:
            print(f"  [{n_done:>4}] W={tally.W} D={tally.D} L={tally.L}", flush=True)

    result = match.run(
        baseline_dir=baseline_dir,
        candidate_dir=candidate_dir,
        tc=args.tc,
        max_plies=args.max_plies,
        max_games=args.max_games,
        workers=args.workers,
        elo0=args.elo0,
        elo1=args.elo1,
        alpha=args.alpha,
        beta=args.beta,
        seed_offset=args.seed_offset,
        progress_cb=progress,
    )

    out_path = _default_out_path(args) if args.out is None else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _result_to_payload(result, args)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print()
    _print_summary(payload)
    print(f"\nresults written to {out_path}")
    return 0


def _cmd_summary(args):
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    _print_summary(payload)
    return 0


def _default_out_path(args):
    today = date.today().isoformat()
    return Path("bench/results") / f"{today}-{args.baseline}-vs-{args.candidate}.json"


def _result_to_payload(result, args):
    return {
        "config": {
            "baseline": args.baseline,
            "candidate": args.candidate,
            "tc": args.tc,
            "max_plies": args.max_plies,
            "max_games": args.max_games,
            "workers": args.workers,
            "elo_bounds": [args.elo0, args.elo1],
            "alpha": args.alpha,
            "beta": args.beta,
            "seed_offset": args.seed_offset,
        },
        "games": [
            {
                "winner": g.winner,
                "plies": g.plies,
                "seed": g.layout_seed,
                "sideA_owner": g.sideA_owner,
                "per_engine": g.per_engine,
            }
            for g in result.games
        ],
        "summary": {
            "W": result.tally.W,
            "D": result.tally.D,
            "L": result.tally.L,
            "total": result.tally.total(),
            "elo": result.elo,
            "elo_err": result.elo_err,
            "sprt": result.sprt.decision,
            "llr": result.sprt.llr,
            "wall_clock_seconds": result.wall_clock_seconds,
        },
    }


def _print_summary(payload):
    s = payload["summary"]
    cfg = payload["config"]
    print("=" * 60)
    print(f"  {cfg['baseline']}  vs  {cfg['candidate']}")
    print("=" * 60)
    print(f"  Games:    {s['total']}  (W={s['W']}  D={s['D']}  L={s['L']})")
    print(f"  Elo:      {s['elo']:+.1f}  ± {s['elo_err']:.1f}")
    print(f"  SPRT:     {s['sprt']}   (LLR={s['llr']:+.2f})")
    print(f"  Time:     {s['wall_clock_seconds']:.1f}s")
    print("=" * 60)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze", help="snapshot current engine files")
    p_freeze.add_argument("tag")
    p_freeze.set_defaults(func=_cmd_freeze)

    p_match = sub.add_parser("match", help="paired self-play A/B match")
    p_match.add_argument("--baseline", required=True)
    p_match.add_argument("--candidate", required=True)
    p_match.add_argument("--tc", type=float, default=0.2)
    p_match.add_argument("--max-plies", type=int, default=300)
    p_match.add_argument("--max-games", type=int, default=600)
    p_match.add_argument("--workers", type=int,
                         default=max(1, (os.cpu_count() or 2) - 1))
    p_match.add_argument("--elo0", type=float, default=0.0)
    p_match.add_argument("--elo1", type=float, default=10.0)
    p_match.add_argument("--alpha", type=float, default=0.05)
    p_match.add_argument("--beta", type=float, default=0.05)
    p_match.add_argument("--seed-offset", type=int, default=0)
    p_match.add_argument("--out", default=None,
                         help="output JSON path (default: bench/results/<date>-<base>-vs-<cand>.json)")
    p_match.set_defaults(func=_cmd_match)

    p_sum = sub.add_parser("summary", help="re-print summary from a results JSON")
    p_sum.add_argument("path")
    p_sum.set_defaults(func=_cmd_summary)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    # On Windows, multiprocessing requires this guard when the entry runs the pool.
    mp.freeze_support()
    sys.exit(main())
```

- [ ] **Step 4: Run the CLI tests**

Run: `.venv/Scripts/python -m pytest bench/tests/test_cli.py -v`
Expected: `4 passed` (the smoke tests are slow — total ~2 minutes).

- [ ] **Step 5: Commit**

```bash
git add bench/cli.py bench/tests/test_cli.py
git commit -m "bench: CLI with freeze/match/summary subcommands"
```

---

## Task 10: Validation runs (proves harness self-correctness)

**Files:** none — this task only runs the harness and inspects output.

This is the "is the harness itself trustworthy" gate from spec §11. Every step here must pass before declaring the harness done.

- [ ] **Step 1: Freeze a baseline**

Run: `.venv/Scripts/python -m bench.cli freeze v1`
Expected: `frozen → bench/snapshots/v1`

- [ ] **Step 2: Sanity check — v1 vs v1 should land near 0 Elo**

Run:
```bash
.venv/Scripts/python -m bench.cli match \
    --baseline v1 --candidate v1 \
    --tc 0.1 --max-plies 100 --max-games 200 --workers 4 \
    --out bench/results/sanity-v1-vs-v1.json
```
Expected: SPRT decision is most likely `undecided`; Elo magnitude < ~50; finishes in roughly 5–15 minutes.

If Elo is far from 0 (e.g., > +80 or < -80) with `total >= 100`, the harness has a bug — most likely `sideA_owner` is not actually getting swapped on alternate jobs, or `pool.imap_unordered` is silently dropping results. Investigate before proceeding.

- [ ] **Step 3: Web smoke test — confirm /api/move still works**

In one terminal:
```bash
./run-local.bat
```
In another terminal:
```bash
curl -X POST http://127.0.0.1:5000/api/new-game -H "Content-Type: application/json" -d '{"mode":"open","difficulty":"easy"}'
curl -X POST http://127.0.0.1:5000/api/move -H "Content-Type: application/json" -d '{"from_row":7,"from_col":0,"to_row":6,"to_col":0}'
```
Expected: both calls return `200 OK` with valid JSON.

Stop the server (`Ctrl-C`).

- [ ] **Step 4: Negative control — deliberately weaken the engine and verify SPRT rejects**

Edit `algorithms.py` and find `_piece_score` (line ~452). At the start of the function add:

```python
def _piece_score(piece, largest_opponent_value):
    # NEGATIVE-CONTROL DEBUG ONLY — DELETE BEFORE COMMIT
    return 1.0
```

Save the file. Then run:
```bash
.venv/Scripts/python -m bench.cli match \
    --baseline v1 --candidate HEAD \
    --tc 0.1 --max-plies 100 --max-games 200 --workers 4 \
    --out bench/results/negctl-v1-vs-HEAD.json
```
Expected: SPRT decision is `accept_H0` (Elo strongly negative). The harness *must* be able to detect a deliberately broken engine.

If the result comes back `undecided` or `accept_H1`, the harness has a serious bug — investigate before declaring done.

- [ ] **Step 5: Restore `_piece_score`**

Use `git diff algorithms.py` to verify the only change is the negative-control hack, then revert:

```bash
git checkout -- algorithms.py
```

Verify clean: `git diff algorithms.py` shows nothing.

- [ ] **Step 6: Final positive control — v1 vs HEAD with no engine changes**

```bash
.venv/Scripts/python -m bench.cli match \
    --baseline v1 --candidate HEAD \
    --tc 0.1 --max-plies 100 --max-games 200 --workers 4 \
    --out bench/results/baseline-v1-vs-HEAD.json
```
Expected: same as Step 2 (HEAD == v1 modulo whitespace), Elo near 0.

- [ ] **Step 7: Commit validation results**

```bash
git add bench/results/sanity-v1-vs-v1.json \
        bench/results/negctl-v1-vs-HEAD.json \
        bench/results/baseline-v1-vs-HEAD.json
git commit -m "bench: validation runs proving harness self-correctness"
```

(Result JSONs are usually `.gitignored` per Task 1 — these three are kept as a permanent record. Either remove them from `.gitignore` first, or use `git add -f`.)

- [ ] **Step 8: Final test sweep**

Run: `.venv/Scripts/python -m pytest bench/tests/ -v`
Expected: all tests pass.

---

## Verification checklist

When all 10 tasks are done:

- [ ] `bench freeze v1` produces `bench/snapshots/v1/` with three files
- [ ] `bench match --baseline v1 --candidate HEAD --tc 0.2` runs to completion in ~30 minutes on a 6-core machine
- [ ] Sanity-check (v1 vs v1, 200 games) gives `|Elo| < 50` with most outcomes `undecided`
- [ ] Negative control (deliberately broken eval) gets `accept_H0` (SPRT rejects)
- [ ] `python app.py` still serves the web game; `/api/move` returns valid JSON
- [ ] All `pytest bench/tests/` tests pass
- [ ] No new runtime dependencies (only `pytest` added as dev dep)
