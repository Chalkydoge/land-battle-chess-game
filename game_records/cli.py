"""Command line tools for game records."""

import argparse
import json
import sys

from game_records.analyze import analyze_games
from game_records.jsonl import iter_record_paths
from game_records.samples import iter_samples


def _cmd_analyze(args):
    paths = list(iter_record_paths(args.root, args.mode))
    if not paths:
        print(f"no record files found under {args.root}/{args.mode}", file=sys.stderr)
        return 1

    report = analyze_games(
        paths,
        game_id=args.game_id,
        min_drop=args.min_drop,
        mate_threshold=args.mate_threshold,
        terminal_window=args.window,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0


def _cmd_export_samples(args):
    paths = list(iter_record_paths(args.root, args.mode))
    if not paths:
        print(f"no record files found under {args.root}/{args.mode}", file=sys.stderr)
        return 1

    sample_types = _sample_types(args.kind)
    samples = iter_samples(
        paths,
        sample_types=sample_types,
        include_unfinished=args.include_unfinished,
        with_features=not args.no_features,
    )

    count = 0
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for sample in samples:
                if args.game_id and sample.get("game_id") != args.game_id:
                    continue
                f.write(json.dumps(sample, ensure_ascii=True, separators=(",", ":")) + "\n")
                count += 1
        print(f"wrote {count} samples to {args.out}")
    else:
        for sample in samples:
            if args.game_id and sample.get("game_id") != args.game_id:
                continue
            print(json.dumps(sample, ensure_ascii=False, separators=(",", ":")))
            count += 1
    if count == 0:
        print("no samples exported", file=sys.stderr)
        return 1
    return 0


def _print_report(report):
    print("=" * 72)
    print("Open Game Record Analysis")
    print("=" * 72)
    for game in report["games"]:
        result = game["result"] or {"winner": None, "reason": "unfinished", "plies": game["plies"]}
        ai = game["ai"]
        print(
            f"{game['game_id']}  complete={game['complete']}  "
            f"winner={result.get('winner')}  reason={result.get('reason')}  "
            f"plies={result.get('plies', game['plies'])}"
        )
        print(
            f"  ai_moves={ai['moves']}  score=[{ai['score_min']}, {ai['score_max']}]  "
            f"avg_depth={ai['avg_depth']:.2f}  timeouts={ai['timeouts']}"
        )
        terminal_window = game.get("terminal_window", [])
        if terminal_window:
            print("  terminal_window:")
            for item in terminal_window:
                move = item["move"]
                score = "" if "score" not in item else f" score={item['score']}"
                target = "" if item["target"] is None else f" x {item['target']}"
                print(
                    f"    ply {item['ply']:>3} {item['side']} "
                    f"{item['piece']} {move['from']}->{move['to']}{target}{score}"
                )

    critical = report["critical_positions"]
    print("-" * 72)
    print(f"Critical AI positions: {len(critical)}")
    for item in critical:
        reasons = ",".join(item["reasons"])
        print(
            f"  {item['game_id']} ply={item['ply']} reasons={reasons} "
            f"score={item['score']} prev={item['previous_score']} "
            f"drop={item['drop']} depth={item['completed_depth']} "
            f"key={item['position_key_before']}"
        )
        move = item["move"]
        print(f"    move={move} line={item['source_line']} file={item['source_path']}")


def _sample_types(kind):
    if kind == "all":
        return None
    return {kind.replace("-", "_")}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m game_records.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze = sub.add_parser("analyze", help="analyze open-game JSONL records")
    analyze.add_argument("--root", default="records")
    analyze.add_argument("--mode", default="open")
    analyze.add_argument("--game-id", default=None)
    analyze.add_argument("--min-drop", type=int, default=200)
    analyze.add_argument("--mate-threshold", type=int, default=90000)
    analyze.add_argument("--window", type=int, default=10)
    analyze.add_argument("--json", action="store_true", help="print machine-readable JSON")
    analyze.set_defaults(func=_cmd_analyze)

    samples = sub.add_parser("export-samples", help="export policy/search/value samples as JSONL")
    samples.add_argument("--root", default="records")
    samples.add_argument("--mode", default="open")
    samples.add_argument("--game-id", default=None)
    samples.add_argument(
        "--kind",
        choices=["all", "human-policy", "ai-search", "value"],
        default="all",
    )
    samples.add_argument("--out", default=None, help="output JSONL path; stdout when omitted")
    samples.add_argument("--include-unfinished", action="store_true")
    samples.add_argument("--no-features", action="store_true")
    samples.set_defaults(func=_cmd_export_samples)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
