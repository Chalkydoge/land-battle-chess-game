"""Analysis helpers for recorded open-information games."""

from collections import Counter

from game_records.jsonl import group_events_by_game, iter_events


def analyze_games(paths, game_id=None, min_drop=200, mate_threshold=90000,
                  terminal_window=10):
    games = group_events_by_game(iter_events(paths))
    if game_id is not None:
        games = {game_id: games[game_id]} if game_id in games else {}

    summaries = []
    critical_positions = []
    for gid, events in sorted(games.items()):
        summary = summarize_game(events)
        summaries.append(summary)
        critical_positions.extend(
            find_critical_ai_positions(events, min_drop, mate_threshold)
        )
        if terminal_window > 0:
            summary["terminal_window"] = terminal_ply_window(events, terminal_window)

    return {
        "games": summaries,
        "critical_positions": critical_positions,
    }


def summarize_game(events):
    events = list(events)
    game_id = events[0].get("game_id") if events else None
    counts = Counter(event.get("event") for event in events)
    start = next((event for event in events if event.get("event") == "game_start"), None)
    end = next((event for event in events if event.get("event") == "game_end"), None)
    plies = [event for event in events if event.get("event") == "ply"]
    ai_plies = [event for event in plies if event.get("side") == "A" and event.get("search")]
    ai_scores = [event["search"].get("best_score") for event in ai_plies]
    ai_depths = [event["search"].get("completed_depth", 0) for event in ai_plies]
    timeouts = sum(1 for event in ai_plies if event["search"].get("timed_out"))

    return {
        "game_id": game_id,
        "source_path": events[0].get("_source_path") if events else None,
        "events": dict(counts),
        "config": start.get("config", {}) if start else {},
        "result": end.get("result") if end else None,
        "plies": len(plies),
        "complete": end is not None,
        "ai": {
            "moves": len(ai_plies),
            "score_min": min(ai_scores) if ai_scores else None,
            "score_max": max(ai_scores) if ai_scores else None,
            "avg_depth": (sum(ai_depths) / len(ai_depths)) if ai_depths else 0.0,
            "timeouts": timeouts,
        },
    }


def find_critical_ai_positions(events, min_drop=200, mate_threshold=90000):
    critical = []
    previous_score = None
    for event in events:
        if event.get("event") != "ply" or event.get("side") != "A":
            continue
        search = event.get("search")
        if not search:
            continue
        score = search.get("best_score")
        if score is None:
            continue
        drop = None if previous_score is None else previous_score - score
        reasons = []
        if abs(score) >= mate_threshold:
            reasons.append("mate_score")
        if drop is not None and drop >= min_drop:
            reasons.append("score_drop")
        if reasons:
            critical.append({
                "game_id": event.get("game_id"),
                "ply": event.get("ply"),
                "reasons": reasons,
                "score": score,
                "previous_score": previous_score,
                "drop": drop,
                "board_score": search.get("board_score"),
                "completed_depth": search.get("completed_depth"),
                "timed_out": search.get("timed_out"),
                "move": search.get("best_move") or event.get("move"),
                "position_key_before": event.get("position_key_before"),
                "position_key_after": event.get("position_key_after"),
                "candidates": search.get("candidates", []),
                "source_path": event.get("_source_path"),
                "source_line": event.get("_source_line"),
            })
        previous_score = score
    return critical


def terminal_ply_window(events, size=10):
    plies = [event for event in events if event.get("event") == "ply"]
    window = []
    for event in plies[-size:]:
        item = {
            "ply": event.get("ply"),
            "side": event.get("side"),
            "actor": event.get("actor"),
            "move": event.get("move"),
            "piece": _piece_id(event.get("piece")),
            "target": _piece_id(event.get("target")),
            "combat": event.get("combat", {}).get("kind") if event.get("combat") else None,
            "terminal": event.get("terminal"),
        }
        search = event.get("search")
        if search:
            item["score"] = search.get("best_score")
            item["depth"] = search.get("completed_depth")
        window.append(item)
    return window


def _piece_id(piece_payload):
    if piece_payload is None:
        return None
    return piece_payload.get("id")
