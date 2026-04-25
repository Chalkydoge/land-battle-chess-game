"""Single-game runner — drives two engine snapshots through one paired game."""

import random
import time
from dataclasses import dataclass, field

import layout


@dataclass
class GameResult:
    winner: str                       # "candidate" / "baseline" / "draw"
    plies: int
    layout_seed: int
    sideA_owner: str                  # "candidate" or "baseline"
    per_engine: dict = field(default_factory=dict)


_OTHER = {"candidate": "baseline", "baseline": "candidate"}


def _opponent(owner):
    return _OTHER[owner]


def play_one_game(engines, sideA_owner, layout_seed, tc, max_plies=300):
    """Play one game between engines["candidate"] and engines["baseline"].

    sideA_owner names which engine plays side "A" (always moves first).
    Returns a GameResult.
    """
    if sideA_owner not in ("candidate", "baseline"):
        raise ValueError(f"bad sideA_owner: {sideA_owner!r}")
    if not {"candidate", "baseline"}.issubset(engines):
        raise ValueError("engines dict must contain 'candidate' and 'baseline'")

    rng = random.Random(layout_seed)
    board = layout.build_initial_board(rng)

    side_to_owner = {
        "A": sideA_owner,
        "B": _opponent(sideA_owner),
    }

    metrics = {
        "candidate": {"nodes": 0, "depths": [], "move_times": []},
        "baseline":  {"nodes": 0, "depths": [], "move_times": []},
    }

    side = "A"
    prev_move = None
    plies = 0
    winner = "draw"

    while plies < max_plies:
        owner = side_to_owner[side]
        eng = engines[owner]

        start = time.perf_counter()
        move, _ = eng._root_search(
            board, side,
            999,
            -10 ** 9, 10 ** 9,
            prev_move=prev_move,
            time_limit_override=tc,
        )
        elapsed = time.perf_counter() - start

        if move is None:
            # No legal move for the current side — opponent wins.
            winner = _opponent(owner)
            break

        metrics[owner]["nodes"] += getattr(eng, "NODE_COUNT", 0)
        metrics[owner]["depths"].append(getattr(eng, "LAST_COMPLETED_DEPTH", 0))
        metrics[owner]["move_times"].append(elapsed)

        fr, fc, tr, tc_col = move
        target_piece = board[tr][tc_col].piece
        flag_captured = target_piece is not None and target_piece.order == 0

        eng.applyMove(board, fr, fc, tr, tc_col)
        plies += 1

        if flag_captured:
            winner = owner
            break

        # If isOver returned True after our move, the side-to-move-next has no
        # legal moves — they lose. Mover wins.
        if eng.isOver(board):
            winner = owner
            break

        side = "B" if side == "A" else "A"
        prev_move = move

    per_engine = {}
    for owner, m in metrics.items():
        depths = m["depths"]
        times = sorted(m["move_times"])
        if times:
            p50 = times[len(times) // 2]
            p95 = times[max(0, int(len(times) * 0.95) - 1)]
        else:
            p50 = p95 = 0.0
        per_engine[owner] = {
            "nodes": m["nodes"],
            "avg_depth": sum(depths) / len(depths) if depths else 0.0,
            "tpm_p50": p50,
            "tpm_p95": p95,
            "moves": len(depths),
        }

    return GameResult(
        winner=winner,
        plies=plies,
        layout_seed=layout_seed,
        sideA_owner=sideA_owner,
        per_engine=per_engine,
    )
