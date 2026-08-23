"""CLI: `make eval SEED=42` — one seed, three arms, printed comparison table."""
from __future__ import annotations

import argparse

from cadence.eval.report import print_comparison_table, run_all_arms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    result = run_all_arms(args.seed, args.n_customers)
    print_comparison_table(result)


if __name__ == "__main__":
    main()
