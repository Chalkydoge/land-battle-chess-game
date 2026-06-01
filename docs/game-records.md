# Game Records Architecture

This project stores open-information game records as JSONL event streams. The
data directory is `records/`; the code lives in `game_records/`.

## Code Layout

- `game_records/schema.py` defines stable schema constants and canonical piece,
  cell, and position-key helpers.
- `game_records/recorder.py` writes live Web-game events:
  `game_start`, one `ply` per half-move, and `game_end`.
- `game_records/jsonl.py` reads JSONL files and groups events by `game_id`.
- `game_records/analyze.py` turns recorded games into summaries and highlights
  critical AI positions such as large score drops or mate-score evaluations.
- `game_records/features.py` encodes `board_before + move` pairs into flat
  numeric features from the moving side's perspective.
- `game_records/samples.py` splits full games into `human_policy`,
  `ai_search`, and `value` samples.
- `game_records/cli.py` exposes the analysis workflow:

```powershell
.\.venv\Scripts\python.exe -m game_records.cli analyze --root records --mode open
```

Sample export:

```powershell
.\.venv\Scripts\python.exe -m game_records.cli export-samples --kind human-policy --out records/human_policy.jsonl
.\.venv\Scripts\python.exe -m game_records.cli export-samples --kind ai-search --out records/ai_search.jsonl
.\.venv\Scripts\python.exe -m game_records.cli export-samples --kind value --out records/value.jsonl
```

## Data Flow

1. `app.py` starts a `JsonlGameRecorder` only for `mode == "open"`.
2. The recorder appends events to `records/open/YYYY-MM-DD.jsonl`.
3. Analysis commands read those files without importing Flask.
4. Future training exporters should read from `game_records/jsonl.py` and
   `game_records/analyze.py`, not from `app.py`.

## Current Use For AI Improvement

The first useful workflow is regression analysis:

1. Record human-vs-AI open games.
2. Run the analyzer and inspect critical AI positions.
3. Convert selected positions into fixed regression cases.
4. Tune evaluation/search and verify the same positions no longer collapse.

Policy/value training should come later, after there are enough complete games
to avoid overfitting to one human line.

The first machine-learning target should be move ordering, not leaf
evaluation. `ai_search` samples expose the current engine's candidate order and
chosen move; `human_policy` samples expose winning human moves after side
normalization. A lightweight policy model can consume both and later plug into
`algorithms._move_order_score()`.
