import json
import random

import algorithms
import layout
from game_records import JsonlGameRecorder, SCHEMA
from game_records.analyze import analyze_games
from game_records.features import encode_board_move
from game_records.samples import samples_from_game


def _first_legal_move(board, side):
    for r in range(12):
        for c in range(5):
            piece = board[r][c].piece
            if piece is None or piece.side != side:
                continue
            moves = algorithms.isLegal(board, (r, c))
            if moves:
                tr, tc = sorted(moves)[0]
                return (r, c, tr, tc)
    raise AssertionError(f"no legal move for {side}")


def test_jsonl_recorder_writes_open_game_events(tmp_path):
    board = layout.build_initial_board(random.Random(7))
    recorder = JsonlGameRecorder(record_root=tmp_path).start_game(board, {
        "source": "test",
        "mode": "open",
        "visibility": "full",
        "layout_seed": 7,
        "side_to_move": "B",
    })

    move = _first_legal_move(board, "B")
    fr, fc, tr, tc = move
    piece = board[fr][fc].piece
    target = board[tr][tc].piece
    before = recorder.serialize_board_state(board)
    combat = recorder.combat_payload(piece, target)
    algorithms.applyMove(board, fr, fc, tr, tc)
    after = recorder.serialize_board_state(board)

    recorder.record_ply(
        "B", "human", move, piece, target,
        before, after, combat=combat, next_side="A",
    )
    recorder.finish("A", "test_finished", board)

    lines = [json.loads(line) for line in recorder.path.read_text(encoding="utf-8").splitlines()]
    assert [line["event"] for line in lines] == ["game_start", "ply", "game_end"]
    assert all(line["schema"] == SCHEMA for line in lines)
    assert lines[0]["initial_board"] == before
    assert lines[1]["piece"]["id"].startswith("B-")
    assert lines[1]["board_before"] == before
    assert lines[1]["board_after"] == after
    assert lines[2]["result"]["winner"] == "A"


def test_app_open_mode_starts_recorder(tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setenv("GAME_RECORD_DIR", str(tmp_path))
    client = app_module.app.test_client()
    response = client.post("/api/new-game", json={"mode": "open", "difficulty": "easy"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recording"]["enabled"] is True
    assert payload["recording"]["schema"] == SCHEMA
    assert tmp_path in app_module.game.recorder.path.parents


def test_analyze_records_finds_ai_score_drop(tmp_path):
    path = tmp_path / "open" / "sample.jsonl"
    path.parent.mkdir()
    events = [
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "game_start",
            "config": {"mode": "open"},
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "ply",
            "ply": 2,
            "side": "A",
            "actor": "ai",
            "move": {"from": [5, 0], "to": [6, 0]},
            "position_key_before": "before-2",
            "position_key_after": "after-2",
            "search": {"best_score": -30, "board_score": -20, "completed_depth": 4},
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "ply",
            "ply": 4,
            "side": "A",
            "actor": "ai",
            "move": {"from": [6, 0], "to": [7, 0]},
            "position_key_before": "before-4",
            "position_key_after": "after-4",
            "search": {"best_score": -400, "board_score": -50, "completed_depth": 5},
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "game_end",
            "result": {"winner": "B", "reason": "flag_capture", "plies": 5},
        },
    ]
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    report = analyze_games([path], min_drop=200)

    assert report["games"][0]["result"]["winner"] == "B"
    assert report["critical_positions"][0]["ply"] == 4
    assert report["critical_positions"][0]["reasons"] == ["score_drop"]


def test_feature_encoder_normalizes_b_side_attack():
    board = [[None for _ in range(5)] for _ in range(12)]
    board[0][3] = "A-FLAG-1"
    board[11][1] = "B-FLAG-1"
    board[2][3] = "B-MGEN-1"
    catalog = {
        "A-FLAG-1": {"id": "A-FLAG-1", "side": "A", "kind": "FLAG", "order": 0, "value": 10000},
        "B-FLAG-1": {"id": "B-FLAG-1", "side": "B", "kind": "FLAG", "order": 0, "value": 10000},
        "B-MGEN-1": {"id": "B-MGEN-1", "side": "B", "kind": "MGEN", "order": 7, "value": 55},
    }

    features = encode_board_move(board, {"from": [2, 3], "to": [1, 3]}, catalog, "B")

    assert features["moving_MGEN"] == 1.0
    assert features["toward_enemy_flag"] == 1.0
    assert features["to_row"] > features["from_row"]


def test_samples_split_human_policy_ai_search_and_value():
    board_before = [[None for _ in range(5)] for _ in range(12)]
    board_before[0][3] = "A-FLAG-1"
    board_before[11][1] = "B-FLAG-1"
    board_before[2][3] = "B-MGEN-1"
    board_after = [row[:] for row in board_before]
    board_after[2][3] = None
    board_after[1][3] = "B-MGEN-1"
    catalog = {
        "A-FLAG-1": {"id": "A-FLAG-1", "side": "A", "kind": "FLAG", "order": 0, "value": 10000},
        "B-FLAG-1": {"id": "B-FLAG-1", "side": "B", "kind": "FLAG", "order": 0, "value": 10000},
        "B-MGEN-1": {"id": "B-MGEN-1", "side": "B", "kind": "MGEN", "order": 7, "value": 55},
    }
    events = [
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "game_start",
            "piece_catalog": catalog,
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "ply",
            "ply": 1,
            "side": "B",
            "actor": "human",
            "move": {"from": [2, 3], "to": [1, 3]},
            "piece": catalog["B-MGEN-1"],
            "target": None,
            "board_before": board_before,
            "board_after": board_after,
            "position_key_before": "p1",
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "ply",
            "ply": 2,
            "side": "A",
            "actor": "ai",
            "move": {"from": [0, 3], "to": [1, 3]},
            "piece": catalog["A-FLAG-1"],
            "target": catalog["B-MGEN-1"],
            "board_before": board_after,
            "board_after": board_after,
            "position_key_before": "p2",
            "search": {
                "best_move": [[0, 3], [1, 3]],
                "best_score": -5,
                "board_score": -3,
                "completed_depth": 4,
                "candidates": [
                    {"move": [[0, 3], [1, 3]], "order_score": 100},
                    {"move": [[0, 3], [0, 2]], "order_score": 50},
                ],
            },
        },
        {
            "schema": SCHEMA,
            "game_id": "g1",
            "event": "game_end",
            "result": {"winner": "B", "reason": "flag_capture", "plies": 2},
        },
    ]

    samples = list(samples_from_game(events))
    human = [s for s in samples if s["sample_type"] == "human_policy"]
    ai = [s for s in samples if s["sample_type"] == "ai_search"]
    value = [s for s in samples if s["sample_type"] == "value"]

    assert len(human) == 1
    assert human[0]["outcome_for_side"] == 1
    assert human[0]["features"]["toward_enemy_flag"] == 1.0
    assert [s["label"] for s in ai] == [1, 0]
    assert value[0]["value_target_a"] == -1
