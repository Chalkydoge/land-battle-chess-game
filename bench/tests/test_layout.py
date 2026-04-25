import random
import layout


def test_same_seed_same_layout():
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    placement_a = layout.random_layout_for_side("A", rng_a)
    placement_b = layout.random_layout_for_side("A", rng_b)
    # Same seed → identical positions and identical piece classes/orders
    assert sorted(placement_a.keys()) == sorted(placement_b.keys())
    for pos in placement_a:
        pa = placement_a[pos]
        pb = placement_b[pos]
        assert type(pa) is type(pb)
        assert pa.order == pb.order


def test_different_seeds_differ():
    placement_a = layout.random_layout_for_side("A", random.Random(1))
    placement_b = layout.random_layout_for_side("A", random.Random(2))
    # Extremely unlikely two different seeds produce identical placement
    differs = any(
        type(placement_a[pos]) is not type(placement_b.get(pos))
        for pos in placement_a
    )
    assert differs


def test_build_initial_board_deterministic():
    board_a = layout.build_initial_board(random.Random(7))
    board_b = layout.build_initial_board(random.Random(7))
    for r in range(12):
        for c in range(5):
            pa = board_a[r][c].piece
            pb = board_b[r][c].piece
            if pa is None:
                assert pb is None
            else:
                assert type(pa) is type(pb)
                assert pa.side == pb.side
