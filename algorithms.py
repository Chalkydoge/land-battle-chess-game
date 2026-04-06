######## This file contains the core game rules and a stronger search-based AI

import time
from collections import defaultdict

from pieceClasses import *


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
PROFILE_SETTINGS = {
    "fast": {
        "time_limit": 0.9,
        "qdepth": 2,
        "mobility_weight": 0.12,
        "advance_weight": 0.16,
        "control_weight": 1.5,
        "pressure_weight": 0.45,
        "danger_weight": 0.75,
    },
    "strong": {
        "time_limit": 4.2,
        "qdepth": 4,
        "mobility_weight": 0.2,
        "advance_weight": 0.22,
        "control_weight": 2.2,
        "pressure_weight": 0.75,
        "danger_weight": 1.15,
    },
}


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
    fromPost = board[fr][fc].piece
    toPost = board[tr][tc].piece
    if toPost == None:
        board[tr][tc].piece = fromPost
        board[fr][fc].piece = None
    else:
        contact(fr, fc, tr, tc, board)
    return (fromPost, toPost)



def undoMove(board, fr, fc, tr, tc, fromPost, toPost):
    board[fr][fc].piece = fromPost
    board[tr][tc].piece = toPost



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
    if profile in ("fast", "strong"):
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


def _profile_value(key):
    return PROFILE_SETTINGS.get(SEARCH_PROFILE, PROFILE_SETTINGS["fast"])[key]


def _piece_score(piece, largest_opponent_value):
    if piece == None:
        return 0
    if piece.order == 0:
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
        if defender.order == 0:
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


def getBoardScore(board, include_mobility=True):
    largestA, largestB = getLargestPiece(board)
    material = 0.0
    mobilityA = 0
    mobilityB = 0
    advanceA = 0
    advanceB = 0
    controlA = defaultdict(int)
    controlB = defaultdict(int)
    winningA = defaultdict(float)
    winningB = defaultdict(float)
    tradeA = defaultdict(float)
    tradeB = defaultdict(float)
    flagA = None
    flagB = None
    pressure = 0.0
    board_control = 0.0

    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece == None:
                continue
            if piece.order == 0:
                if piece.side == "A":
                    flagA = (x, y)
                else:
                    flagB = (x, y)
            if piece.side == "A":
                material += _piece_score(piece, largestB)
                advanceA += _advance_score(piece, x)
            else:
                material -= _piece_score(piece, largestA)
                advanceB += _advance_score(piece, x)
            if (x, y) in KEY_CELLS and piece.order not in (0, 10):
                board_control += 1.2 if piece.side == "A" else -1.2
            if isinstance(board[x][y], Camp):
                board_control += 0.9 if piece.side == "A" else -0.9
            if piece.order not in (0, 10) and not isinstance(board[x][y], Headquarters):
                moves = isLegal(board, (x, y))
                if include_mobility:
                    if piece.side == "A":
                        mobilityA += len(moves)
                    else:
                        mobilityB += len(moves)
                if piece.side == "A" and flagB != None:
                    pressure += max(0, 8 - (abs(x - flagB[0]) + abs(y - flagB[1]))) * 0.8
                elif piece.side == "B" and flagA != None:
                    pressure -= max(0, 8 - (abs(x - flagA[0]) + abs(y - flagA[1]))) * 0.8
                for (a, b) in moves:
                    if piece.side == "A":
                        controlA[(a, b)] += 1
                    else:
                        controlB[(a, b)] += 1
                    target = board[a][b].piece
                    if target != None and target.side != piece.side:
                        swing = _capture_swing(piece, target, largestB if piece.side == "A" else largestA)
                        if piece.side == "A":
                            pressure += swing * 0.12
                            outcome = _combat_outcome(piece, target)
                            if outcome > 0:
                                winningA[(a, b)] += 1.0
                            elif outcome == 0:
                                tradeA[(a, b)] += 1.0
                        else:
                            pressure -= swing * 0.12
                            outcome = _combat_outcome(piece, target)
                            if outcome > 0:
                                winningB[(a, b)] += 1.0
                            elif outcome == 0:
                                tradeB[(a, b)] += 1.0

    danger = 0.0
    flag_safety = 0.0
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece == None:
                continue
            piece_value = _piece_score(piece, largestB if piece.side == "A" else largestA)
            if piece.side == "A":
                enemy_winning = winningB[(x, y)]
                enemy_trade = tradeB[(x, y)]
                friendly_cover = controlA[(x, y)]
                local_danger = piece_value * (enemy_winning * 0.32 + enemy_trade * 0.18) - friendly_cover * 1.4
                danger -= max(0.0, local_danger)
            else:
                enemy_winning = winningA[(x, y)]
                enemy_trade = tradeA[(x, y)]
                friendly_cover = controlB[(x, y)]
                local_danger = piece_value * (enemy_winning * 0.32 + enemy_trade * 0.18) - friendly_cover * 1.4
                danger += max(0.0, local_danger)

    if flagA != None:
        flag_safety -= winningB[flagA] * 500
        flag_safety -= tradeB[flagA] * 180
        flag_safety += controlA[flagA] * 24
    if flagB != None:
        flag_safety += winningA[flagB] * 500
        flag_safety += tradeA[flagB] * 180
        flag_safety -= controlB[flagB] * 24

    score = material
    score += int((advanceA - advanceB) * _profile_value("advance_weight"))
    if include_mobility:
        score += int((mobilityA - mobilityB) * _profile_value("mobility_weight"))
    score += int(board_control * _profile_value("control_weight"))
    score += int(pressure * _profile_value("pressure_weight"))
    score += int(danger * _profile_value("danger_weight"))
    score += int(flag_safety)
    return score



