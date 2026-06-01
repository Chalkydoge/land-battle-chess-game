"""Read JSONL game records and group them into games."""

import json
from collections import defaultdict
from pathlib import Path


def iter_record_paths(root="records", mode="open"):
    root = Path(root)
    mode_dir = root / mode
    if mode_dir.is_file():
        yield mode_dir
        return
    if not mode_dir.exists():
        return
    for path in sorted(mode_dir.glob("*.jsonl")):
        if path.is_file():
            yield path


def iter_events(paths):
    for path in _as_paths(paths):
        with Path(path).open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                event["_source_path"] = str(path)
                event["_source_line"] = line_no
                yield event


def group_events_by_game(events):
    games = defaultdict(list)
    for event in events:
        game_id = event.get("game_id")
        if game_id:
            games[game_id].append(event)
    return dict(games)


def _as_paths(paths):
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]
