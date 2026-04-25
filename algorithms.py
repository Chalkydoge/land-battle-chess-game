######## This file contains the core game rules and a stronger search-based AI

import time
import random as _random
from collections import defaultdict

from pieceClasses import *


# ===================== Zobrist Hashing =====================

def _zobrist_piece_code(piece):
    """Encode a piece into 0..23 for Zobrist table lookup.
    order mapping: 0-10 stay as-is, None(bomb)=11.  Side A → +0, B → +12."""
    if piece is None:
        return -1
    order = 11 if piece.order is None else piece.order
    return order + (0 if piece.side == "A" else 12)

# Pre-generate Zobrist random numbers (deterministic seed for reproducibility)
_rng = _random.Random(0xDEADBEEF)
ZOBRIST_TABLE = [[[_rng.getrandbits(64) for _ in range(24)]
                  for _ in range(5)] for _ in range(12)]
ZOBRIST_SIDE = _rng.getrandbits(64)   # XOR when side == "B"
ZOBRIST_HASH = 0                      # running hash, updated by applyMove/undoMove
POSITION_HISTORY = set()               # Zobrist hashes on current search path (repetition detection)


def compute_zobrist(board, side):
    """Full recomputation of Zobrist hash from scratch."""
    h = 0
    for r in range(12):
        for c in range(5):
            code = _zobrist_piece_code(board[r][c].piece)
            if code >= 0:
                h ^= ZOBRIST_TABLE[r][c][code]
    if side == "B":
        h ^= ZOBRIST_SIDE
    return h

# ===================== End Zobrist =====================


#### finding all posts that are legal moves given a selected piece

railroadPosts = set()
# this set contains all posts that are on the railroad
for i in range(1, 11):
    railroadPosts.add((i, 0))
    railroadPosts.add((i, 4))
for i in range(0, 5):
    railroadPosts.add((1, i))
    railroadPosts.add((5, i))
    railroadPosts.add((6, i))
    railroadPosts.add((10, i))


SEARCH_PROFILE = "fast"
LAST_SEARCH_DEBUG = None
MATE_SCORE = 100000
INF = 10 ** 9
TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2
TRANSPOSITION_TABLE = {}
KILLER_MOVES = defaultdict(list)
HISTORY_TABLE = defaultdict(int)
SEARCH_DEADLINE = None
NODE_COUNT = 0
LAST_COMPLETED_DEPTH = 0
KEY_CELLS = {
    (4, 1), (4, 2), (4, 3),
    (5, 0), (5, 1), (5, 2), (5, 3), (5, 4),
    (6, 0), (6, 1), (6, 2), (6, 3), (6, 4),
    (7, 1), (7, 2), (7, 3),
}
# Futility Pruning margins: at depth_left=N, a quiet move that can't lift
# static_eval into [alpha, beta] is skipped.
FUTILITY_MARGIN = {1: 120, 2: 250}
PROFILE_SETTINGS = {
    "fast": {
        "time_limit": 2.0,
        "qdepth": 3,
        "advance_weight": 0.2,
        "control_weight": 1.5,
        "threat_weight": 1.0,
        "max_depth_cap": None,
        "root_random_pool": 1,
        "root_random_prob": 0.0,
    },
    "strong": {
        "time_limit": 5.0,
        "qdepth": 5,
        "advance_weight": 0.25,
        "control_weight": 2.0,
        "threat_weight": 1.2,
        "max_depth_cap": None,
        "root_random_pool": 1,
        "root_random_prob": 0.0,
    },
    # Hidden-mode profiles: weaker than fast/strong.
    # See set_hidden_mode() / _is_hidden_to_ai() for the companion masking.
    "hidden_easy": {
        "time_limit": 1.0,
        "qdepth": 2,
        "advance_weight": 0.15,
        "control_weight": 1.0,
        "threat_weight": 0.7,
        "max_depth_cap": 4,
        "root_random_pool": 4,
        "root_random_prob": 0.55,
    },
    "hidden_hard": {
        "time_limit": 3.0,
        "qdepth": 4,
        "advance_weight": 0.22,
        "control_weight": 1.6,
        "threat_weight": 1.0,
        "max_depth_cap": 8,
        "root_random_pool": 2,
        "root_random_prob": 0.2,
    },
}


# --- Hidden-information masking (active only in hidden mode) ---
# When _HIDE_ENEMY_INFO is True, the evaluation layer treats every B-side
# piece whose `_revealed` attribute is not truthy as "unknown": its real
# order/value never feeds into _piece_score / _combat_outcome / threat
# scoring. applyMove/contact() still resolve real outcomes (needed for legal
# move generation and correct post-move board state), but the leaf eval that
# guides search cannot exploit enemy ranks the AI has not publicly observed.
#
# The revealed flag lives on the Piece instance so it survives copy.deepcopy
# of the board for search (id()-based tracking would not).
_HIDE_ENEMY_INFO = False
# Stub value for unrevealed B pieces — set slightly below the mean of the
# 20 non-special pieces (司令 100 … 排长 3 mean ≈ 35) so the AI is mildly
# pessimistic about charging at unknowns.
_HIDDEN_VALUE_STUB = 28


def set_hidden_mode(enabled):
    """Enable/disable identity masking of B-side pieces for the AI."""
    global _HIDE_ENEMY_INFO
    _HIDE_ENEMY_INFO = bool(enabled)


def reset_reveal_tracking():
    """No-op placeholder: reveal state lives on Piece instances, and each new
    game creates fresh pieces. Kept as a public hook in case callers want to
    clear state explicitly."""
    return


def mark_piece_revealed(piece):
    """Flag a piece as publicly known (e.g., after it participated in combat).
    Safe to call on the live game board — `_revealed` deep-copies into the
    search's board copy so the AI keeps seeing it as revealed during search."""
    if piece is not None:
        piece._revealed = True


def _is_hidden_to_ai(piece):
    """True iff this piece's true identity should be masked from AI eval."""
    if not _HIDE_ENEMY_INFO or piece is None:
        return False
    if piece.side != "B":
        return False
    return not getattr(piece, "_revealed", False)


