import os

from flask import Flask, jsonify, request, render_template
import copy
import random

import layout
from pieceClasses import Post, Camp, Headquarters
from pieceClasses import (Mar, Gen, MGen, BGen, Col, Maj, Capt, Lt, Spr,
                          Bomb, LMN, Flag)
from layout import (
    CAMP_POSITIONS_A, CAMP_POSITIONS_B,
    HQ_POSITIONS_A, HQ_POSITIONS_B,
)
from algorithms import (
    isLegal,
    contact,
    contactWithGameOverCheck,
    AIMove,
    get_last_search_debug,
    get_plan_debug_snapshot,
    set_search_profile,
    set_hidden_mode,
    reset_reveal_tracking,
    mark_piece_revealed,
)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

# --------------- game state (single global instance) ---------------


class GameState:
    def __init__(self):
        self.board = None
        self.winner = None
        self.turn = None  # "A" = AI, "B" = player
        self.maxDepth = 2
        self.mode = "hidden"  # "open" = both sides visible, "hidden" = AI pieces masked
        self.ai_mar_alive = True  # AI marshal (司令) alive — flag hidden while True
        self.last_ai_debug = None
        self.last_ai_move = None


game = GameState()
set_search_profile("fast")


# Board structure: which cell type at each (row, col)
# Camps are always empty at start; pieces only go on Post/Headquarters.
# Side A: rows 0-5, Side B: rows 6-11
# (CAMP_POSITIONS_A/B and HQ_POSITIONS_A/B are imported from layout.py)


def init_board(randomize=True):
    """Create the 12x5 board. If randomize, generate random legal layouts."""
    if randomize:
        return layout.build_initial_board()
    # Default fixed layout (original) — kept for non-randomized debug
    board = []
    for r in range(12):
        row = []
        for c in range(5):
            if (r, c) in HQ_POSITIONS_A or (r, c) in HQ_POSITIONS_B:
                row.append(Headquarters(r, c))
            elif (r, c) in CAMP_POSITIONS_A or (r, c) in CAMP_POSITIONS_B:
                row.append(Camp(r, c))
            else:
                row.append(Post(r, c))
        board.append(row)
    default = _default_pieces()
    for (r, c), piece in default.items():
        board[r][c].piece = piece
    return board


def _default_pieces():
    """The original hardcoded piece placement."""
    return {
        (0, 0): LMN("A"), (0, 1): Flag("A"), (0, 2): Capt("A"),
        (0, 3): LMN("A"), (0, 4): LMN("A"),
        (1, 0): Capt("A"), (1, 1): Lt("A"), (1, 2): BGen("A"),
        (1, 3): Spr("A"), (1, 4): Spr("A"),
        (2, 0): MGen("A"), (2, 2): Lt("A"), (2, 4): Maj("A"),
        (3, 0): Gen("A"), (3, 1): Bomb("A"), (3, 3): Lt("A"),
        (3, 4): Mar("A"),
        (4, 0): Maj("A"), (4, 2): Spr("A"), (4, 4): Bomb("A"),
        (5, 0): MGen("A"), (5, 1): Col("A"), (5, 2): BGen("A"),
        (5, 3): Capt("A"), (5, 4): Col("A"),
        (6, 0): MGen("B"), (6, 1): Spr("B"), (6, 2): Capt("B"),
        (6, 3): Mar("B"), (6, 4): Col("B"),
        (7, 0): Bomb("B"), (7, 2): Spr("B"), (7, 4): Bomb("B"),
        (8, 0): Capt("B"), (8, 1): Maj("B"), (8, 3): BGen("B"),
        (8, 4): Lt("B"),
        (9, 0): Maj("B"), (9, 2): BGen("B"), (9, 4): Gen("B"),
        (10, 0): LMN("B"), (10, 1): Lt("B"), (10, 2): Spr("B"),
        (10, 3): MGen("B"), (10, 4): LMN("B"),
        (11, 0): Capt("B"), (11, 1): Lt("B"), (11, 2): Col("B"),
        (11, 3): Flag("B"), (11, 4): LMN("B"),
    }


