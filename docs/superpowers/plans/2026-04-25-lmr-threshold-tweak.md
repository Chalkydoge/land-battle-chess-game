# LMR Threshold 4 → 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the LMR (Late Move Reduction) starting threshold in `algorithms.py` from `i >= 4` to `i >= 3`, then run the bench harness to decide whether the change is statistically stronger via paired self-play + SPRT.

**Architecture:** Two-line edit in `_alpha_beta` (one in the maximizer branch, one in the minimizer). Validation by running `bench match --baseline v1 --candidate HEAD`. Decision branches based on SPRT result: accept → commit; reject → revert.

**Tech Stack:** Existing harness — no new dependencies, no new modules.

**Reference spec:** `docs/superpowers/specs/2026-04-25-lmr-threshold-tweak-design.md`

---

## File Structure

**Modified files:**
- `algorithms.py:1111` — `i >= 4` → `i >= 3` (maximizer / A side)
- `algorithms.py:1155` — `i >= 4` → `i >= 3` (minimizer / B side)

**New files:**
- `bench/results/lmr3-v1-vs-HEAD.json` — match output (force-added regardless of outcome, for the historical record)

**Modified docs:**
- `docs/superpowers/specs/2026-04-25-lmr-threshold-tweak-design.md` — append "Decision Record" section with W/D/L, Elo, SPRT verdict, node-count comparison.

---

## Task 1: Pre-flight check

**Goal:** Confirm that v1 baseline is the right reference and the working tree is clean before changes.

**Files:** none changed.

- [ ] **Step 1: Verify v1 snapshot exists and matches the LMR-4 state**

Run:
```bash
grep -n "i >= 4 and not is_capture" bench/snapshots/v1/algorithms.py
```
Expected output: two lines (around 1111 and 1155):
```
1111:                if (i >= 4 and not is_capture and depth_left >= 3
1155:                if (i >= 4 and not is_capture and depth_left >= 3
```

If output is missing lines or shows `i >= 3`, abort. Either v1 is wrong (it must be the baseline) or the working tree was already modified.

- [ ] **Step 2: Verify the working tree is clean and on main**

Run:
```bash
git status --short
git rev-parse --abbrev-ref HEAD
```
Expected: no modified tracked files (untracked `CLAUDE.md` is OK), branch `main`.

If unmodified files exist beyond `CLAUDE.md`, ask the user before proceeding.

- [ ] **Step 3: Run the test suite (baseline pass)**

Run:
```bash
cd bench && ../.venv/Scripts/python -m pytest -q
```
Expected: `29 passed` in roughly 20 seconds.

- [ ] **Step 4: Web AI smoke (baseline)**

Run from project root:
```bash
.venv/Scripts/python -c "import algorithms, app, time; b=app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(b,6); print(f'baseline_smoke move={m} time={time.perf_counter()-t:.2f}s'); assert m is not None"
```
Expected: prints `baseline_smoke move=(...) time=~2.00s`, no exception.

This is the reference for after-change comparison.

- [ ] **Step 5: No commit yet** — Task 1 is verification only.

---

## Task 2: Apply the LMR change

**Goal:** Change the LMR starting threshold from 4 to 3 at both call sites.

**Files:**
- Modify: `algorithms.py:1111`
- Modify: `algorithms.py:1155`

- [ ] **Step 1: Edit line 1111 (A-side maximizer)**

Find the block in `algorithms.py` around line 1111 that reads:
```python
                # --- Late Move Reduction (LMR) ---
                reduction = 0
                if (i >= 4 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1
```
Change `i >= 4` to `i >= 3`:
```python
                # --- Late Move Reduction (LMR) ---
                reduction = 0
                if (i >= 3 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1
```

- [ ] **Step 2: Edit line 1155 (B-side minimizer)**

Find the analogous block near line 1155:
```python
                reduction = 0
                if (i >= 4 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1
```
Change `i >= 4` to `i >= 3`:
```python
                reduction = 0
                if (i >= 3 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1
```

- [ ] **Step 3: Verify exactly two changes**

Run:
```bash
git diff --stat algorithms.py
grep -n "i >= 3 and not is_capture" algorithms.py
grep -n "i >= 4 and not is_capture" algorithms.py
```
Expected:
- diff stat shows `algorithms.py | 2 +- ...` (or 4 ± if Python autoformatting introduced more)
- `i >= 3` grep returns exactly two lines
- `i >= 4` grep returns nothing

If `i >= 4` still matches, an edit was missed.

- [ ] **Step 4: No commit yet** — wait until match results come back. We may revert.

---

## Task 3: Post-change regression checks

