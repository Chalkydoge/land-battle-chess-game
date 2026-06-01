"""Shared schema helpers for game records."""

import hashlib
import json

from pieceClasses import Camp, Headquarters


SCHEMA = "land-battle-chess.open-jsonl.v1"
DEFAULT_RECORD_ROOT = "records"

CLASS_TO_KIND = {
    "Mar": "MAR",
    "Gen": "GEN",
    "MGen": "MGEN",
    "BGen": "BGEN",
    "Col": "COL",
    "Maj": "MAJ",
    "Capt": "CAPT",
    "Lt": "LT",
    "Spr": "SPR",
    "Bomb": "BOMB",
    "LMN": "LMN",
    "Flag": "FLAG",
}


def piece_kind(piece):
    if piece is None:
        return None
    return CLASS_TO_KIND.get(type(piece).__name__, type(piece).__name__.upper())


def cell_type(cell):
    if isinstance(cell, Headquarters):
        return "hq"
    if isinstance(cell, Camp):
        return "camp"
    return "post"


def position_key(board_state, side_to_move=None):
    payload = {"board": board_state, "side_to_move": side_to_move}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
