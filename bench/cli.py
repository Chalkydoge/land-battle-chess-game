"""Command-line entry: bench.cli freeze | match | summary."""

import argparse
import json
import multiprocessing as mp
import os
import sys
from datetime import date
from pathlib import Path

from bench import snapshot, match


def _cmd_freeze(args):
    out = snapshot.freeze(args.tag)
    print(f"frozen → {out}")
    return 0


def _resolve_or_freeze(tag):
    if tag == snapshot.HEAD_TAG:
        return snapshot.freeze(tag)
    return snapshot.resolve(tag)


def _cmd_match(args):
    baseline_dir = _resolve_or_freeze(args.baseline)
    candidate_dir = _resolve_or_freeze(args.candidate)
    print(f"baseline:  {baseline_dir}")
    print(f"candidate: {candidate_dir}")
    print(f"tc={args.tc}s  max_plies={args.max_plies}  "
          f"max_games={args.max_games}  workers={args.workers}")

    def progress(tally, n_done):
        if n_done % max(1, args.workers * 2) == 0:
            print(f"  [{n_done:>4}] W={tally.W} D={tally.D} L={tally.L}",
                  flush=True)

    result = match.run(
        baseline_dir=baseline_dir,
        candidate_dir=candidate_dir,
        tc=args.tc,
        max_plies=args.max_plies,
        max_games=args.max_games,
        workers=args.workers,
        elo0=args.elo0,
        elo1=args.elo1,
        alpha=args.alpha,
        beta=args.beta,
        seed_offset=args.seed_offset,
        progress_cb=progress,
    )

    out_path = _default_out_path(args) if args.out is None else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _result_to_payload(result, args)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print()
    _print_summary(payload)
    print(f"\nresults written to {out_path}")
    return 0


def _cmd_summary(args):
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    _print_summary(payload)
    return 0


def _default_out_path(args):
    today = date.today().isoformat()
    return Path("bench/results") / f"{today}-{args.baseline}-vs-{args.candidate}.json"


def _result_to_payload(result, args):
    return {
        "config": {
            "baseline": args.baseline,
            "candidate": args.candidate,
            "tc": args.tc,
            "max_plies": args.max_plies,
            "max_games": args.max_games,
            "workers": args.workers,
            "elo_bounds": [args.elo0, args.elo1],
            "alpha": args.alpha,
            "beta": args.beta,
            "seed_offset": args.seed_offset,
        },
        "games": [
            {
                "winner": g.winner,
                "plies": g.plies,
                "seed": g.layout_seed,
                "sideA_owner": g.sideA_owner,
                "per_engine": g.per_engine,
            }
            for g in result.games
        ],
        "summary": {
            "W": result.tally.W,
            "D": result.tally.D,
            "L": result.tally.L,
            "total": result.tally.total(),
            "elo": result.elo,
            "elo_err": result.elo_err,
            "sprt": result.sprt.decision,
            "llr": result.sprt.llr,
            "wall_clock_seconds": result.wall_clock_seconds,
        },
    }


def _print_summary(payload):
    s = payload["summary"]
    cfg = payload["config"]
    print("=" * 60)
    print(f"  {cfg['baseline']}  vs  {cfg['candidate']}")
    print("=" * 60)
    print(f"  Games:    {s['total']}  (W={s['W']}  D={s['D']}  L={s['L']})")
    print(f"  Elo:      {s['elo']:+.1f}  +/- {s['elo_err']:.1f}")
    print(f"  SPRT:     {s['sprt']}   (LLR={s['llr']:+.2f})")
    print(f"  Time:     {s['wall_clock_seconds']:.1f}s")
    print("=" * 60)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze", help="snapshot current engine files")
    p_freeze.add_argument("tag")
    p_freeze.set_defaults(func=_cmd_freeze)

    p_match = sub.add_parser("match", help="paired self-play A/B match")
    p_match.add_argument("--baseline", required=True)
    p_match.add_argument("--candidate", required=True)
    p_match.add_argument("--tc", type=float, default=0.2)
    p_match.add_argument("--max-plies", type=int, default=300)
    p_match.add_argument("--max-games", type=int, default=600)
    p_match.add_argument("--workers", type=int,
                         default=max(1, (os.cpu_count() or 2) - 1))
    p_match.add_argument("--elo0", type=float, default=0.0)
    p_match.add_argument("--elo1", type=float, default=10.0)
    p_match.add_argument("--alpha", type=float, default=0.05)
    p_match.add_argument("--beta", type=float, default=0.05)
    p_match.add_argument("--seed-offset", type=int, default=0)
    p_match.add_argument("--out", default=None,
                         help="output JSON path (default: bench/results/<date>-<base>-vs-<cand>.json)")
    p_match.set_defaults(func=_cmd_match)

    p_sum = sub.add_parser("summary", help="re-print summary from a results JSON")
    p_sum.add_argument("path")
    p_sum.set_defaults(func=_cmd_summary)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