def _move_to_debug(move):
    if move is None:
        return None
    return [[move[0], move[1]], [move[2], move[3]]]


# finding all legal moves for a selected piece
def isLegal(board, selected):
    (a, b) = selected
    valid = set()
    # landmines and pieces in headquarters cannot move
    if board[a][b].piece.order == 10 or isinstance(board[a][b], Headquarters):
        return valid

    # searching adjacent moves with one step
    for (c, d) in [(a - 1, b), (a + 1, b), (a, b - 1), (a, b + 1)]:
        if 0 <= c <= 11 and 0 <= d <= 4 and (
            board[c][d].piece == None or
            (board[c][d].piece.side != board[a][b].piece.side and
             not isinstance(board[c][d], Camp))
        ):
            valid.add((c, d))
    for (c, d) in [(a - 1, b - 1), (a - 1, b + 1), (a + 1, b - 1), (a + 1, b + 1)]:
        if 0 <= c <= 11 and 0 <= d <= 4 and isinstance(board[c][d], Camp) and board[c][d].piece == None:
            valid.add((c, d))
    # Camps reach out to every diagonal direction as well
    if isinstance(board[a][b], Camp):
        for (c, d) in [(a - 1, b - 1), (a - 1, b + 1), (a + 1, b - 1), (a + 1, b + 1)]:
            if 0 <= c <= 11 and 0 <= d <= 4:
                if board[c][d].piece == None or (
                    board[c][d].piece.side != board[a][b].piece.side and
                    not isinstance(board[c][d], Camp)
                ):
                    valid.add((c, d))
    # the front line only has three access roads; the other two are invalid
    if (a, b) in [(5, 1), (6, 1), (5, 3), (6, 3)]:
        valid.discard((5, 1))
        valid.discard((6, 1))
        valid.discard((5, 3))
        valid.discard((6, 3))

    # searching moves enabled by railroads
    if (a, b) in railroadPosts:
        # finding railroad path for Sappers (Sappers can make turns on railroads)
        if board[a][b].piece.order == 1:
            lst = []
            if (a, b) in [(5, 1), (5, 3), (6, 1), (6, 3)]:
                lst = findSprPaths(a, b - 1, a, b, board, lst) + findSprPaths(a, b + 1, a, b, board, lst)
            else:
                lst = (
                    findSprPaths(a - 1, b, a, b, board, lst) +
                    findSprPaths(a + 1, b, a, b, board, lst) +
                    findSprPaths(a, b - 1, a, b, board, lst) +
                    findSprPaths(a, b + 1, a, b, board, lst)
                )
            for (i, j) in lst:
                valid.add((i, j))
        # finding railroad path for regular pieces
        else:
            # finding vertical railroad paths
            if (b == 0 or b == 4) and 1 <= a <= 10:
                (c, d) = (a, b)
                c += 1
                while 1 <= c <= 10 and board[c][d].piece == None:
                    c += 1
                    if c <= 10 and (
                        board[c][d].piece == None or
                        board[c][d].piece.side != board[a][b].piece.side
                    ):
                        valid.add((c, d))
                (c, d) = (a, b)
                c -= 1
                while 1 <= c <= 10 and board[c][d].piece == None:
                    c -= 1
                    if c >= 1 and (
                        board[c][d].piece == None or
                        board[c][d].piece.side != board[a][b].piece.side
                    ):
                        valid.add((c, d))
            # finding horizontal railroad paths
            if a == 5 or a == 6 or a == 1 or a == 10:
                (c, d) = (a, b)
                d += 1
                while 0 <= d <= 4 and board[c][d].piece == None:
                    d += 1
                    if d <= 4 and (
                        board[c][d].piece == None or
                        board[c][d].piece.side != board[a][b].piece.side
                    ):
                        valid.add((c, d))
                (c, d) = (a, b)
                d -= 1
                while 0 <= d <= 4 and board[c][d].piece == None:
                    d -= 1
                    if d >= 0 and (
                        board[c][d].piece == None or
                        board[c][d].piece.side != board[a][b].piece.side
                    ):
                        valid.add((c, d))

    valid.discard((a, b))
    return valid


# recursively finding railroad paths for Sappers
def findSprPaths(a, b, i, j, board, lst):
    if (a, b) not in railroadPosts:
        return []
    if (a, b) in lst:
        return []
    if board[a][b].piece != None:
        if board[a][b].piece.side != board[i][j].piece.side:
            return [(a, b)]
        return []

    if (a, b) in [(5, 1), (5, 3), (6, 1), (6, 3)]:
        lst.append((a, b))
        return [(a, b)] + findSprPaths(a, b - 1, i, j, board, lst) + findSprPaths(a, b + 1, i, j, board, lst)

    lst.append((a, b))
    return (
        [(a, b)] +
        findSprPaths(a - 1, b, i, j, board, lst) +
        findSprPaths(a + 1, b, i, j, board, lst) +
        findSprPaths(a, b - 1, i, j, board, lst) +
        findSprPaths(a, b + 1, i, j, board, lst)
    )


#### making moves

# determine if game is over
def isOver(board):
    Aok, Bok = False, False
    for x in range(12):
        for y in range(5):
            if board[x][y].piece != None:
                if board[x][y].piece.side == "A" and not Aok:
                    if isLegal(board, (x, y)) != set():
                        Aok = True
                elif board[x][y].piece.side == "B" and not Bok:
                    if isLegal(board, (x, y)) != set():
                        Bok = True
    if not Aok:
        return "B"
    if not Bok:
        return "A"
    return None


# two pieces make contact (and updates the game-over check)
def contactWithGameOverCheck(a, b, i, j, data):
    if data.board[a][b].piece.order == 0:
        data.winner = data.board[i][j].piece.side
    elif data.board[i][j].piece.order == 0:
        data.winner = data.board[a][b].piece.side
    contact(a, b, i, j, data.board)
    winner = isOver(data.board)
    if winner != None:
        data.winner = winner