def cell_type(cell):
    if isinstance(cell, Headquarters):
        return "hq"
    elif isinstance(cell, Camp):
        return "camp"
    return "post"


def check_ai_marshal(board):
    """Check if AI (side A) marshal (order=9) is still on the board."""
    for r in range(12):
        for c in range(5):
            p = board[r][c].piece
            if p is not None and p.side == "A" and p.order == 9:
                return True
    return False


def serialize_board(board, mode="hidden", ai_mar_alive=True):
    result = []
    for r in range(12):
        row = []
        for c in range(5):
            cell = board[r][c]
            piece = None
            if cell.piece is not None:
                p = cell.piece
                if mode == "hidden" and p.side == "A":
                    # Reveal AI flag when AI marshal is dead
                    if not ai_mar_alive and p.order == 0:
                        piece = {"name": p.name, "side": p.side, "order": p.order}
                    else:
                        piece = {"name": None, "side": p.side, "order": None}
                else:
                    piece = {"name": p.name, "side": p.side, "order": p.order}
            row.append({"type": cell_type(cell), "piece": piece})
        result.append(row)
    return result


def board_response():
    return {
        "board": serialize_board(game.board, game.mode, game.ai_mar_alive),
        "turn": game.turn,
        "winner": game.winner,
        "mode": game.mode,
        "ai_debug_current": get_plan_debug_snapshot(game.board, "A") if game.board is not None else None,
        "ai_debug_last_turn": game.last_ai_debug,
    }


def build_battle_event(attacker_piece, defender_piece):
    """Build a battle event payload from two pieces before contact()."""
    if attacker_piece is None or defender_piece is None:
        return None

    if attacker_piece.order is None or defender_piece.order is None or attacker_piece.order == defender_piece.order:
        kind = "mutual"
    elif attacker_piece.order == 1 and defender_piece.order == 10:
        kind = "sapper_mine"
    elif attacker_piece.order > defender_piece.order:
        kind = "attacker_win"
    else:
        kind = "defender_win"

    return {
        "kind": kind,
        "attacker_side": attacker_piece.side,
        "attacker_name": attacker_piece.name,
        "defender_side": defender_piece.side,
        "defender_name": defender_piece.name,
    }


def serialize_move_piece(piece, mode, ai_mar_alive):
    """Serialize a moving piece with the same visibility rule as serialize_board()."""
    if piece is None:
        return None
    if mode == "hidden" and piece.side == "A":
        if not ai_mar_alive and piece.order == 0:
            return {"name": piece.name, "side": piece.side, "order": piece.order}
        return {"name": None, "side": piece.side, "order": None}
    return {"name": piece.name, "side": piece.side, "order": piece.order}


def build_move_record(fr, fc, tr, tc, piece, mode, ai_mar_alive):
    if piece is None:
        return None
    return {
        "from": [fr, fc],
        "to": [tr, tc],
        "piece": serialize_move_piece(piece, mode, ai_mar_alive),
    }


# --------------- routes ---------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/new-game", methods=["POST"])
def new_game():
    body = request.get_json(silent=True) or {}
    difficulty = body.get("difficulty", "easy")
    mode = body.get("mode", "hidden")
    randomize = body.get("randomize", True)
    if mode not in ("open", "hidden"):
        mode = "hidden"
    game.board = init_board(randomize=randomize)
    game.winner = None
    game.turn = "B"  # player goes first
    # Hidden mode uses its own weaker profile; open mode keeps the original.
    if mode == "hidden":
        if difficulty == "hard":
            game.maxDepth = 8
            set_search_profile("hidden_hard")
        else:
            game.maxDepth = 4
            set_search_profile("hidden_easy")
    else:
        if difficulty == "hard":
            game.maxDepth = 12
            set_search_profile("strong")
        else:
            game.maxDepth = 6
            set_search_profile("fast")
    game.mode = mode
    game.ai_mar_alive = True
    game.last_ai_debug = None
    game.last_ai_move = None
    # Masking: AI treats B pieces as unknown until combat reveals them.
    set_hidden_mode(mode == "hidden")
    reset_reveal_tracking()
    return jsonify(board_response())


