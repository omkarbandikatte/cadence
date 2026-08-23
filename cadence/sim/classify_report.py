"""M2 verification: score core/classify's classifier against generator ground
truth. Lives in sim/, not core/ — it needs ground truth to score against."""
from __future__ import annotations

import sys
from collections import defaultdict

from cadence.core.classify.classifier import classify
from cadence.sim.generator import ground_truth_root_cause, generate_corpus

ROOT_CAUSES = [
    "BALANCE_SHORTFALL",
    "ISSUER_DEGRADED",
    "TECHNICAL_TRANSIENT",
    "MANDATE_DEFECT",
    "INSTRUMENT_DEFECT",
    "RISK_BLOCK",
    "UNKNOWN",
]


def run_report(seed: int = 42, n_customers: int = 300) -> dict:
    g = generate_corpus(seed, n_customers=n_customers, write_to_db=False)

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cyc_id in g.cycle_order:
        if g.cycle_status[cyc_id] != "FAILED":
            continue
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        customer = g.world.customers[mandate.customer_id]
        truth = ground_truth_root_cause(g.world, g.cycle_first_code, cyc_id)

        designed = g.world.designed_causes.get(cyc_id)
        gateway_desc = designed.gateway_desc if designed else None
        issuer_day = g.world.issuer_days.get((customer.issuer_code, cycle.debit_date))
        observed_rate = issuer_day.observed_success_rate if issuer_day else None

        result = classify(g.cycle_first_code[cyc_id], gateway_desc, observed_rate)
        confusion[truth][result.root_cause] += 1

    return dict(confusion)


def print_report(confusion: dict) -> None:
    labels = sorted(set(confusion) | {p for row in confusion.values() for p in row})
    print("confusion matrix (rows=truth, cols=predicted):")
    header = "truth\\pred".ljust(20) + "".join(l[:10].ljust(12) for l in labels)
    print(header)
    for truth in labels:
        row = confusion.get(truth, {})
        line = truth.ljust(20) + "".join(str(row.get(p, 0)).ljust(12) for p in labels)
        print(line)

    print("\nper-cause precision / recall:")
    for cause in labels:
        tp = confusion.get(cause, {}).get(cause, 0)
        fn = sum(v for p, v in confusion.get(cause, {}).items() if p != cause)
        fp = sum(confusion.get(t, {}).get(cause, 0) for t in labels if t != cause)
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        print(f"  {cause:22s} precision={precision:.3f}  recall={recall:.3f}  (n={tp+fn})")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    confusion = run_report(args.seed, args.n_customers)
    print_report(confusion)


if __name__ == "__main__":
    main()
