"""Elo + SPRT statistics for paired self-play."""

import math
from dataclasses import dataclass


@dataclass
class Tally:
    """Win/draw/loss counts from the candidate's perspective."""
    W: int = 0
    D: int = 0
    L: int = 0

    def record(self, winner):
        if winner == "candidate":
            self.W += 1
        elif winner == "baseline":
            self.L += 1
        elif winner == "draw":
            self.D += 1
        else:
            raise ValueError(f"unknown winner {winner!r}")

    def total(self):
        return self.W + self.D + self.L


@dataclass
class SprtDecision:
    decision: str
    llr: float
    upper: float
    lower: float


_ELO_CAP = 1200.0


def _score_rate(t):
    n = t.total()
    if n == 0:
        return 0.5
    return (t.W + 0.5 * t.D) / n


def elo(t):
    """Return (elo_estimate, std_error) from a Tally."""
    n = t.total()
    if n == 0:
        return 0.0, float("inf")
    score = _score_rate(t)
    if score <= 0.0:
        return -_ELO_CAP, float("inf")
    if score >= 1.0:
        return _ELO_CAP, float("inf")
    elo_est = -400.0 * math.log10(1.0 / score - 1.0)
    var_terms = t.W * t.L + (t.W + t.L) * t.D / 4.0
    if var_terms <= 0:
        return elo_est, float("inf")
    err = 400.0 * math.sqrt(var_terms) / (n * math.log(10) * score * (1.0 - score))
    return elo_est, err


def _elo_to_score(elo_value):
    return 1.0 / (1.0 + 10.0 ** (-elo_value / 400.0))


def sprt(t, elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05):
    """Sequential probability ratio test on win/draw/loss counts.

    H0: true Elo = elo0 (typically 0 — change is no improvement)
    H1: true Elo = elo1 (typically +10 — change is a real improvement)
    """
    n = t.total()
    upper = math.log((1.0 - beta) / alpha)
    lower = math.log(beta / (1.0 - alpha))

    if n == 0:
        return SprtDecision(decision="undecided", llr=0.0, upper=upper, lower=lower)

    p0 = _elo_to_score(elo0)
    p1 = _elo_to_score(elo1)

    wins_eq = t.W + 0.5 * t.D
    losses_eq = t.L + 0.5 * t.D
    if not (0 < p0 < 1) or not (0 < p1 < 1):
        return SprtDecision(decision="undecided", llr=0.0, upper=upper, lower=lower)
    llr = (wins_eq * math.log(p1 / p0)
           + losses_eq * math.log((1.0 - p1) / (1.0 - p0)))

    if llr >= upper:
        decision = "accept_H1"
    elif llr <= lower:
        decision = "accept_H0"
    else:
        decision = "undecided"
    return SprtDecision(decision=decision, llr=llr, upper=upper, lower=lower)
