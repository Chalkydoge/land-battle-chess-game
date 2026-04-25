"""Tournament runner — paired openings, multiprocessing, SPRT early-stop."""

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from pathlib import Path

from bench import engine, game, stats


# ---- Worker-process state -------------------------------------------------
# These globals live in each pool-worker process. The initializer populates
# them once, and _play_job uses them.

_WORKER_ENGINES = {}


def _init_worker(baseline_dir, candidate_dir):
    global _WORKER_ENGINES
    _WORKER_ENGINES = {
        "baseline":  engine.load("baseline",  Path(baseline_dir)),
        "candidate": engine.load("candidate", Path(candidate_dir)),
    }


def _play_job(args):
    seed, sideA_owner, tc, max_plies = args
    return game.play_one_game(
        engines=_WORKER_ENGINES,
        sideA_owner=sideA_owner,
        layout_seed=seed,
        tc=tc,
        max_plies=max_plies,
    )


# ---- Result objects -------------------------------------------------------

@dataclass
class MatchResult:
    tally: stats.Tally
    sprt: stats.SprtDecision
    games: list = field(default_factory=list)
    wall_clock_seconds: float = 0.0
    elo: float = 0.0
    elo_err: float = 0.0


def run(baseline_dir, candidate_dir, tc, max_plies, max_games, workers,
        elo0=0.0, elo1=10.0, alpha=0.05, beta=0.05, seed_offset=0,
        progress_cb=None):
    """Run a paired-self-play match and return MatchResult."""
    tally = stats.Tally()
    games = []
    start = time.perf_counter()

    ctx = mp.get_context("spawn")  # Windows-safe; isolates worker imports
    with ctx.Pool(
        processes=max(1, workers),
        initializer=_init_worker,
        initargs=(str(baseline_dir), str(candidate_dir)),
    ) as pool:

        next_seed = seed_offset
        while tally.total() < max_games:
            batch_seeds = [next_seed + i for i in range(max(1, workers))]
            next_seed += len(batch_seeds)
            jobs = []
            for s in batch_seeds:
                jobs.append((s, "candidate", tc, max_plies))
                jobs.append((s, "baseline",  tc, max_plies))
            for result in pool.imap_unordered(_play_job, jobs):
                tally.record(result.winner)
                games.append(result)
                if progress_cb:
                    progress_cb(tally, len(games))
            decision = stats.sprt(tally, elo0=elo0, elo1=elo1,
                                  alpha=alpha, beta=beta)
            if decision.decision != "undecided":
                break

    decision = stats.sprt(tally, elo0=elo0, elo1=elo1, alpha=alpha, beta=beta)
    elo_val, elo_err = stats.elo(tally)
    return MatchResult(
        tally=tally,
        sprt=decision,
        games=games,
        wall_clock_seconds=time.perf_counter() - start,
        elo=elo_val,
        elo_err=elo_err,
    )
