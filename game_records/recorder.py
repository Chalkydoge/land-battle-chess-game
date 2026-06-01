"""JSONL game recorder for open-information games.

The recorder stores one event per line so a live game can be inspected while
it is still in progress. Each event is self-contained enough for later replay
or conversion into training samples.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from game_records.schema import (
    DEFAULT_RECORD_ROOT,
    SCHEMA,
    cell_type,
    piece_kind,
    position_key,
)


def _utc_timestamp():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class JsonlGameRecorder:
    def __init__(self, record_root=None):
        root = record_root or os.getenv("GAME_RECORD_DIR", DEFAULT_RECORD_ROOT)
        self.record_root = Path(root)
        self.game_id = None
        self.path = None
        self.ply = 0
        self.finished = False
        self.piece_catalog = {}
        self._piece_counters = {}

    def start_game(self, board, config):
        now = datetime.now()
        self.game_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        self.path = self.record_root / "open" / f"{now.date().isoformat()}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ply = 0
        self.finished = False
        self.piece_catalog = {}
        self._piece_counters = {}
        self._assign_piece_ids(board)

        board_state = self.serialize_board_state(board)
        self._write({
            "event": "game_start",
            "config": dict(config),
            "board_shape": [12, 5],
            "cell_types": self.serialize_cell_types(board),
            "piece_catalog": self.piece_catalog,
            "initial_board": board_state,
            "initial_position_key": position_key(board_state, "B"),
        })
        return self

    def status(self):
        if self.game_id is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "schema": SCHEMA,
            "game_id": self.game_id,
            "path": str(self.path),
            "plies": self.ply,
            "finished": self.finished,
        }

    def serialize_cell_types(self, board):
        return [[cell_type(board[r][c]) for c in range(5)] for r in range(12)]

    def serialize_board_state(self, board):
        state = []
        for r in range(12):
            row = []
            for c in range(5):
                piece = board[r][c].piece
                row.append(self._piece_id(piece) if piece is not None else None)
            state.append(row)
        return state

    def piece_payload(self, piece):
        if piece is None:
            return None
        piece_id = self._piece_id(piece)
        payload = {
            "id": piece_id,
            "side": piece.side,
            "kind": piece_kind(piece),
            "order": piece.order,
            "value": getattr(piece, "value", None),
        }
        self.piece_catalog[piece_id] = payload
        return payload

    def combat_payload(self, attacker, defender):
        if attacker is None or defender is None:
            return None

        attacker_payload = self.piece_payload(attacker)
        defender_payload = self.piece_payload(defender)
        if attacker.order is None or defender.order is None or attacker.order == defender.order:
            kind = "mutual"
            removed = [attacker_payload["id"], defender_payload["id"]]
            survivor = None
        elif attacker.order == 1 and defender.order == 10:
            kind = "sapper_mine"
            removed = [defender_payload["id"]]
            survivor = attacker_payload["id"]
        elif attacker.order > defender.order:
            kind = "attacker_win"
            removed = [defender_payload["id"]]
            survivor = attacker_payload["id"]
        else:
            kind = "defender_win"
            removed = [attacker_payload["id"]]
            survivor = defender_payload["id"]

        return {
            "kind": kind,
            "attacker": attacker_payload["id"],
            "defender": defender_payload["id"],
            "removed": removed,
            "survivor": survivor,
        }

    def record_ply(self, side, actor, move, piece, target, board_before,
                   board_after, combat=None, search=None, terminal=None,
                   next_side=None):
        if self.finished or self.game_id is None:
            return
        self.ply += 1
        fr, fc, tr, tc = move
        payload = {
            "event": "ply",
            "ply": self.ply,
            "side": side,
            "actor": actor,
            "move": {"from": [fr, fc], "to": [tr, tc]},
            "piece": self.piece_payload(piece),
            "target": self.piece_payload(target),
            "combat": combat,
            "board_before": board_before,
            "board_after": board_after,
            "position_key_before": position_key(board_before, side),
            "position_key_after": position_key(board_after, next_side),
        }
        if search is not None:
            payload["search"] = search
        if terminal is not None:
            payload["terminal"] = terminal
        self._write(payload)

    def finish(self, winner, reason, final_board=None):
        if self.finished or self.game_id is None:
            return
        self.finished = True
        payload = {
            "event": "game_end",
            "result": {
                "winner": winner,
                "reason": reason,
                "plies": self.ply,
            },
        }
        if final_board is not None:
            final_state = self.serialize_board_state(final_board)
            payload["final_board"] = final_state
            payload["final_position_key"] = position_key(final_state, None)
        self._write(payload)

    def _assign_piece_ids(self, board):
        for r in range(12):
            for c in range(5):
                piece = board[r][c].piece
                if piece is not None:
                    self._assign_piece_id(piece)

    def _piece_id(self, piece):
        piece_id = getattr(piece, "_record_id", None)
        if piece_id is None:
            piece_id = self._assign_piece_id(piece)
        return piece_id

    def _assign_piece_id(self, piece):
        kind = piece_kind(piece)
        key = (piece.side, kind)
        self._piece_counters[key] = self._piece_counters.get(key, 0) + 1
        piece_id = f"{piece.side}-{kind}-{self._piece_counters[key]}"
        piece._record_id = piece_id
        self.piece_catalog[piece_id] = {
            "id": piece_id,
            "side": piece.side,
            "kind": kind,
            "order": piece.order,
            "value": getattr(piece, "value", None),
        }
        return piece_id

    def _write(self, payload):
        payload = {
            "schema": SCHEMA,
            "ts": _utc_timestamp(),
            "game_id": self.game_id,
            **payload,
        }
        line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