**Goal:** Confirm the change doesn't break tests or the web path before spending 30 minutes on the match.

**Files:** none changed.

- [ ] **Step 1: Run bench tests**

Run:
```bash
cd bench && ../.venv/Scripts/python -m pytest -q
```
Expected: `29 passed`.

If anything fails, investigate before proceeding. The change should not affect any test (LMR is a search-efficiency optimization, not a behavior change).

- [ ] **Step 2: Web AI smoke (post-change)**

Run from project root:
```bash
.venv/Scripts/python -c "import algorithms, app, time; b=app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(b,6); print(f'post_smoke move={m} time={time.perf_counter()-t:.2f}s'); assert m is not None"
```
Expected: prints a move, time ~2s. The chosen move may differ from baseline (different LMR → different search → possibly different best move), but the call must succeed.

If the call hangs or throws, investigate. The change is structurally trivial; an exception means something unrelated broke.

- [ ] **Step 3: No commit yet.**

---

## Task 4: Run the bench match

**Goal:** Run paired self-play between v1 (baseline) and HEAD (candidate with `i >= 3`) until SPRT decides or 600 games are played.

**Files:** writes `bench/results/lmr3-v1-vs-HEAD.json`.

- [ ] **Step 1: Run the match**

Run from project root:
```bash
.venv/Scripts/python -m bench.cli match \
    --baseline v1 --candidate HEAD \
    --tc 0.1 --max-plies 200 --max-games 600 --workers 4 \
    --out bench/results/lmr3-v1-vs-HEAD.json
```

Expected wall-clock: 30–40 minutes on a 4-worker machine. The CLI prints progress every batch (`[N] W=.. D=.. L=..`).

If the run is interrupted, the JSON file is not written. Re-run from scratch — partial state is not persisted.

- [ ] **Step 2: Read the SPRT verdict**

After completion, the CLI prints a summary block:
```
============================================================
  v1  vs  HEAD
============================================================
  Games:    XXX  (W=YY  D=ZZ  L=WW)
  Elo:      ±N.N  +/- N.N
  SPRT:     <accept_H1 | accept_H0 | undecided>   (LLR=...)
  Time:     N.Ns
============================================================
```

Capture the SPRT decision verbatim — it determines Task 5's branch.

- [ ] **Step 3: No commit yet** — Task 5 routes the result.

---

## Task 5: Decision and disposition

**Goal:** Take action based on the SPRT verdict from Task 4.

**Files:** depends on branch.

The verdict from Task 4 lands in one of three buckets. Follow the matching branch.

### Branch A: `accept_H1` (candidate is stronger)

- [ ] **A1: Stage the changes**

```bash
git add algorithms.py
git add -f bench/results/lmr3-v1-vs-HEAD.json
```

- [ ] **A2: Commit**

```bash
git commit -m "$(cat <<'EOF'
algorithms: LMR threshold 4 -> 3

SPRT accept_H1 over <N> paired self-play games (Elo +<X> ± <Y>,
LLR=<Z>). Reducing search depth one move earlier in the move-ordered
list cuts more nodes than the resulting fail-high re-searches cost.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Replace `<N>`, `<X>`, `<Y>`, `<Z>` with the actual numbers from the SPRT summary.

- [ ] **A3: Skip to Task 6.**

### Branch B: `accept_H0` (candidate is weaker)

- [ ] **B1: Revert the source change**

```bash
git checkout -- algorithms.py
```

Verify `git diff algorithms.py` shows no changes.

- [ ] **B2: Stage and commit only the result JSON as a negative record**

```bash
git add -f bench/results/lmr3-v1-vs-HEAD.json
git commit -m "$(cat <<'EOF'
bench: record — LMR 4->3 rejected by SPRT

SPRT accept_H0 over <N> paired self-play games (Elo <X> ± <Y>,
LLR=<Z>). The reduction triggered too many fail-high re-searches at
this branching factor; net effect was weaker play. Original threshold
restored.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **B3: Skip to Task 6.**

### Branch C: `undecided` after 600 games

- [ ] **C1: Inspect the Elo sign**

Read `summary.elo` from `bench/results/lmr3-v1-vs-HEAD.json`:
```bash
.venv/Scripts/python -c "import json; print(json.load(open('bench/results/lmr3-v1-vs-HEAD.json'))['summary']['elo'])"
```

- [ ] **C2: Stop and ask the user**

Report the Elo and ask: "SPRT undecided after 600 games. Elo estimate is `<X> ± <Y>`. Do you want to (a) keep the change anyway, (b) revert, or (c) extend the budget and re-run?"

Wait for their answer.

- [ ] **C3: Act on user's choice**

