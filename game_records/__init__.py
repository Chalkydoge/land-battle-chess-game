"""Game record storage and analysis helpers."""

from game_records.analyze import analyze_games, summarize_game
from game_records.features import encode_board_move
from game_records.jsonl import group_events_by_game, iter_events, iter_record_paths
from game_records.recorder import JsonlGameRecorder
from game_records.samples import iter_samples, samples_from_game
from game_records.schema import DEFAULT_RECORD_ROOT, SCHEMA


__all__ = [
    "DEFAULT_RECORD_ROOT",
    "SCHEMA",
    "JsonlGameRecorder",
    "analyze_games",
    "encode_board_move",
    "group_events_by_game",
    "iter_samples",
    "iter_events",
    "iter_record_paths",
    "samples_from_game",
    "summarize_game",
]