@app.route("/api/ai-debug")
def ai_debug():
    return jsonify({
        "current": get_plan_debug_snapshot(game.board, "A") if game.board is not None else None,
        "last_turn": game.last_ai_debug,
        "turn": game.turn,
        "winner": game.winner,
    })


@app.route("/api/legal-moves")
def legal_moves():
    row = request.args.get("row", type=int)
    col = request.args.get("col", type=int)
    if game.board is None:
        return jsonify({"moves": []})
    cell = game.board[row][col]
    if cell.piece is None or cell.piece.side != "B":
        return jsonify({"moves": []})
    moves = isLegal(game.board, (row, col))
    return jsonify({"moves": [list(m) for m in moves]})


@app.route("/api/move", methods=["POST"])
def make_move():
    if game.board is None or game.winner is not None:
        return jsonify(board_response())

    body = request.get_json()
    fr, fc = body["from_row"], body["from_col"]
    tr, tc = body["to_row"], body["to_col"]

    # validate
    legal = isLegal(game.board, (fr, fc))
    if (tr, tc) not in legal:
        return jsonify({**board_response(), "error": "illegal move"}), 400

    battle_events = []
    player_piece_before = game.board[fr][fc].piece
    player_move_record = build_move_record(fr, fc, tr, tc, player_piece_before, game.mode, game.ai_mar_alive)
    ai_move_record = None

    # execute player move
    if game.board[tr][tc].piece is None:
        game.board[tr][tc].piece = game.board[fr][fc].piece
        game.board[fr][fc].piece = None
    else:
        event = build_battle_event(game.board[fr][fc].piece, game.board[tr][tc].piece)
        if event is not None:
            battle_events.append(event)
        # Combat exposes both pieces publicly — let AI eval use their real rank.
        mark_piece_revealed(game.board[fr][fc].piece)
        mark_piece_revealed(game.board[tr][tc].piece)
        contactWithGameOverCheck(fr, fc, tr, tc, game)

    # Check if AI marshal was killed by this move
    if game.ai_mar_alive and not check_ai_marshal(game.board):
        game.ai_mar_alive = False

    board_after_player = serialize_board(game.board, game.mode, game.ai_mar_alive)

    if game.winner is not None:
        return jsonify({
            "player_move": {"from": [fr, fc], "to": [tr, tc]},
            "board_after_player": board_after_player,
            "ai_move": None,
            "battle_events": battle_events,
            "move_records": {"player": player_move_record, "ai": ai_move_record},
            **board_response(),
        })

    # AI turn
    game.turn = "A"
    board_copy = copy.deepcopy(game.board)
    result = AIMove(board_copy, game.maxDepth, prev_move=game.last_ai_move)
    ai_move, _ = result
    game.last_ai_debug = get_last_search_debug()
    if ai_move is not None:
        a, b, i, j = ai_move
        game.last_ai_move = ai_move
        ai_piece_before = game.board[a][b].piece
        ai_move_record = build_move_record(a, b, i, j, ai_piece_before, game.mode, game.ai_mar_alive)
        if game.board[i][j].piece is None:
            game.board[i][j].piece = game.board[a][b].piece
            game.board[a][b].piece = None
        else:
            event = build_battle_event(game.board[a][b].piece, game.board[i][j].piece)
            if event is not None:
                battle_events.append(event)
            mark_piece_revealed(game.board[a][b].piece)
            mark_piece_revealed(game.board[i][j].piece)
            contactWithGameOverCheck(a, b, i, j, game)
    else:
        game.last_ai_move = None

    game.turn = "B"
    resp = {
        "player_move": {"from": [fr, fc], "to": [tr, tc]},
        "board_after_player": board_after_player,
        "ai_move": {"from": [ai_move[0], ai_move[1]],
                     "to": [ai_move[2], ai_move[3]]} if ai_move else None,
        "battle_events": battle_events,
        "move_records": {"player": player_move_record, "ai": ai_move_record},
        **board_response(),
    }
    return jsonify(resp)


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("APP_PORT", "5000"))
    except ValueError:
        port = 5000
    debug = os.getenv("APP_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug, threaded=False)
