"""Fits gap_term.yaml and the model_weights block of policy.yaml — TRAIN split
only, never held-out. Lives in sim/ (not core/) because fitting needs ground
truth; core/predict only ever reads the frozen config these scripts produce.
See docs/05-DECISION-ENGINE.md Part A "Tuning the weights".
"""
from __future__ import annotations

import itertools
from datetime import timedelta

import yaml

from cadence.core.predict.config import GAP_TERM_PATH, MODEL_WEIGHTS_PATH, POLICY_PATH
from cadence.core.predict.model import PredictionInputs, predict
from cadence.sim.generator import generate_corpus, ground_truth_root_cause

RECOVERABLE_CAUSES = {"BALANCE_SHORTFALL", "ISSUER_DEGRADED"}


def _train_recoverable_cycles(g):
    out = []
    for cyc_id in g.cycle_order:
        if g.cycle_status[cyc_id] != "FAILED":
            continue
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        if mandate.customer_id not in g.train_customer_ids:
            continue
        cause = ground_truth_root_cause(g.world, g.cycle_first_code, cyc_id)
        if cause not in RECOVERABLE_CAUSES:
            continue
        out.append(cyc_id)
    return out


def _oracle_recovery_offset(g, cyc_id, min_cooling_off: int, reserve_days: int, max_offset: int = 14) -> int | None:
    """Best day within the model's own 15-day horizon (day_offset 0..14) —
    not the full cycle window, so this is a fair comparison for
    predict_report.py. sim/validate.py's oracle (V1 ceiling) is a different,
    intentionally unconstrained perfect-information policy."""
    cycle = g.world.cycles[cyc_id]
    mandate = g.world.mandates[cycle.mandate_id]
    start = cycle.debit_date + timedelta(days=min_cooling_off)
    end = min(cycle.period_end - timedelta(days=reserve_days), cycle.debit_date + timedelta(days=max_offset))
    d = start
    while d <= end:
        balance = g.world.funding_calendar[mandate.customer_id].get(d, 0)
        if balance >= cycle.amount_paise:
            return (d - cycle.debit_date).days
        d += timedelta(days=1)
    return None


def fit_gap_term(g, min_cooling_off: int, reserve_days: int) -> tuple[float, ...]:
    counts = [0.0] * 15
    for cyc_id in _train_recoverable_cycles(g):
        offset = _oracle_recovery_offset(g, cyc_id, min_cooling_off, reserve_days)
        if offset is None:
            continue
        counts[min(offset, 14)] += 1
    total = sum(counts)
    if total == 0:
        return tuple(1 / 15 for _ in range(15))
    return tuple(c / total for c in counts)


def _customer_history_doms(g, customer_id: str, before_date) -> tuple[int, ...]:
    doms = []
    for cyc_id in g.cycle_order:
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        if mandate.customer_id != customer_id:
            continue
        if cycle.debit_date >= before_date:
            continue
        if g.cycle_status[cyc_id] == "SUCCESS":
            doms.append(cycle.debit_date.day)
    return tuple(doms)


def _score_weights(g, cycles, weights, gap_prior, min_cooling_off, reserve_days, notice_hours, population_prior):
    hits = 0
    total = 0
    for cyc_id in cycles:
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        customer_id = mandate.customer_id
        inputs = PredictionInputs(
            failure_date=cycle.debit_date,
            cycle_period_end=cycle.period_end,
            customer_successful_doms=_customer_history_doms(g, customer_id, cycle.debit_date),
            population_dom_prior=population_prior,
            gap_term_prior=gap_prior,
            issuer_success_rate_by_offset={},
            co_occurring_issuer_degradation=False,
            weights=weights,
            min_history_successes=3,
            circular_gaussian_sigma_days=1.5,
            min_cooling_off_days=min_cooling_off,
            reserve_days_before_cycle_end=reserve_days,
            pre_debit_notice_hours=notice_hours,
        )
        result = predict(inputs)
        if result.best_day_offset is None:
            continue
        total += 1
        target_date = cycle.debit_date + timedelta(days=result.best_day_offset)
        balance = g.world.funding_calendar[customer_id].get(target_date, 0)
        if balance >= cycle.amount_paise:
            hits += 1
    return (hits / total) if total else 0.0


def fit(seed: int = 42, n_customers: int = 300) -> dict:
    g = generate_corpus(seed, n_customers=n_customers, write_to_db=False)

    with open(POLICY_PATH) as f:
        policy = yaml.safe_load(f)
    constants = {k: v["value"] for k, v in policy["constants"].items() if isinstance(v, dict) and "value" in v}
    min_cooling_off = constants["min_cooling_off_days"]
    reserve_days = constants["reserve_days_before_cycle_end"]
    notice_hours = constants["pre_debit_notice_hours"]
    population_prior = tuple(policy["population_dom_prior"])

    gap_prior = fit_gap_term(g, min_cooling_off, reserve_days)
    with open(GAP_TERM_PATH, "w") as f:
        yaml.safe_dump({"gap_term_prior": [round(x, 5) for x in gap_prior]}, f, default_flow_style=None)

    train_cycles = _train_recoverable_cycles(g)
    candidates = [
        {"w_cust": wc, "w_pop": wp, "w_gap": 1.0, "w_iss": 1.0, "w_pen": wpen}
        for wc, wp, wpen in itertools.product([0.5, 1.0, 1.5], [0.3, 0.6, 1.0], [0.5, 1.0, 1.5])
    ]
    best_weights = None
    best_score = -1.0
    for weights in candidates:
        s = _score_weights(g, train_cycles, weights, gap_prior, min_cooling_off, reserve_days, notice_hours, population_prior)
        if s > best_score:
            best_score = s
            best_weights = weights

    with open(MODEL_WEIGHTS_PATH) as f:
        model_weights = yaml.safe_load(f)
    model_weights.update(best_weights)
    with open(MODEL_WEIGHTS_PATH, "w") as f:
        yaml.safe_dump(model_weights, f, default_flow_style=False, sort_keys=False)

    return {"gap_term_prior": gap_prior, "weights": best_weights, "train_hit_rate": best_score, "n_train_cycles": len(train_cycles)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    result = fit(args.seed, args.n_customers)
    print(f"fit on {result['n_train_cycles']} train cycles")
    print(f"weights: {result['weights']}")
    print(f"train hit rate (predicted day has sufficient balance): {result['train_hit_rate']:.3f}")
    print(f"gap_term_prior written to {GAP_TERM_PATH}")


if __name__ == "__main__":
    main()
