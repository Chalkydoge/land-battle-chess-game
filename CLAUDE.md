# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run & Dev Commands

This is a Windows-first project. The repo uses a local `.venv`; dependencies are only Flask.

- **Start the game (one-click)**: `./run-local.bat` — creates `.venv` if needed, installs from `requirements.txt`, auto-picks a free port in 5000-5019, launches browser at `http://127.0.0.1:<port>/`.
- **Update + start**: `./update-and-run.bat` — aborts on uncommitted changes, does `git pull --ff-only`, then runs the launcher.
- **Run Flask directly** (after venv is set up): `.venv/Scripts/python app.py`. Env vars: `APP_HOST` (default `127.0.0.1`), `APP_PORT` (default `5000`), `APP_DEBUG` (default `0`).
- **Quick AI smoke-test** (no server):
  ```bash
  .venv/Scripts/python -c "import algorithms, app, time; board = app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(board, 6); print(f'move={m} score={s} time={time.perf_counter()-t:.2f}s depth={algorithms.LAST_COMPLETED_DEPTH}')"
  ```

There is no test suite and no linter configured. The `.stats` files in the repo root are cProfile outputs from past AI-tuning sessions.

## Architecture

The app is a single-process Flask server (`app.py`) with a single global `GameState`. There is no database and no concurrency — `app.run(threaded=False)` is intentional because the game state is a module-level singleton.

### Request flow

```
Browser (templates/index.html)
   │  POST /api/move {from_row, from_col, to_row, to_col}
   ▼
app.py:make_move — validates via isLegal(), applies player move, then:
   │
   ▼
algorithms.AIMove(board_copy, maxDepth, prev_move)
   │  (deep-copied board; AI is side "A", always maximizer)
   ▼
_root_search → iterative deepening → _alpha_beta → quiescence_search → getBoardScore
```

### Three core modules

| File | Responsibility |
|---|---|
| `app.py` | Flask routes, board setup, layout randomization, piece visibility (hidden-mode masks side A's pieces unless AI marshal is dead), battle event serialization for UI animation |
| `pieceClasses.py` | `Post`/`Camp`/`Headquarters` cell classes (originally Tkinter-drawn — drawing methods remain but the web UI ignores them); piece classes `Mar/Gen/MGen/BGen/Col/Maj/Capt/Lt/Spr/Bomb/LMN/Flag` with `order` and `value` attributes |
| `algorithms.py` | Game rules (`isLegal`, `contact`, `isOver`), AI search (alpha-beta + many optimizations), evaluation (`getBoardScore`) |

### Board conventions

- 12 rows × 5 columns. Side A (AI/orange) occupies rows 0-5; side B (player/blue) occupies rows 6-11.
- Railroads: columns 0 and 4 (rows 1-10) + rows 1, 5, 6, 10 (full width). Stored in `algorithms.railroadPosts`.
- Front-line junctions `(5,1) (5,3) (6,1) (6,3)` are NOT mutually connected — `isLegal` explicitly discards them.
- Camps (diagonal-reachable, protect occupant): `{(2,1), (2,3), (3,2), (4,1), (4,3)}` for A, mirrored for B.
- Headquarters (pieces inside cannot move; flag must be placed here): `{(0,1), (0,3)}` for A, `{(11,1), (11,3)}` for B.
- Piece `order`: higher beats lower. Special cases: `order=10` (mine, immovable) beaten only by `order=1` (sapper). `order=None` (bomb) mutually destroys anything. `order=0` (flag) loses to everything; capturing it ends the game.

### AI engine (read `AI_DESIGN.md` for full rationale)

The AI is called with `set_search_profile("fast")` (easy, 2s limit, qdepth=3, maxDepth=6) or `"strong"` (hard, 5s, qdepth=5, maxDepth=12). Profile settings live in `PROFILE_SETTINGS` at the top of `algorithms.py`.

Search stack: **iterative deepening → aspiration windows → PVS alpha-beta with NMP + LMR + futility pruning + repetition detection → quiescence search → `getBoardScore`**.

Key invariants when modifying the AI:
- **`getBoardScore` must not call `isLegal()`** — it's the hot path. Threat detection uses 4-adjacency plus precomputed `_RAIL_LINES` for remote-railroad threats. Adding an `isLegal` call will collapse search depth by ~150x.
- **`applyMove`/`undoMove` maintain a running `ZOBRIST_HASH`** used as the TT key. If you add a move primitive, it must XOR the hash symmetrically or TT entries will collide across positions.
- **TT is preserved across turns** and only cleared when it exceeds 200k entries; `HISTORY_TABLE` is decayed (÷4) rather than cleared. If you change evaluation semantics, clear both manually on the next move or results will be poisoned.
- `_terminal_score` has a fast path that skips `isOver()` unless one side has only immovable pieces left — do not regress this.

### Move-history debug

`get_last_search_debug()` and `get_plan_debug_snapshot()` return JSON about the last AI move (principal move, completed depth, node count, top candidate moves with ordering scores). These are surfaced via `/api/ai-debug` and embedded in every `/api/move` response for the UI's debug panel.

### Hidden-information mode

When `game.mode == "hidden"`, `serialize_board` and `serialize_move_piece` strip `name`/`order` for side A pieces so the UI only knows they are AI-colored. The AI-side flag is revealed once the AI marshal (`order=9`) is captured — this is tracked in `game.ai_mar_alive` and requires checking every move.

## Legacy Code (do not modify unless asked)

`server.py` + `__init__.py` are the original 2019 Tkinter + socket multiplayer client/server. They share `pieceClasses.py` with the web version. The README marks this path as legacy; the web flow in `app.py` is the canonical entry point now.