# two pieces make contact
def contact(a, b, i, j, board):
    # Bombs co-destroy any enemy piece
    if (
        board[a][b].piece.order == None or
        board[i][j].piece.order == None or
        board[a][b].piece.order == board[i][j].piece.order
    ):
        board[a][b].piece = None
        board[i][j].piece = None
    # Sappers can capture landmines
    elif board[a][b].piece.order == 1 and board[i][j].piece.order == 10:
        board[i][j].piece = board[a][b].piece
        board[a][b].piece = None
    # other pieces react according to their order
    elif board[a][b].piece.order > board[i][j].piece.order:
        board[i][j].piece = board[a][b].piece
        board[a][b].piece = None
    else:
        board[a][b].piece = None



def applyMove(board, fr, fc, tr, tc):
    global ZOBRIST_HASH
    fromPost = board[fr][fc].piece
    toPost = board[tr][tc].piece
    # XOR out the moving piece from its origin
    code_from = _zobrist_piece_code(fromPost)
    if code_from >= 0:
        ZOBRIST_HASH ^= ZOBRIST_TABLE[fr][fc][code_from]
    if toPost is None:
        board[tr][tc].piece = fromPost
        board[fr][fc].piece = None
        # XOR in the piece at its destination
        ZOBRIST_HASH ^= ZOBRIST_TABLE[tr][tc][code_from]
    else:
        # XOR out the captured piece
        code_to = _zobrist_piece_code(toPost)
        if code_to >= 0:
            ZOBRIST_HASH ^= ZOBRIST_TABLE[tr][tc][code_to]
        contact(fr, fc, tr, tc, board)
        # XOR in whatever remains at from and to cells
        new_from = _zobrist_piece_code(board[fr][fc].piece)
        new_to = _zobrist_piece_code(board[tr][tc].piece)
        if new_from >= 0:
            ZOBRIST_HASH ^= ZOBRIST_TABLE[fr][fc][new_from]
        if new_to >= 0:
            ZOBRIST_HASH ^= ZOBRIST_TABLE[tr][tc][new_to]
    # Flip side-to-move
    ZOBRIST_HASH ^= ZOBRIST_SIDE
    return (fromPost, toPost)



def undoMove(board, fr, fc, tr, tc, fromPost, toPost):
    global ZOBRIST_HASH
    # XOR out whatever is currently at from/to (post-move state)
    cur_from = _zobrist_piece_code(board[fr][fc].piece)
    cur_to = _zobrist_piece_code(board[tr][tc].piece)
    if cur_from >= 0:
        ZOBRIST_HASH ^= ZOBRIST_TABLE[fr][fc][cur_from]
    if cur_to >= 0:
        ZOBRIST_HASH ^= ZOBRIST_TABLE[tr][tc][cur_to]
    # Restore original pieces
    board[fr][fc].piece = fromPost
    board[tr][tc].piece = toPost
    # XOR in the restored pieces
    orig_from = _zobrist_piece_code(fromPost)
    orig_to = _zobrist_piece_code(toPost)
    if orig_from >= 0:
        ZOBRIST_HASH ^= ZOBRIST_TABLE[fr][fc][orig_from]
    if orig_to >= 0:
        ZOBRIST_HASH ^= ZOBRIST_TABLE[tr][tc][orig_to]
    # Flip side-to-move back
    ZOBRIST_HASH ^= ZOBRIST_SIDE



def searchAfterMove(board, fr, fc, tr, tc, nextSearchFn, maxDepth, depth, alpha, beta):
    fromPost, toPost = applyMove(board, fr, fc, tr, tc)
    try:
        _, moveScore = nextSearchFn(board, maxDepth, depth + 1, alpha, beta, (fr, fc, tr, tc))
    finally:
        undoMove(board, fr, fc, tr, tc, fromPost, toPost)
    return moveScore


#### simple AI evaluation and alpha-beta search


def set_search_profile(profile):
    global SEARCH_PROFILE
    if profile in PROFILE_SETTINGS:
        SEARCH_PROFILE = profile



def getLargestPiece(board):
    largestA, largestB = 0, 0
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece == None or piece.order == 0:
                continue
            value = getattr(piece, "value", 0)
            if piece.side == "A":
                largestA = max(largestA, value)
            else:
                largestB = max(largestB, value)
    return (largestA, largestB)


def _profile_value(key, default=None):
    return PROFILE_SETTINGS.get(SEARCH_PROFILE, PROFILE_SETTINGS["fast"]).get(key, default)


