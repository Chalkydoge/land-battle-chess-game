import math
from bench import stats


def test_tally_starts_zero():
    t = stats.Tally()
    assert t.W == 0 and t.D == 0 and t.L == 0
    assert t.total() == 0


def test_tally_record():
    t = stats.Tally()
    t.record("candidate")
    t.record("candidate")
    t.record("baseline")
    t.record("draw")
    assert t.W == 2 and t.L == 1 and t.D == 1
    assert t.total() == 4


def test_elo_balanced_returns_zero():
    # 50% score → Elo 0
    t = stats.Tally(W=50, D=0, L=50)
    elo, err = stats.elo(t)
    assert abs(elo) < 1e-6
    assert err > 0


def test_elo_perfect_returns_high_value():
    # All wins → very high Elo (capped or clipped)
    t = stats.Tally(W=10, D=0, L=0)
    elo, err = stats.elo(t)
    # Score=1 → log10(1/1 - 1) = -inf, so we expect a large finite cap
    assert elo > 700


def test_elo_known_value():
    # 75% score → Elo = -400 * log10(1/0.75 - 1) ≈ +191
    t = stats.Tally(W=15, D=0, L=5)
    elo, _ = stats.elo(t)
    expected = -400.0 * math.log10(1.0 / 0.75 - 1.0)
    assert abs(elo - expected) < 0.5


def test_sprt_undecided_at_start():
    t = stats.Tally(W=1, D=0, L=1)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "undecided"
    assert -2.95 < decision.llr < 2.95


def test_sprt_accepts_strong_candidate():
    # Strong dominance — should accept H1
    t = stats.Tally(W=160, D=10, L=30)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "accept_H1"
    assert decision.llr >= 2.94


def test_sprt_rejects_weak_candidate():
    # Strong negative — should accept H0 (reject H1)
    t = stats.Tally(W=30, D=10, L=160)
    decision = stats.sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05)
    assert decision.decision == "accept_H0"
    assert decision.llr <= -2.94
