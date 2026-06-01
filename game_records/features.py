"""Feature encoding for recorded board positions and moves."""


PIECE_KINDS = [
    "MAR", "GEN", "MGEN", "BGEN", "COL", "MAJ",
    "CAPT", "LT", "SPR", "BOMB", "LMN", "FLAG",
]

PIECE_VALUE_FALLBACK = {
    "MAR": 100,
    "GEN": 80,
    "MGEN": 55,
    "BGEN": 35,
    "COL": 20,
    "MAJ": 12,
    "CAPT": 7,
    "LT": 3,
    "SPR": 12,
    "BOMB": 20,
    "LMN": 15,
    "FLAG": 10000,
}


def encode_board_move(board, move, piece_catalog, side):
    """Encode a board-before + move pair into flat numeric features.

    Features are perspective-normalized: the moving side is always treated as
    "friendly" and is oriented as if it advances toward increasing row numbers.
    Human B-side samples therefore become usable for AI A-side move ordering.
    """
    move = _move_tuple(move)
    fr, fc, tr, tc = _orient_move(move, side)
    catalog = piece_catalog or {}
    board_view = _oriented_board(board, side)

    moving_id = _cell(board, move[0], move[1])
    target_id = _cell(board, move[2], move[3])
    moving = catalog.get(moving_id, _payload_from_id(moving_id))
    target = catalog.get(target_id, _payload_from_id(target_id))

    own_flag = _find_flag(board_view, catalog, side, friendly=True)
    enemy_flag = _find_flag(board_view, catalog, side, friendly=False)

    features = {
        "bias": 1.0,
        "from_row": fr / 11.0,
        "from_col": fc / 4.0,
        "to_row": tr / 11.0,
        "to_col": tc / 4.0,
        "delta_forward": tr - fr,
        "delta_side": abs(tc - fc),
        "move_distance": abs(tr - fr) + abs(tc - fc),
        "is_capture": 1.0 if target_id is not None else 0.0,
        "is_forward": 1.0 if tr > fr else 0.0,
        "is_retreat": 1.0 if tr < fr else 0.0,
        "moving_order": _order_value(moving) / 10.0,
        "moving_value": _piece_value(moving) / 100.0,
        "target_order": _order_value(target) / 10.0,
        "target_value": _piece_value(target) / 100.0,
        "capture_value_delta": (_piece_value(target) - _piece_value(moving)) / 100.0,
        "target_is_flag": 1.0 if _kind(target) == "FLAG" else 0.0,
        "target_is_mine": 1.0 if _kind(target) == "LMN" else 0.0,
        "moving_is_sapper": 1.0 if _kind(moving) == "SPR" else 0.0,
        "moving_is_bomb": 1.0 if _kind(moving) == "BOMB" else 0.0,
    }

    for kind in PIECE_KINDS:
        features[f"moving_{kind}"] = 1.0 if _kind(moving) == kind else 0.0
        features[f"target_{kind}"] = 1.0 if _kind(target) == kind else 0.0

    features.update(_material_features(board, catalog, side))
    features.update(_flag_distance_features(fr, fc, tr, tc, own_flag, enemy_flag))
    return features


def feature_names():
    probe_board = [[None for _ in range(5)] for _ in range(12)]
    probe_board[0][0] = "A-FLAG-1"
    probe_board[11][4] = "B-FLAG-1"
    probe_catalog = {
        "A-FLAG-1": {"id": "A-FLAG-1", "side": "A", "kind": "FLAG", "order": 0, "value": 10000},
        "B-FLAG-1": {"id": "B-FLAG-1", "side": "B", "kind": "FLAG", "order": 0, "value": 10000},
    }
    return sorted(encode_board_move(probe_board, ([0, 0], [1, 0]), probe_catalog, "A"))


def _material_features(board, catalog, side):
    friendly_count = enemy_count = 0
    friendly_material = enemy_material = 0.0
    for row in board:
        for piece_id in row:
            if piece_id is None:
                continue
            payload = catalog.get(piece_id, _payload_from_id(piece_id))
            if _piece_side(payload, piece_id) == side:
                friendly_count += 1
                friendly_material += _piece_value(payload)
            else:
                enemy_count += 1
                enemy_material += _piece_value(payload)
    return {
        "friendly_count": friendly_count / 25.0,
        "enemy_count": enemy_count / 25.0,
        "material_balance": (friendly_material - enemy_material) / 1000.0,
    }


def _flag_distance_features(fr, fc, tr, tc, own_flag, enemy_flag):
    features = {
        "dist_own_flag_before": 0.0,
        "dist_own_flag_after": 0.0,
        "dist_enemy_flag_before": 0.0,
        "dist_enemy_flag_after": 0.0,
        "toward_own_flag": 0.0,
        "toward_enemy_flag": 0.0,
        "adjacent_enemy_flag_after": 0.0,
    }
    if own_flag is not None:
        before = _manhattan((fr, fc), own_flag)
        after = _manhattan((tr, tc), own_flag)
        features["dist_own_flag_before"] = before / 15.0
        features["dist_own_flag_after"] = after / 15.0
        features["toward_own_flag"] = 1.0 if after < before else 0.0
    if enemy_flag is not None:
        before = _manhattan((fr, fc), enemy_flag)
        after = _manhattan((tr, tc), enemy_flag)
        features["dist_enemy_flag_before"] = before / 15.0
        features["dist_enemy_flag_after"] = after / 15.0
        features["toward_enemy_flag"] = 1.0 if after < before else 0.0
        features["adjacent_enemy_flag_after"] = 1.0 if after == 1 else 0.0
    return features


def _find_flag(board_view, catalog, side, friendly):
    for r, row in enumerate(board_view):
        for c, piece_id in enumerate(row):
            if piece_id is None:
                continue
            payload = catalog.get(piece_id, _payload_from_id(piece_id))
            is_friendly = _piece_side(payload, piece_id) == side
            if is_friendly == friendly and _kind(payload) == "FLAG":
                return (r, c)
    return None


def _oriented_board(board, side):
    if side == "A":
        return board
    return [[board[11 - r][4 - c] for c in range(5)] for r in range(12)]


def _orient_move(move, side):
    fr, fc, tr, tc = move
    if side == "A":
        return (fr, fc, tr, tc)
    return (11 - fr, 4 - fc, 11 - tr, 4 - tc)


def _move_tuple(move):
    if isinstance(move, dict):
        fr, fc = move["from"]
        tr, tc = move["to"]
        return (fr, fc, tr, tc)
    if len(move) == 2:
        fr, fc = move[0]
        tr, tc = move[1]
        return (fr, fc, tr, tc)
    return tuple(move)


def _cell(board, row, col):
    return board[row][col]


def _payload_from_id(piece_id):
    if piece_id is None:
        return None
    side, kind, _ = piece_id.split("-", 2)
    return {
        "id": piece_id,
        "side": side,
        "kind": kind,
        "order": None,
        "value": PIECE_VALUE_FALLBACK.get(kind, 0),
    }


def _piece_side(payload, piece_id=None):
    if payload is not None:
        return payload.get("side")
    if piece_id is None:
        return None
    return piece_id.split("-", 1)[0]


def _kind(payload):
    if payload is None:
        return None
    return payload.get("kind")


def _piece_value(payload):
    if payload is None:
        return 0
    value = payload.get("value")
    if value is not None:
        return value
    return PIECE_VALUE_FALLBACK.get(_kind(payload), 0)


def _order_value(payload):
    if payload is None:
        return 0
    order = payload.get("order")
    if order is None:
        return 11 if _kind(payload) == "BOMB" else 0
    return order


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