def _piece_score(piece, largest_opponent_value):
    if piece == None:
        return 0
    if _is_hidden_to_ai(piece):
        return _HIDDEN_VALUE_STUB
    if piece.order == 0:
        # In hidden mode, zero out A's flag to cancel the asymmetry caused
        # by B's hidden flag mapping to the stub value — otherwise the AI
        # would see a phantom +10000 baseline advantage.
        if _HIDE_ENEMY_INFO:
            return _HIDDEN_VALUE_STUB
        return 10000
    if piece.order == None:
        return max(20, largest_opponent_value // 2)
    return getattr(piece, "value", 0)


def _advance_score(piece, row):
    if piece == None or piece.order in (0, 10):
        return 0
    if piece.side == "A":
        return row
    return 11 - row


def _combat_outcome(attacker, defender):
    if defender == None:
        return 0
    # Unknown identity → treat as uncertain (mutual) so threat/opportunity
    # scoring cannot exploit concealed ranks.
    if _is_hidden_to_ai(attacker) or _is_hidden_to_ai(defender):
        return 0
    if defender.order == 0:
        return 1
    if attacker.order == None or defender.order == None or attacker.order == defender.order:
        return 0
    if attacker.order == 1 and defender.order == 10:
        return 1
    if attacker.order > defender.order:
        return 1
    return -1


def _capture_swing(attacker, defender, largest_opponent_value):
    attacker_value = _piece_score(attacker, largest_opponent_value)
    defender_value = _piece_score(defender, attacker_value)
    outcome = _combat_outcome(attacker, defender)
    if outcome > 0:
        return defender_value * 1.05
    if outcome == 0:
        return defender_value - attacker_value * 0.9
    return -attacker_value * 1.1


def _move_order_score(board, move, side, tt_move=None, ply=0, root_prev_move=None):
    fr, fc, tr, tc = move
    attacker = board[fr][fc].piece
    defender = board[tr][tc].piece
    score = 0

    if tt_move == move:
        score += 200000

    killers = KILLER_MOVES.get(ply, [])
    if len(killers) > 0 and killers[0] == move:
        score += 15000
    elif len(killers) > 1 and killers[1] == move:
        score += 9000

    score += HISTORY_TABLE[(side, move)]

    if defender != None:
        score += 80000
        # In hidden mode, defender.order is not something AI should "see" for
        # unrevealed B pieces — skip the flag-hunt priority bonus so the AI
        # cannot target flags by identity.
        if defender.order == 0 and not _is_hidden_to_ai(defender):
            score += 100000
        score += int(_capture_swing(attacker, defender, getattr(defender, "value", 0)) * 20)

    advance_delta = _advance_score(attacker, tr) - _advance_score(attacker, fr)
    score += int(advance_delta * 10)
    if (tr, tc) in KEY_CELLS:
        score += 40
    if isinstance(board[tr][tc], Camp):
        score += 60
    if root_prev_move != None and _is_reverse_move(move, root_prev_move):
        score -= 1200
    return score


def _is_reverse_move(move, prev_move):
    if move == None or prev_move == None:
        return False
    return (
        move[0] == prev_move[2] and
        move[1] == prev_move[3] and
        move[2] == prev_move[0] and
        move[3] == prev_move[1]
    )


def _leaf_score(board):
    return quiescence_search(board, "A", -INF, INF, _profile_value("qdepth"))


# Adjacency directions for fast threat detection
_ADJ_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# Railroad lines for remote threat scanning.
# Each entry is a contiguous straight line on which pieces can move freely
# (and from which other pieces on the same line are reachable in one move,
# ignoring sapper turns). Rails 5/6 split at the front-line junctions but
# remain useful as "visibility lines" for threat detection.
_RAIL_LINES = [
    # Vertical lines on col 0 and col 4, rows 1..10
    [(r, 0) for r in range(1, 11)],
    [(r, 4) for r in range(1, 11)],
    # Horizontal lines on rows 1, 5, 6, 10
    [(1, c) for c in range(5)],
    [(5, c) for c in range(5)],
    [(6, c) for c in range(5)],
    [(10, c) for c in range(5)],
]

# Map each railroad cell → list of (line, index_in_line) it belongs to
_RAIL_CELL_LINES = {}
for _line in _RAIL_LINES:
    for _idx, _pos in enumerate(_line):
        _RAIL_CELL_LINES.setdefault(_pos, []).append((_line, _idx))


def _rail_nearest_enemy(board, line, idx, side):
    """Return list of (piece, enemy_pos, distance) for nearest enemy in both
    directions on a rail line. Stops at first non-empty cell in each direction."""
    results = []
    # Forward
    for j in range(idx + 1, len(line)):
        r, c = line[j]
        p = board[r][c].piece
        if p is not None:
            if p.side != side:
                results.append((p, (r, c), j - idx))
            break
    # Backward
    for j in range(idx - 1, -1, -1):
        r, c = line[j]
        p = board[r][c].piece
        if p is not None:
            if p.side != side:
                results.append((p, (r, c), idx - j))
            break
    return results


def _game_phase_multipliers(board):
    """Return (advance_mul, control_mul, threat_mul, phase_tag) based on total material.
    Phase thresholds tuned for land-battle-chess (initial total material ~540 per side
    excluding flags)."""
    total = 0
    for x in range(12):
        for y in range(5):
            p = board[x][y].piece
            if p is None or p.order == 0:
                continue
            if p.order is None:
                total += 50  # bombs
            else:
                total += getattr(p, "value", 0)
    # Phase by total material on the board (both sides combined)
    if total > 700:
        return (0.5, 1.5, 1.0, "opening")
    if total > 300:
        return (1.0, 1.0, 1.0, "midgame")
    return (3.0, 0.8, 1.5, "endgame")


def getBoardScore(board, include_mobility=True):
    """Fast static evaluation — NO isLegal() calls, pure board scan O(60)."""
    largestA, largestB = getLargestPiece(board)
    adv_w = _profile_value("advance_weight")
    ctrl_w = _profile_value("control_weight")
    threat_w = _profile_value("threat_weight")

    # Phase-aware scaling
    adv_mul, ctrl_mul, threat_mul, _phase = _game_phase_multipliers(board)
    adv_w *= adv_mul
    ctrl_w *= ctrl_mul
    threat_w *= threat_mul

    score = 0.0
    flagA = None
    flagB = None

    # --- Single pass: material + positional + adjacency threats ---
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece is None:
                continue

            is_a = piece.side == "A"
            sign = 1 if is_a else -1
            largest_opp = largestB if is_a else largestA

            # Material score
            score += sign * _piece_score(piece, largest_opp)

            # Track flags
            if piece.order == 0:
                if is_a:
                    flagA = (x, y)
                else:
                    flagB = (x, y)
                continue

            # Mines: material only, no positional value
            if piece.order == 10:
                continue

            # Advancement bonus
            score += sign * _advance_score(piece, x) * adv_w

            # Key cells / camp control
            if (x, y) in KEY_CELLS:
                score += sign * ctrl_w
            if isinstance(board[x][y], Camp):
                score += sign * ctrl_w * 0.75

            # Adjacency-based threat detection (replaces expensive isLegal)
            if not isinstance(board[x][y], Headquarters):
                piece_val = _piece_score(piece, largest_opp)
                for dx, dy in _ADJ_DIRS:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < 12 and 0 <= ny < 5):
                        continue
                    neighbor = board[nx][ny].piece
                    if neighbor is None or neighbor.side == piece.side:
                        continue
                    # Pieces in camps are protected
                    if isinstance(board[nx][ny], Camp):
                        continue
                    neighbor_val = _piece_score(
                        neighbor, largest_opp)
                    outcome = _combat_outcome(piece, neighbor)
                    if outcome > 0:
                        # Can capture this neighbor — opportunity
                        score += sign * neighbor_val * 0.15 * threat_w
                    elif outcome == 0:
                        # Mutual destruction — net value matters
                        score += sign * (neighbor_val -
                                         piece_val) * 0.08 * threat_w
                    else:
                        # Would lose — danger
                        score -= sign * piece_val * 0.12 * threat_w

                # Railroad remote threat: if this piece is on a rail line,
                # see what enemy is visible along it. Mines/flags never move,
                # so skip them as the attacker (they can still be a target).
                if piece.order not in (10, 0) and (x, y) in _RAIL_CELL_LINES:
                    for line, idx in _RAIL_CELL_LINES[(x, y)]:
                        for enemy, (ex, ey), dist in _rail_nearest_enemy(board, line, idx, piece.side):
                            # Enemies inside a camp are untargetable
                            if isinstance(board[ex][ey], Camp):
                                continue
                            enemy_val = _piece_score(enemy, largest_opp)
                            outcome = _combat_outcome(piece, enemy)
                            atten = 1.0 / dist  # closer threats matter more
                            if outcome > 0:
                                score += sign * enemy_val * 0.08 * threat_w * atten
                            elif outcome == 0:
                                score += sign * (enemy_val - piece_val) * 0.04 * threat_w * atten
                            else:
                                score -= sign * piece_val * 0.06 * threat_w * atten

    # --- Flag safety ---
    for flag_pos, flag_side in [(flagA, "A"), (flagB, "B")]:
        if flag_pos is None:
            continue
        fx, fy = flag_pos
        sign = 1 if flag_side == "A" else -1
        opp_largest = largestB if flag_side == "A" else largestA

        # Immediate adjacency: protectors and attackers
        for dx, dy in _ADJ_DIRS:
            nx, ny = fx + dx, fy + dy
            if 0 <= nx < 12 and 0 <= ny < 5:
                n = board[nx][ny].piece
                if n is not None:
                    if n.side == flag_side:
                        score += sign * 25
                    else:
                        score -= sign * 100

        # Nearby enemies (Manhattan distance 2-3): pressure on flag
        for x2 in range(max(0, fx - 3), min(12, fx + 4)):
            for y2 in range(max(0, fy - 3), min(5, fy + 4)):
                dist = abs(x2 - fx) + abs(y2 - fy)
                if dist < 2 or dist > 3:
                    continue
                n = board[x2][y2].piece
                if n is not None and n.side != flag_side and n.order not in (0, 10, None):
                    pv = _piece_score(n, opp_largest)
                    score -= sign * pv * (4 - dist) * 0.03

    # --- Tactical patterns ---
    score += _tactical_patterns(board, flagA, flagB, largestA, largestB)

    return int(score)


