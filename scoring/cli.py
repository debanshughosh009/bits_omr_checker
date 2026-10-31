#!/usr/bin/env python3
"""
cli.py – Headless scoring CLI.

Usage:
    python scoring/cli.py \\
        --results output/results.csv \\
        --keys scoring/keys/quiz1.json \\
        --out output/score.csv \\
        --scheme 4,-1,0 \\
        --multi zero \\
        [--per-question]

Run from the repository root.
"""

import argparse
import sys
from pathlib import Path

# Allow running as ``python scoring/cli.py`` from the repo root.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scoring.scorer import parse_scheme, validate_key, score_all, VALID_MULTI_POLICIES
from scoring.io_utils import (
    read_results, load_key, key_file_hash,
    write_score, write_run_json,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Score results.csv using an answer key."
    )
    parser.add_argument(
        "--results", default="output/results.csv",
        help="Path to results.csv (default: output/results.csv)",
    )
    parser.add_argument(
        "--keys", required=True,
        help="Path to answer-key JSON file.",
    )
    parser.add_argument(
        "--out", default="output/score.csv",
        help="Output path for score.csv (default: output/score.csv)",
    )
    parser.add_argument(
        "--scheme", default="4,-1,0",
        help=(
            "Marking scheme as correct,wrong,unattempted "
            "(default: 4,-1,0). Examples: 1,0,0  3,-1,0  2,-0.5,0"
        ),
    )
    parser.add_argument(
        "--multi", default="zero", choices=VALID_MULTI_POLICIES,
        help="Multi-mark policy (default: zero).",
    )
    parser.add_argument(
        "--per-question", action="store_true",
        help="Include per-question mark columns in the output.",
    )
    args = parser.parse_args(argv)

    # Parse scheme
    parts = args.scheme.split(",")
    if len(parts) != 3:
        parser.error("--scheme must be three comma-separated numbers.")
    mc, mw, mu = parse_scheme(parts[0].strip(), parts[1].strip(),
                              parts[2].strip())

    # Load data
    print(f"Reading {args.results} …")
    rows, q_columns, header = read_results(args.results)
    print(f"  {len(rows)} rows, {len(q_columns)} questions")

    # Load key
    key_data = load_key(args.keys)
    num_q = len(q_columns)
    options = key_data.get("options", "ABCD")
    if key_data["questions"] != num_q:
        sys.exit(
            f"ERROR: Key file has {key_data['questions']} questions "
            f"but results.csv has {num_q}."
        )
    keys_by_set = {}
    for s, kl in key_data["sets"].items():
        validate_key(kl, num_q, options)
        keys_by_set[s.upper()] = kl

    sets_in_data = sorted({r.get("Set", "").strip().upper()
                           for r in rows} - {""})
    for s in sets_in_data:
        if s not in keys_by_set:
            print(f"  WARNING: Set '{s}' found in data but no key provided.")

    # Score
    scored = score_all(
        rows, keys_by_set, mc, mw, mu, args.multi, q_columns,
        options=options, per_question=args.per_question,
    )

    # Write
    out = write_score(args.out, scored, q_columns,
                      per_question=args.per_question)
    print(f"Wrote {out}  ({len(scored)} rows)")

    kh = key_file_hash(args.keys)
    run_json = write_run_json(
        args.out, (mc, mw, mu), args.multi, args.keys, kh,
        len(rows), per_question=args.per_question,
    )
    print(f"Wrote {run_json}")


if __name__ == "__main__":
    main()

