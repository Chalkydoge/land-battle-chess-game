"""Convert recorded games into policy/search/value samples."""

from game_records.features import encode_board_move
from game_records.jsonl import group_events_by_game, iter_events


SAMPLE_TYPES = {"human_policy", "ai_search", "value"}


def iter_samples(paths, sample_types=None, include_unfinished=False, with_features=True):
    sample_types = set(sample_types or SAMPLE_TYPES)
    unknown = sample_types - SAMPLE_TYPES
    if unknown:
        raise ValueError(f"unknown sample types: {sorted(unknown)}")

    games = group_events_by_game(iter_events(paths))
    for events in games.values():
        yield from samples_from_game(
            events,
            sample_types=sample_types,
            include_unfinished=include_unfinished,
            with_features=with_features,
        )


def samples_from_game(events, sample_types=None, include_unfinished=False,
                      with_features=True):
    sample_types = set(sample_types or SAMPLE_TYPES)
    events = list(events)
    start = next((event for event in events if event.get("event") == "game_start"), None)
    end = next((event for event in events if event.get("event") == "game_end"), None)
    if start is None:
        return
    if end is None and not include_unfinished:
        return

    catalog = dict(start.get("piece_catalog", {}))
    result = end.get("result") if end else None
    value_target_a = _value_target_for_a(result)

    for event in events:
        if event.get("event") != "ply":
            continue
        _merge_piece(catalog, event.get("piece"))
        _merge_piece(catalog, event.get("target"))

        if "human_policy" in sample_types and event.get("actor") == "human":
            yield _chosen_move_sample(
                "human_policy", event, catalog, result, with_features
            )

        if "ai_search" in sample_types and event.get("actor") == "ai" and event.get("search"):
            yield from _ai_search_samples(event, catalog, result, with_features)

        if "value" in sample_types:
            yield _value_sample(event, catalog, result, value_target_a)


def _chosen_move_sample(sample_type, event, catalog, result, with_features):
    sample = {
        "sample_type": sample_type,
        "game_id": event.get("game_id"),
        "ply": event.get("ply"),
        "side": event.get("side"),
        "actor": event.get("actor"),
        "position_key": event.get("position_key_before"),
        "move": event.get("move"),
        "piece": event.get("piece"),
        "target": event.get("target"),
        "label": 1,
        "outcome_for_side": _outcome_for_side(result, event.get("side")),
        "result": result,
        "source_path": event.get("_source_path"),
        "source_line": event.get("_source_line"),
    }
    if with_features:
        sample["features"] = encode_board_move(
            event["board_before"], event["move"], catalog, event.get("side")
        )
    return sample


def _ai_search_samples(event, catalog, result, with_features):
    search = event.get("search", {})
    chosen = search.get("best_move")
    if chosen is None:
        chosen = event.get("move")
    candidates = search.get("candidates", [])
    for rank, candidate in enumerate(candidates, start=1):
        move = candidate.get("move")
        if move is None:
            continue
        sample = {
            "sample_type": "ai_search",
            "game_id": event.get("game_id"),
            "ply": event.get("ply"),
            "side": event.get("side"),
            "actor": event.get("actor"),
            "position_key": event.get("position_key_before"),
            "move": {"from": move[0], "to": move[1]},
            "candidate_rank": rank,
            "candidate_order_score": candidate.get("order_score"),
            "label": 1 if _same_move(move, chosen) else 0,
            "search_score": search.get("best_score"),
            "board_score": search.get("board_score"),
            "completed_depth": search.get("completed_depth"),
            "timed_out": search.get("timed_out"),
            "outcome_for_side": _outcome_for_side(result, event.get("side")),
            "result": result,
            "source_path": event.get("_source_path"),
            "source_line": event.get("_source_line"),
        }
        if with_features:
            sample["features"] = encode_board_move(
                event["board_before"], sample["move"], catalog, event.get("side")
            )
        yield sample


def _value_sample(event, catalog, result, value_target_a):
    side = event.get("side")
    target_for_side = value_target_a if side == "A" else -value_target_a
    return {
        "sample_type": "value",
        "game_id": event.get("game_id"),
        "ply": event.get("ply"),
        "side": side,
        "actor": event.get("actor"),
        "position_key": event.get("position_key_before"),
        "board": event.get("board_before"),
        "value_target_a": value_target_a,
        "value_target_side": target_for_side,
        "result": result,
        "source_path": event.get("_source_path"),
        "source_line": event.get("_source_line"),
    }


def _merge_piece(catalog, piece):
    if piece is not None:
        catalog[piece["id"]] = piece


def _outcome_for_side(result, side):
    if not result or result.get("winner") is None:
        return 0
    if result.get("winner") == side:
        return 1
    if result.get("winner") == "draw":
        return 0
    return -1


def _value_target_for_a(result):
    if not result or result.get("winner") in (None, "draw"):
        return 0
    return 1 if result.get("winner") == "A" else -1


def _same_move(a, b):
    return tuple(_flat_move(a)) == tuple(_flat_move(b))


def _flat_move(move):
    if isinstance(move, dict):
        return [*move["from"], *move["to"]]
    if len(move) == 2:
        return [*move[0], *move[1]]
    return list(move)
