"""M4 verification: mean_days_from_optimal and hit_rate_within_2_days on the
HELD-OUT split only — docs/12-AGENT-PROMPTS.md M4 prompt."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from cadence.core.predict.config import load_gap_term_prior, load_model_config
from cadence.core.predict.model import PredictionInputs, predict
from cadence.sim.fit_predict_weights import (
    RECOVERABLE_CAUSES,
    _customer_history_doms,
    _oracle_recovery_offset,
)
from cadence.sim.generator import generate_corpus, ground_truth_root_cause


def _held_out_recoverable_cycles(g):
    out = []
    for cyc_id in g.cycle_order:
        if g.cycle_status[cyc_id] != "FAILED":
            continue
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        if mandate.customer_id not in g.holdout_customer_ids:
            continue
        cause = ground_truth_root_cause(g.world, g.cycle_first_code, cyc_id)
        if cause not in RECOVERABLE_CAUSES:
            continue
        out.append(cyc_id)
    return out


def run_report(seed: int = 42, n_customers: int = 300) -> dict:
    g = generate_corpus(seed, n_customers=n_customers, write_to_db=False)
    cfg = load_model_config()
    gap_prior = load_gap_term_prior()

    per_segment_diffs: dict[str, list[int]] = defaultdict(list)
    all_diffs: list[int] = []

    for cyc_id in _held_out_recoverable_cycles(g):
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        customer = g.world.customers[mandate.customer_id]

        oracle_offset = _oracle_recovery_offset(
            g, cyc_id, cfg["min_cooling_off_days"], cfg["reserve_days_before_cycle_end"]
        )
        if oracle_offset is None:
            continue

        inputs = PredictionInputs(
            failure_date=cycle.debit_date,
            cycle_period_end=cycle.period_end,
            customer_successful_doms=_customer_history_doms(g, mandate.customer_id, cycle.debit_date),
            population_dom_prior=cfg["population_dom_prior"],
            gap_term_prior=gap_prior,
            issuer_success_rate_by_offset={},
            co_occurring_issuer_degradation=False,
            weights=cfg["weights"],
            min_history_successes=cfg["min_history_successes"],
            circular_gaussian_sigma_days=cfg["circular_gaussian_sigma_days"],
            min_cooling_off_days=cfg["min_cooling_off_days"],
            reserve_days_before_cycle_end=cfg["reserve_days_before_cycle_end"],
            pre_debit_notice_hours=cfg["pre_debit_notice_hours"],
        )
        result = predict(inputs)
        if result.best_day_offset is None:
            continue

        diff = abs(result.best_day_offset - oracle_offset)
        all_diffs.append(diff)
        per_segment_diffs[customer.segment].append(diff)

    mean_days_from_optimal = sum(all_diffs) / len(all_diffs) if all_diffs else float("nan")
    hit_rate_within_2 = sum(1 for d in all_diffs if d <= 2) / len(all_diffs) if all_diffs else float("nan")

    per_segment = {
        seg: {
            "n": len(diffs),
            "mean_days_from_optimal": sum(diffs) / len(diffs) if diffs else float("nan"),
            "hit_rate_within_2_days": sum(1 for d in diffs if d <= 2) / len(diffs) if diffs else float("nan"),
        }
        for seg, diffs in per_segment_diffs.items()
    }

    return {
        "n": len(all_diffs),
        "mean_days_from_optimal": mean_days_from_optimal,
        "hit_rate_within_2_days": hit_rate_within_2,
        "per_segment": per_segment,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    r = run_report(args.seed, args.n_customers)
    print(f"held-out recoverable cycles scored: {r['n']}")
    print(f"mean_days_from_optimal: {r['mean_days_from_optimal']:.2f}")
    print(f"hit_rate_within_2_days: {r['hit_rate_within_2_days']:.3f}")
    print("\nper-segment (SALARIED_MONTH_END should be comparable to SALARIED_MONTH_START):")
    for seg, stats in sorted(r["per_segment"].items()):
        print(f"  {seg:24s} n={stats['n']:4d}  mean_days_from_optimal={stats['mean_days_from_optimal']:.2f}  "
              f"hit_rate_within_2_days={stats['hit_rate_within_2_days']:.3f}")


if __name__ == "__main__":
    main()