def _terminal_score(board, ply=0):
    has_flag_a = False
    has_flag_b = False
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece != None and piece.order == 0:
                if piece.side == "A":
                    has_flag_a = True
                else:
                    has_flag_b = True
    if not has_flag_a:
        return -MATE_SCORE + ply
    if not has_flag_b:
        return MATE_SCORE - ply

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
    cells = []
    for x in range(12):
        for y in range(5):
            piece = board[x][y].piece
            if piece == None:
                cells.append(0)
            else:
                order = 11 if piece.order == None else piece.order + 1
                cells.append(order if piece.side == "A" else -order)
    return (side, tuple(cells))


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


def _alpha_beta(board, side, depth_left, alpha, beta, ply=0):
    global NODE_COUNT
    NODE_COUNT += 1
    if _is_search_timeout():
        raise TimeoutError

    alpha_original = alpha
    beta_original = beta

    terminal = _terminal_score(board, ply)
    if terminal != None:
        return (None, terminal)

    if depth_left <= 0:
        return (None, quiescence_search(board, side, alpha, beta, _profile_value("qdepth")))

    tt_hit, alpha, beta, tt_move = _tt_lookup(board, side, depth_left, alpha, beta)
    if tt_hit != None:
        return tt_hit

    moves = _ordered_moves(board, side, tt_move=tt_move, ply=ply)
    if len(moves) == 0:
        return (None, getBoardScore(board, include_mobility=False))

    bestMove = None
    if side == "A":
        bestScore = -INF
        for fr, fc, tr, tc in moves:
            move = (fr, fc, tr, tc)
            fromPost, toPost = applyMove(board, fr, fc, tr, tc)
            try:
                _, childScore = _alpha_beta(board, "B", depth_left - 1, alpha, beta, ply + 1)
            finally:
                undoMove(board, fr, fc, tr, tc, fromPost, toPost)
            if childScore > bestScore:
                bestScore = childScore
                bestMove = move
            alpha = max(alpha, bestScore)
            if alpha >= beta:
                if toPost == None:
                    _record_killer(ply, move)
                _record_history(side, move, depth_left)
                break
    else:
        bestScore = INF
        for fr, fc, tr, tc in moves:
            move = (fr, fc, tr, tc)
            fromPost, toPost = applyMove(board, fr, fc, tr, tc)
            try:
                _, childScore = _alpha_beta(board, "A", depth_left - 1, alpha, beta, ply + 1)
            finally:
                undoMove(board, fr, fc, tr, tc, fromPost, toPost)
            if childScore < bestScore:
                bestScore = childScore
                bestMove = move
            beta = min(beta, bestScore)
            if alpha >= beta:
                if toPost == None:
                    _record_killer(ply, move)
                _record_history(side, move, depth_left)
                break

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


def _root_search(board, side, maxDepth, alpha, beta, prev_move=None):
    global LAST_SEARCH_DEBUG
    global SEARCH_DEADLINE
    global NODE_COUNT
    global LAST_COMPLETED_DEPTH

    terminalScore = _terminal_score(board)
    if terminalScore != None:
        LAST_COMPLETED_DEPTH = 0
        LAST_SEARCH_DEBUG = _build_search_debug(board, side, maxDepth, None, terminalScore)
        LAST_SEARCH_DEBUG["candidates"] = []
        return (None, terminalScore)

    KILLER_MOVES.clear()
    HISTORY_TABLE.clear()
    TRANSPOSITION_TABLE.clear()
    NODE_COUNT = 0
    LAST_COMPLETED_DEPTH = 0
    SEARCH_DEADLINE = time.perf_counter() + _profile_value("time_limit")

    bestMove = None
    bestScore = getBoardScore(board, include_mobility=False)
    timed_out = False
    try:
        for targetDepth in range(1, maxDepth + 1):
            try:
                move, score = _alpha_beta(board, side, targetDepth, alpha, beta, 0)
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
