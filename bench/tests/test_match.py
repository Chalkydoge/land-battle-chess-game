from pathlib import Path
import pytest
from bench import snapshot, match


@pytest.fixture
def head_snapshot():
    snapshot.freeze("HEAD")
    return snapshot.resolve("HEAD")


def test_match_v1_vs_v1_runs(head_snapshot):
    """Smoke test: HEAD vs HEAD should run a small batch and finish."""
    result = match.run(
        baseline_dir=head_snapshot,
        candidate_dir=head_snapshot,
        tc=0.05,
        max_plies=40,
        max_games=4,
        workers=2,
        elo0=0.0,
        elo1=10.0,
        seed_offset=0,
    )
    assert result.tally.total() >= 4
    assert result.tally.total() <= 4 + 4   # may overshoot by a batch
    assert result.sprt.decision in ("undecided", "accept_H0", "accept_H1")
    assert result.wall_clock_seconds > 0


def test_match_records_per_game(head_snapshot):
    result = match.run(
        baseline_dir=head_snapshot,
        candidate_dir=head_snapshot,
        tc=0.05,
        max_plies=20,
        max_games=2,
        workers=2,
    )
    assert len(result.games) >= 2
    for g in result.games:
        assert g.winner in ("candidate", "baseline", "draw")
        assert g.layout_seed >= 0