def _tactical_patterns(board, flagA, flagB, largestA, largestB):
    """Detect military-chess-specific tactical motifs.
    All scoring is from A's perspective (positive = good for A)."""
    tscore = 0.0

    # 1. Bomb ambush: own bomb adjacent to enemy Marshal/General (order>=8)
    # 2. Trapped big piece: own order>=7 with all 4 neighbors blocked
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece is None:
                continue
            sign = 1 if piece.side == "A" else -1
            # Bomb ambush
            if piece.order is None:  # bomb
                for dx, dy in _ADJ_DIRS:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < 12 and 0 <= ny < 5):
                        continue
                    n = board[nx][ny].piece
                    if n is None or n.side == piece.side:
                        continue
                    if n.order is not None and n.order >= 8:
                        tscore += sign * 35
                        break  # one per bomb is enough
            # Trapped big piece (order 7/8/9)
            if piece.order is not None and piece.order >= 7 and piece.order <= 9:
                if isinstance(board[x][y], Camp):
                    continue
                blocked = 0
                has_escape = False
                for dx, dy in _ADJ_DIRS:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < 12 and 0 <= ny < 5):
                        blocked += 1
                        continue
                    n = board[nx][ny].piece
                    if n is None:
                        has_escape = True
                        break
                    if n.side == piece.side:
                        blocked += 1
                    else:
                        # Enemy: escape if we can beat it
                        if _combat_outcome(piece, n) > 0:
                            has_escape = True
                            break
                        blocked += 1
                if not has_escape and blocked >= 4:
                    # Not on a railroad escape hatch?
                    if (x, y) not in railroadPosts:
                        tscore -= sign * 25

    # 3. Sapper vs landmine alignment on railroad lines
    # For each friendly sapper on a rail line, check if an enemy mine is
    # reachable along that line with no blockers.
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece is None or piece.order != 1:  # not a sapper
                continue
            if (x, y) not in _RAIL_CELL_LINES:
                continue
            sign = 1 if piece.side == "A" else -1
            for line, idx in _RAIL_CELL_LINES[(x, y)]:
                for direction in (1, -1):
                    j = idx + direction
                    while 0 <= j < len(line):
                        r, c = line[j]
                        p = board[r][c].piece
                        if p is None:
                            j += direction
                            continue
                        if p.side != piece.side and p.order == 10:
                            tscore += sign * 20
                        break

    # 4. Flag defense integrity: check the row in front of each flag
    # for mines/bombs/big pieces. A gap in the defense line is bad.
    for flag_pos, flag_side in [(flagA, "A"), (flagB, "B")]:
        if flag_pos is None:
            continue
        fx, fy = flag_pos
        sign = 1 if flag_side == "A" else -1
        # The row immediately in front of the HQ
        front_row = fx + 1 if flag_side == "A" else fx - 1
        if not (0 <= front_row < 12):
            continue
        defenders = 0
        for c in range(max(0, fy - 1), min(5, fy + 2)):
            d = board[front_row][c].piece
            if d is None or d.side != flag_side:
                continue
            if d.order == 10 or d.order is None or (d.order is not None and d.order >= 7):
                defenders += 1
        if defenders >= 2:
            tscore += sign * 40
        elif defenders == 0:
            tscore -= sign * 30

    return tscore



