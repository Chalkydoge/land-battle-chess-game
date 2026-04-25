import time
import random
import layout
import algorithms


def test_time_override_caps_search():
    board = layout.build_initial_board(random.Random(99))
    # With a very short time budget, the search must return well within ~50ms
    # of the budget. Default profile ("fast") would allow up to 2 seconds.
    start = time.perf_counter()
    move, score = algorithms._root_search(
        board, "A", maxDepth=12,
        alpha=-10**9, beta=10**9,
        prev_move=None,
        time_limit_override=0.05,
    )
    elapsed = time.perf_counter() - start
    assert move is not None
    assert elapsed < 0.5, f"override ignored — took {elapsed:.2f}s"


def test_no_override_uses_profile():
    """Sanity: omitting time_limit_override falls back to profile time_limit."""
    board = layout.build_initial_board(random.Random(100))
    algorithms.set_search_profile("fast")  # 2s budget
    start = time.perf_counter()
    move, _ = algorithms._root_search(
        board, "A", maxDepth=12,
        alpha=-10**9, beta=10**9,
        prev_move=None,
    )
    elapsed = time.perf_counter() - start
    assert move is not None
    # Profile budget is 2.0s; allow generous slack.
    assert elapsed < 3.0, f"profile time budget violated — took {elapsed:.2f}s"
