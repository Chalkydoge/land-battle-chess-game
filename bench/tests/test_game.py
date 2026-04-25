import random
import pytest
from bench import snapshot, engine, game


@pytest.fixture(scope="module")
def loaded_engines():
    snapshot.freeze("HEAD")
    eng = engine.load("HEAD_a", snapshot.resolve("HEAD"))
    eng2 = engine.load("HEAD_b", snapshot.resolve("HEAD"))
    return {"candidate": eng, "baseline": eng2}


def test_play_one_game_terminates(loaded_engines):
    result = game.play_one_game(
        engines=loaded_engines,
        sideA_owner="candidate",
        layout_seed=42,
        tc=0.05,
        max_plies=60,
    )
    assert result.winner in ("candidate", "baseline", "draw")
    assert 1 <= result.plies <= 60
    assert result.layout_seed == 42
    assert result.sideA_owner == "candidate"
    assert "candidate" in result.per_engine
    assert "baseline" in result.per_engine


def test_paired_game_uses_same_layout():
    """Two games with the same seed must start from identical boards."""
    import layout
    rng_a = random.Random(7)
    rng_b = random.Random(7)
    board_a = layout.build_initial_board(rng_a)
    board_b = layout.build_initial_board(rng_b)
    for r in range(12):
        for c in range(5):
            pa = board_a[r][c].piece
            pb = board_b[r][c].piece
            if pa is None:
                assert pb is None
            else:
                assert type(pa) is type(pb) and pa.side == pb.side


def test_max_plies_forces_draw(loaded_engines):
    """A pathologically tiny ply cap must yield a draw."""
    result = game.play_one_game(
        engines=loaded_engines,
        sideA_owner="candidate",
        layout_seed=11,
        tc=0.05,
        max_plies=4,
    )
    # 4 plies is way too few to capture a flag from the random start
    assert result.winner == "draw"
    assert result.plies == 4