def _terminal_score(board, ply=0):
    has_flag_a = False
    has_flag_b = False
    mobile_a = False
    mobile_b = False
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece is None:
                continue
            if piece.order == 0:
                if piece.side == "A":
                    has_flag_a = True
                else:
                    has_flag_b = True
            elif piece.order != 10 and not isinstance(board[x][y], Headquarters):
                if piece.side == "A":
                    mobile_a = True
                else:
                    mobile_b = True
    if not has_flag_a:
        return -MATE_SCORE + ply
    if not has_flag_b:
        # In hidden mode the AI cannot know which B piece is the flag until
        # it is revealed. Returning MATE here would let the search tree plan
        # exact flag-capture lines using the hidden piece identity. Let the
        # static eval grade the post-capture position instead; the game-over
        # check in app.py still ends the real game correctly.
        if _HIDE_ENEMY_INFO:
            return None
        return MATE_SCORE - ply
    # Both sides have potentially mobile pieces — not terminal (fast path)
    if mobile_a and mobile_b:
        return None
    # Rare: one side may have only immovable pieces left — full check needed
    winner = isOver(board)
    if winner == "A":
        return MATE_SCORE - ply
    if winner == "B":
        return -MATE_SCORE + ply
    return None



def _all_moves(board, side, captures_only=False):
    moves = []
    rows = range(11, -1, -1) if side == "A" else range(12)
    for x in rows:
        for y in range(5):
            piece = board[x][y].piece
            if piece != None and piece.side == side:
                for (a, b) in isLegal(board, (x, y)):
                    if captures_only and board[a][b].piece == None:
                        continue
                    moves.append((x, y, a, b))
    return moves


def _ordered_moves(board, side, tt_move=None, ply=0, root_prev_move=None, captures_only=False):
    moves = _all_moves(board, side, captures_only=captures_only)
    moves.sort(
        key=lambda move: _move_order_score(board, move, side, tt_move, ply, root_prev_move),
        reverse=True,
    )
    return moves


def _board_key(board, side):
    # Uses the running Zobrist hash (updated incrementally by applyMove/undoMove).
    # O(1) vs the old O(60) tuple construction.
    return (side, ZOBRIST_HASH)


def _is_search_timeout():
    return SEARCH_DEADLINE != None and time.perf_counter() >= SEARCH_DEADLINE


def _record_killer(ply, move):
    killers = KILLER_MOVES[ply]
    if move in killers:
        killers.remove(move)
    killers.insert(0, move)
    del killers[2:]


def _record_history(side, move, depth_left):
    HISTORY_TABLE[(side, move)] += depth_left * depth_left * 40


def _tt_lookup(board, side, depth_left, alpha, beta):
    key = _board_key(board, side)
    entry = TRANSPOSITION_TABLE.get(key)
    if entry == None or entry["depth"] < depth_left:
        return (None, alpha, beta, None)
    score = entry["score"]
    move = entry["move"]
    flag = entry["flag"]
    if flag == TT_EXACT:
        return ((move, score), alpha, beta, move)
    if flag == TT_LOWER:
        alpha = max(alpha, score)
    elif flag == TT_UPPER:
        beta = min(beta, score)
    if alpha >= beta:
        return ((move, score), alpha, beta, move)
    return (None, alpha, beta, move)


def _tt_store(board, side, depth_left, score, move, flag):
    TRANSPOSITION_TABLE[_board_key(board, side)] = {
        "depth": depth_left,
        "score": score,
        "move": move,
        "flag": flag,
    }



def quiescence_search(board, side, alpha, beta, qdepth):
    global NODE_COUNT
    NODE_COUNT += 1
    if _is_search_timeout():
        raise TimeoutError

    terminal = _terminal_score(board)
    if terminal != None:
        return terminal

    stand_pat = getBoardScore(board, include_mobility=False)
    if side == "A":
        if stand_pat >= beta:
            return stand_pat
        alpha = max(alpha, stand_pat)
    else:
        if stand_pat <= alpha:
            return stand_pat
        beta = min(beta, stand_pat)

    if qdepth <= 0:
        return stand_pat

    moves = _ordered_moves(board, side, captures_only=True)
    if len(moves) == 0:
        return stand_pat

    if side == "A":
        best = stand_pat
        for fr, fc, tr, tc in moves:
            fromPost, toPost = applyMove(board, fr, fc, tr, tc)
            try:
                score = quiescence_search(board, "B", alpha, beta, qdepth - 1)
            finally:
                undoMove(board, fr, fc, tr, tc, fromPost, toPost)
            best = max(best, score)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best

    best = stand_pat
    for fr, fc, tr, tc in moves:
        fromPost, toPost = applyMove(board, fr, fc, tr, tc)
        try:
            score = quiescence_search(board, "A", alpha, beta, qdepth - 1)
        finally:
            undoMove(board, fr, fc, tr, tc, fromPost, toPost)
        best = min(best, score)
        beta = min(beta, best)
        if alpha >= beta:
            break
    return best


