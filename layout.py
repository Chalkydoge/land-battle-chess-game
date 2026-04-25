"""Seedable layout & board init — shared between app.py (web) and bench/."""

import random as _random_module
from pieceClasses import (
    Mar, Gen, MGen, BGen, Col, Maj, Capt, Lt, Spr, Bomb, LMN, Flag,
    Post, Camp, Headquarters,
)


CAMP_POSITIONS_A = {(2, 1), (2, 3), (3, 2), (4, 1), (4, 3)}
CAMP_POSITIONS_B = {(7, 1), (7, 3), (8, 2), (9, 1), (9, 3)}
HQ_POSITIONS_A = {(0, 1), (0, 3)}
HQ_POSITIONS_B = {(11, 1), (11, 3)}


def make_pieces(side):
    """All 25 pieces for one side."""
    return [
        Mar(side), Gen(side), MGen(side), MGen(side),
        BGen(side), BGen(side), Col(side), Col(side),
        Maj(side), Maj(side), Capt(side), Capt(side), Capt(side),
        Lt(side), Lt(side), Lt(side), Spr(side), Spr(side), Spr(side),
        Bomb(side), Bomb(side), LMN(side), LMN(side), LMN(side),
        Flag(side),
    ]


def random_layout_for_side(side, rng=None):
    """Strategically-weighted random layout, seedable via `rng`.

    rng must be a random.Random instance (or None to use module random).
    """
    if rng is None:
        rng = _random_module

    if side == "A":
        camps = CAMP_POSITIONS_A
        hqs = HQ_POSITIONS_A
        back_rows = {0, 1}
        mid_rows = {2, 3}
        front_rows = {4, 5}
        front_row = 5
    else:
        camps = CAMP_POSITIONS_B
        hqs = HQ_POSITIONS_B
        back_rows = {10, 11}
        mid_rows = {8, 9}
        front_rows = {6, 7}
        front_row = 6

    all_rows = sorted(back_rows | mid_rows | front_rows)
    all_pos = [(r, c) for r in all_rows for c in range(5)
               if (r, c) not in camps and (r, c) not in hqs]
    hq_list = list(hqs)

    pieces = make_pieces(side)
    flag = [p for p in pieces if isinstance(p, Flag)][0]
    lmns = [p for p in pieces if isinstance(p, LMN)]
    bombs = [p for p in pieces if isinstance(p, Bomb)]
    marshal = [p for p in pieces if isinstance(p, Mar)][0]
    general = [p for p in pieces if isinstance(p, Gen)][0]
    mgens = [p for p in pieces if isinstance(p, MGen)]
    bgens = [p for p in pieces if isinstance(p, BGen)]
    sappers = [p for p in pieces if isinstance(p, Spr)]
    others = [p for p in pieces if isinstance(p, (Col, Maj, Capt, Lt))]
    rng.shuffle(others)

    placement = {}

    def available(zone_rows=None):
        return [p for p in all_pos + hq_list
                if p not in placement and
                (zone_rows is None or p[0] in zone_rows)]

    def place_in(piece, candidates):
        opts = [c for c in candidates if c not in placement]
        if not opts:
            opts = [p for p in all_pos + hq_list if p not in placement]
        pos = rng.choice(opts)
        placement[pos] = piece

    flag_pos = rng.choice(hq_list)
    placement[flag_pos] = flag
    fx, fy = flag_pos

    mine_candidates = [p for p in all_pos
                       if p[0] in back_rows and p not in placement]
    mine_candidates.sort(key=lambda p: abs(p[0] - fx) + abs(p[1] - fy))
    for i, lmn in enumerate(lmns):
        placement[mine_candidates[i]] = lmn

    bomb_back = [p for p in all_pos
                 if p[0] in back_rows and p not in placement]
    bomb_back.sort(key=lambda p: abs(p[0] - fx) + abs(p[1] - fy))
    if bomb_back:
        placement[bomb_back[0]] = bombs[0]
    else:
        place_in(bombs[0], available(mid_rows))

    bomb_mid = [p for p in all_pos
                if p[0] in mid_rows and p not in placement]
    rng.shuffle(bomb_mid)
    if bomb_mid:
        placement[bomb_mid[0]] = bombs[1]
    else:
        place_in(bombs[1], [p for p in available() if p[0] != front_row])

    mid_spots = available(mid_rows)
    rng.shuffle(mid_spots)
    for piece in [marshal, general]:
        if mid_spots:
            placement[mid_spots.pop()] = piece
        else:
            place_in(piece, available(back_rows))

    front_spots = available(front_rows)
    rng.shuffle(front_spots)
    for piece in mgens + bgens:
        if front_spots:
            placement[front_spots.pop()] = piece
        else:
            place_in(piece, available(mid_rows))

    rail_spots = [p for p in available() if p[1] in (0, 4)]
    rng.shuffle(rail_spots)
    if rail_spots:
        placement[rail_spots[0]] = sappers[0]
        remaining_sappers = sappers[1:]
    else:
        remaining_sappers = sappers

    fill_pieces = others + remaining_sappers
    rng.shuffle(fill_pieces)
    fill_spots = available()
    rng.shuffle(fill_spots)
    for i, piece in enumerate(fill_pieces):
        placement[fill_spots[i]] = piece

    return placement


def build_initial_board(rng=None):
    """Build a 12x5 board populated with a seeded random layout for both sides."""
    if rng is None:
        rng = _random_module
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
    for side in ("A", "B"):
        for (r, c), piece in random_layout_for_side(side, rng).items():
            board[r][c].piece = piece
    return board