- (a) keep → follow Branch A's commit (use SPRT="undecided" in commit message)
- (b) revert → follow Branch B's revert+commit (use SPRT="undecided" in commit message)
- (c) extend → re-run Task 4 with `--max-games 1200 --seed-offset 600` (continue with fresh seeds), then re-run Task 5

After acting, proceed to Task 6.

---

## Task 6: Append decision record to spec

**Goal:** Append a "Decision Record" section to the spec so the outcome is preserved alongside the original hypothesis.

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-lmr-threshold-tweak-design.md`

- [ ] **Step 1: Read summary fields from the result JSON**

```bash
.venv/Scripts/python -c "
import json, statistics
d = json.load(open('bench/results/lmr3-v1-vs-HEAD.json'))
s = d['summary']
games = d['games']
def med(key, owner):
    vals = [g['per_engine'][owner].get(key, 0) for g in games if owner in g['per_engine']]
    return statistics.median(vals) if vals else 0
print(f\"W={s['W']} D={s['D']} L={s['L']} total={s['total']}\")
print(f\"Elo={s['elo']:+.1f} +/- {s['elo_err']:.1f}\")
print(f\"SPRT={s['sprt']} LLR={s['llr']:+.2f}\")
print(f\"wall={s['wall_clock_seconds']:.0f}s\")
print(f\"baseline_nodes_median={med('nodes', 'baseline'):.0f}\")
print(f\"candidate_nodes_median={med('nodes', 'candidate'):.0f}\")
print(f\"baseline_avg_depth_median={med('avg_depth', 'baseline'):.2f}\")
print(f\"candidate_avg_depth_median={med('avg_depth', 'candidate'):.2f}\")
"
```

Capture all printed values.

- [ ] **Step 2: Append a `## 6. Decision Record` section to the spec**

Open `docs/superpowers/specs/2026-04-25-lmr-threshold-tweak-design.md` and append at the end:

```markdown

## 6. Decision Record

**Run date:** <YYYY-MM-DD when match completed>
**Result file:** `bench/results/lmr3-v1-vs-HEAD.json`

| Metric | Value |
|---|---|
| Games | <total> (W=<W>, D=<D>, L=<L>) |
| Elo | <±X.X> ± <Y.Y> |
| SPRT decision | `<accept_H1 / accept_H0 / undecided>` (LLR=<Z>) |
| Wall clock | <Ns> |
| Baseline nodes (median per game) | <N> |
| Candidate nodes (median per game) | <N> |
| Baseline avg completed depth | <X.XX> |
| Candidate avg completed depth | <X.XX> |

**Decision:** <kept the change / reverted / kept on user override / extended budget>.

**Notes:** <one or two sentences observing what the node-count and depth deltas suggest about whether the LMR change actually saved nodes or just shifted them>.
```

Replace `<...>` placeholders with the values from Step 1 and the choice from Task 5.

- [ ] **Step 3: Commit the spec update**

```bash
git add docs/superpowers/specs/2026-04-25-lmr-threshold-tweak-design.md
git commit -m "$(cat <<'EOF'
docs: record LMR 4->3 experiment outcome in spec

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final regression sweep

**Goal:** Whether the change was kept or reverted, confirm the repo is in a healthy state.

**Files:** none changed.

- [ ] **Step 1: Tests pass**

```bash
cd bench && ../.venv/Scripts/python -m pytest -q
```
Expected: `29 passed`.

- [ ] **Step 2: Web AI smoke**

```bash
.venv/Scripts/python -c "import algorithms, app, time; b=app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(b,6); print(f'final_smoke move={m} time={time.perf_counter()-t:.2f}s'); assert m is not None"
```
Expected: prints a move; time ~2s.

- [ ] **Step 3: Check git log**

```bash
git log --oneline e34c66b..HEAD
```
Expected: 1–3 new commits depending on branch:
- Branch A (accepted): 2 commits (algorithms change + spec record)
- Branch B (rejected): 2 commits (negative record + spec record)
- Branch C (extended): possibly more

The git history should tell a clean story of "we tried X, observed Y, decided Z."

---

## Verification checklist

When all 7 tasks are done:

- [ ] `bench/results/lmr3-v1-vs-HEAD.json` exists and is committed (force-added since `*.json` is gitignored)
- [ ] `algorithms.py` matches the chosen branch's expected state (`i >= 3` if accepted, `i >= 4` if reverted)
- [ ] Spec has a Decision Record section with concrete numbers (no `<placeholder>` text remaining)
- [ ] All 29 tests still pass
- [ ] Web AI smoke still works
- [ ] git log tells a coherent story