def _alpha_beta(board, side, depth_left, alpha, beta, ply=0, allow_null=True):
    global NODE_COUNT
    NODE_COUNT += 1
    if _is_search_timeout():
        raise TimeoutError

    alpha_original = alpha
    beta_original = beta

    # Repetition detection: if we've seen this exact position on the current
    # search path, treat it as a draw. Only matters for ply > 0 since the root
    # position was just reached fresh.
    if ply > 0 and ZOBRIST_HASH in POSITION_HISTORY:
        return (None, 0)

    terminal = _terminal_score(board, ply)
    if terminal != None:
        return (None, terminal)

    if depth_left <= 0:
        return (None, quiescence_search(board, side, alpha, beta, _profile_value("qdepth")))

    tt_hit, alpha, beta, tt_move = _tt_lookup(board, side, depth_left, alpha, beta)
    if tt_hit != None:
        return tt_hit

    # --- Null Move Pruning (NMP) ---
    # Skip our turn and see if opponent can still beat us.
    # If not, this position is so good we can prune.
    if allow_null and depth_left >= 3 and ply > 0:
        null_side = "B" if side == "A" else "A"
        R = 2 if depth_left <= 5 else 3
        _, null_score = _alpha_beta(
            board, null_side, depth_left - 1 - R, alpha, beta, ply + 1, False)
        if side == "A" and null_score >= beta:
            return (None, null_score)
        elif side == "B" and null_score <= alpha:
            return (None, null_score)

    moves = _ordered_moves(board, side, tt_move=tt_move, ply=ply)
    if len(moves) == 0:
        return (None, getBoardScore(board, include_mobility=False))

    # --- Futility Pruning setup ---
    # At shallow depths, if static eval is far from alpha/beta, quiet moves
    # are unlikely to change the outcome — skip them to save search time.
    can_futility = depth_left in FUTILITY_MARGIN and ply > 0
    static_eval = None
    if can_futility:
        static_eval = getBoardScore(board, include_mobility=False)

    # Record current position for repetition detection
    cur_hash = ZOBRIST_HASH
    POSITION_HISTORY.add(cur_hash)

    try:
        bestMove = None
        if side == "A":
            # When futility pruning is active, static_eval acts as a stand-pat floor.
            bestScore = static_eval if can_futility else -INF
            for i, (fr, fc, tr, tc) in enumerate(moves):
                move = (fr, fc, tr, tc)
                is_capture = board[tr][tc].piece is not None

                # --- Futility Pruning ---
                if (can_futility and not is_capture and move != tt_move
                        and static_eval + FUTILITY_MARGIN[depth_left] < alpha):
                    continue

                # --- Late Move Reduction (LMR) ---
                reduction = 0
                if (i >= 4 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1

                fromPost, toPost = applyMove(board, fr, fc, tr, tc)
                try:
                    if i == 0:
                        # First move: full window
                        _, childScore = _alpha_beta(
                            board, "B", depth_left - 1 - reduction,
                            alpha, beta, ply + 1)
                    else:
                        # PVS: null window probe
                        _, childScore = _alpha_beta(
                            board, "B", depth_left - 1 - reduction,
                            alpha, alpha + 1, ply + 1)
                    # Re-search if reduced/null-window result beats alpha
                    if (reduction > 0 or i > 0) and childScore > alpha and childScore < beta:
                        _, childScore = _alpha_beta(
                            board, "B", depth_left - 1,
                            alpha, beta, ply + 1)
                finally:
                    undoMove(board, fr, fc, tr, tc, fromPost, toPost)
                if childScore > bestScore:
                    bestScore = childScore
                    bestMove = move
                alpha = max(alpha, bestScore)
                if alpha >= beta:
                    if toPost is None:
                        _record_killer(ply, move)
                    _record_history(side, move, depth_left)
                    break
        else:
            bestScore = static_eval if can_futility else INF
            for i, (fr, fc, tr, tc) in enumerate(moves):
                move = (fr, fc, tr, tc)
                is_capture = board[tr][tc].piece is not None

                # --- Futility Pruning (B side: minimizing) ---
                if (can_futility and not is_capture and move != tt_move
                        and static_eval - FUTILITY_MARGIN[depth_left] > beta):
                    continue

                reduction = 0
                if (i >= 4 and not is_capture and depth_left >= 3
                        and move != tt_move):
                    reduction = 1

                fromPost, toPost = applyMove(board, fr, fc, tr, tc)
                try:
                    if i == 0:
                        _, childScore = _alpha_beta(
                            board, "A", depth_left - 1 - reduction,
                            alpha, beta, ply + 1)
                    else:
                        # PVS: null window probe
                        _, childScore = _alpha_beta(
                            board, "A", depth_left - 1 - reduction,
                            beta - 1, beta, ply + 1)
                    if (reduction > 0 or i > 0) and childScore < beta and childScore > alpha:
                        _, childScore = _alpha_beta(
                            board, "A", depth_left - 1,
                            alpha, beta, ply + 1)
                finally:
                    undoMove(board, fr, fc, tr, tc, fromPost, toPost)
                if childScore < bestScore:
                    bestScore = childScore
                    bestMove = move
                beta = min(beta, bestScore)
                if alpha >= beta:
                    if toPost is None:
                        _record_killer(ply, move)
                    _record_history(side, move, depth_left)
                    break
    finally:
        # Always clean up, even on TimeoutError
        POSITION_HISTORY.discard(cur_hash)

    if bestScore <= alpha_original:
        flag = TT_UPPER
    elif bestScore >= beta_original:
        flag = TT_LOWER
    else:
        flag = TT_EXACT
    _tt_store(board, side, depth_left, bestScore, bestMove, flag)
    return (bestMove, bestScore)


def _fallback_move(board, side, prev_move=None):
    ordered = _ordered_moves(board, side, root_prev_move=prev_move)
    if len(ordered) == 0:
        return (None, getBoardScore(board, include_mobility=False))
    move = ordered[0]
    fr, fc, tr, tc = move
    fromPost, toPost = applyMove(board, fr, fc, tr, tc)
    try:
        score = getBoardScore(board, include_mobility=False)
    finally:
        undoMove(board, fr, fc, tr, tc, fromPost, toPost)
    return (move, score)


def _build_root_candidates(board, side, prev_move=None, top_n=8):
    candidates = []
    ordered = _ordered_moves(board, side, root_prev_move=prev_move)
    for move in ordered[:top_n]:
        candidates.append({
            "move": _move_to_debug(move),
            "order_score": _move_order_score(board, move, side, root_prev_move=prev_move),
        })
    return candidates


def _build_search_debug(board, side, maxDepth, bestMove, bestScore):
    return {
        "side": side,
        "profile": SEARCH_PROFILE,
        "max_depth": maxDepth,
        "completed_depth": LAST_COMPLETED_DEPTH,
        "best_move": _move_to_debug(bestMove),
        "best_score": bestScore,
        "board_score": getBoardScore(board, include_mobility=False),
        "legal_move_count": len(_all_moves(board, side)),
        "nodes": NODE_COUNT,
    }


def get_plan_debug_snapshot(board, side="A", prev_move=None, top_n=8, chosen_move=None):
    if board == None:
        return None
    moves = _all_moves(board, side)
    return {
        "side": side,
        "profile": SEARCH_PROFILE,
        "board_score": getBoardScore(board, include_mobility=False),
        "legal_move_count": len(moves),
        "chosen_move": _move_to_debug(chosen_move),
        "top_n": top_n,
        "candidates": _build_root_candidates(board, side, prev_move, top_n),
    }


def get_last_search_debug():
    return LAST_SEARCH_DEBUG


def _root_search(board, side, maxDepth, alpha, beta, prev_move=None,
                 time_limit_override=None):
    global LAST_SEARCH_DEBUG
    global SEARCH_DEADLINE
    global NODE_COUNT
    global LAST_COMPLETED_DEPTH
    global ZOBRIST_HASH

    # Profile-level depth cap (used to weaken hidden-mode AI without touching
    # the UI-level maxDepth wiring).
    _cap = _profile_value("max_depth_cap", None)
    if _cap is not None and maxDepth > _cap:
        maxDepth = _cap

    # Initialize Zobrist hash from current board — increments handled by applyMove/undoMove.
    ZOBRIST_HASH = compute_zobrist(board, side)
    POSITION_HISTORY.clear()

    terminalScore = _terminal_score(board)
    if terminalScore != None:
        LAST_COMPLETED_DEPTH = 0
        LAST_SEARCH_DEBUG = _build_search_debug(board, side, maxDepth, None, terminalScore)
        LAST_SEARCH_DEBUG["candidates"] = []
        return (None, terminalScore)

    KILLER_MOVES.clear()
    # Decay history table instead of clearing — retain learned move preferences
    for key in list(HISTORY_TABLE):
        HISTORY_TABLE[key] //= 4
        if HISTORY_TABLE[key] == 0:
            del HISTORY_TABLE[key]
    # Keep transposition table across turns; only clear if too large
    if len(TRANSPOSITION_TABLE) > 200000:
        TRANSPOSITION_TABLE.clear()
    NODE_COUNT = 0
    LAST_COMPLETED_DEPTH = 0
    SEARCH_DEADLINE = time.perf_counter() + (
        time_limit_override if time_limit_override is not None
        else _profile_value("time_limit")
    )

    bestMove = None
    bestScore = getBoardScore(board, include_mobility=False)
    timed_out = False
    try:
        for targetDepth in range(1, maxDepth + 1):
            try:
                # Aspiration window: narrow search around previous score
                if targetDepth >= 3 and bestMove is not None:
                    asp = 40
                    a_asp = bestScore - asp
                    b_asp = bestScore + asp
                    move, score = _alpha_beta(
                        board, side, targetDepth, a_asp, b_asp, 0)
                    # Fall outside window — re-search with full bounds
                    if move is None or score <= a_asp or score >= b_asp:
                        move, score = _alpha_beta(
                            board, side, targetDepth, alpha, beta, 0)
                else:
                    move, score = _alpha_beta(
                        board, side, targetDepth, alpha, beta, 0)
            except TimeoutError:
                timed_out = True
                break
            if move != None:
                if prev_move != None and _is_reverse_move(move, prev_move):
                    score += -16 if side == "A" else 16
                bestMove = move
                bestScore = score
            LAST_COMPLETED_DEPTH = targetDepth
    finally:
        SEARCH_DEADLINE = None

    if bestMove == None:
        bestMove, bestScore = _fallback_move(board, side, prev_move)

    # --- Optional weakening: root-level non-optimal pick ---
    # With probability `root_random_prob`, swap the best move for a random
    # pick from the top-K heuristically-ordered moves. Lets the AI "make
    # plausible mistakes" on easy difficulty without breaking play quality.
    _pool = _profile_value("root_random_pool", 1)
    _prob = _profile_value("root_random_prob", 0.0)
    if bestMove is not None and _pool > 1 and _prob > 0 and _random.random() < _prob:
        _ordered = _ordered_moves(board, side, root_prev_move=prev_move)
        if len(_ordered) > 1:
            _pool_moves = list(_ordered[:max(_pool, 1)])
            if bestMove not in _pool_moves:
                _pool_moves[-1] = bestMove
            _alt = _random.choice(_pool_moves)
            if _alt != bestMove:
                fr, fc, tr, tc = _alt
                fromPost, toPost = applyMove(board, fr, fc, tr, tc)
                try:
                    _alt_score = getBoardScore(board, include_mobility=False)
                finally:
                    undoMove(board, fr, fc, tr, tc, fromPost, toPost)
                bestMove = _alt
                bestScore = _alt_score

    LAST_SEARCH_DEBUG = _build_search_debug(board, side, maxDepth, bestMove, bestScore)
    LAST_SEARCH_DEBUG["timed_out"] = timed_out
    LAST_SEARCH_DEBUG["candidates"] = _build_root_candidates(board, side, prev_move, 8)
    return (bestMove, bestScore)


# AI move seeks to maximize the board score
def AIMove(board, maxDepth, depth=0, alpha=-100000, beta=100000, prev_move=None):
    if depth != 0:
        return _alpha_beta(board, "A", maxDepth - depth, alpha, beta, depth)
    return _root_search(board, "A", maxDepth, alpha, beta, prev_move)


# Player move seeks to minimize the board score
def PlayerMove(board, maxDepth, depth=0, alpha=-100000, beta=100000, prev_move=None):
    if depth != 0:
        return _alpha_beta(board, "B", maxDepth - depth, alpha, beta, depth)
    return _root_search(board, "B", maxDepth, alpha, beta, prev_move)
