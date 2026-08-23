"""CLI: `make report SEED=42` — 5-seed run, bootstrap CI, HTML report."""
from __future__ import annotations

import argparse

from cadence.eval.report import generate_html_report, print_multi_seed_summary, run_multi_seed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    parser.add_argument("--n-seeds", type=int, default=5)
    args = parser.parse_args()

    seeds = [args.seed + i for i in range(args.n_seeds)]
    summary = run_multi_seed(seeds, args.n_customers)
    print_multi_seed_summary(summary)
    path = generate_html_report(summary)
    print(f"\nreport written to {path}")


if __name__ == "__main__":
    main()
