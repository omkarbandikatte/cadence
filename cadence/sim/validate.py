"""Validation checks V1-V4 from docs/07-SYNTHETIC-DATA.md — run before trusting
a single downstream result. See docs/14-RISK-REGISTER.md R1/R2.
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys
from collections import defaultdict
from datetime import timedelta

import numpy as np
import yaml

from cadence.sim import bank
from cadence.sim.generator import generate_corpus

TERMINAL_CODES = {"MANDATE_EXPIRED", "MANDATE_REVOKED", "AMOUNT_EXCEEDS_MANDATE"}
TERMINAL_DESIGNED_CAUSES = {"INSTRUMENT_DEFECT", "RISK_BLOCK", "UNKNOWN"}

BASELINE_RETRY_OFFSETS_DAYS = (1, 3, 5)  # PRODUCT_CHOICE, matches today's status quo per docs/01-PRD.md

FORBIDDEN_PATTERNS = [
    r"funding_calendar",
    r"is_outage",
    r"\.segment\b",
    r"from cadence\.sim\.bank",
    r"from cadence\.sim import bank",
    r"import cadence\.sim\.bank",
]


def _load_constants() -> dict:
    config_path = pathlib.Path(__file__).resolve().parents[1] / "config" / "policy.yaml"
    with open(config_path) as f:
        policy = yaml.safe_load(f)
    return {k: v["value"] for k, v in policy["constants"].items() if isinstance(v, dict) and "value" in v}


def _fresh_world(g) -> bank.World:
    return bank.World(
        customers=g.world.customers,
        mandates=g.world.mandates,
        cycles=g.world.cycles,
        funding_calendar=copy.deepcopy(g.world.funding_calendar),
        issuer_days=g.world.issuer_days,
        designed_causes=g.world.designed_causes,
    )


def _is_terminal(g, cyc_id: str) -> bool:
    code = g.cycle_first_code[cyc_id]
    if code in TERMINAL_CODES:
        return True
    designed = g.world.designed_causes.get(cyc_id)
    return designed is not None and designed.root_cause in TERMINAL_DESIGNED_CAUSES


def run_oracle(g, constants: dict) -> dict:
    """Perfect-information policy: reads funding_calendar/issuer outages
    directly and presents on the best feasible day. Skips terminal cases."""
    world = _fresh_world(g)
    rng = np.random.default_rng(0)
    min_cooling_off = constants["min_cooling_off_days"]
    reserve_days = constants["reserve_days_before_cycle_end"]

    recovered = 0
    total_failed = 0
    for cyc_id in g.cycle_order:
        if g.cycle_status[cyc_id] != "FAILED":
            continue
        total_failed += 1
        if _is_terminal(g, cyc_id):
            continue

        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        customer = world.customers[mandate.customer_id]
        start = cycle.debit_date + timedelta(days=min_cooling_off)
        end = cycle.period_end - timedelta(days=reserve_days)

        chosen = None
        d = start
        while d <= end:
            balance = world.funding_calendar[mandate.customer_id].get(d, 0)
            outage = world.issuer_days.get((customer.issuer_code, d))
            if balance >= cycle.amount_paise and not (outage and outage.is_outage):
                chosen = d
                break
            d += timedelta(days=1)

        if chosen is not None:
            result = bank.resolve(world, cyc_id, chosen, attempt_no=2, rng=rng)
            if result.succeeded:
                bank.apply_debit(world, mandate.customer_id, chosen, cycle.amount_paise)
                recovered += 1

    return {
        "recovered": recovered,
        "total_failed": total_failed,
        "recovery_rate": recovered / total_failed if total_failed else 0.0,
    }


def run_baseline(g, constants: dict) -> dict:
    """Fixed-interval T+1/T+3/T+5 retry, no classification, no gate, capped."""
    world = _fresh_world(g)
    rng = np.random.default_rng(1)
    max_retries = constants["max_presentations_per_cycle"]

    recovered = 0
    total_failed = 0
    for cyc_id in g.cycle_order:
        if g.cycle_status[cyc_id] != "FAILED":
            continue
        total_failed += 1

        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        for attempt_idx, offset in enumerate(BASELINE_RETRY_OFFSETS_DAYS[:max_retries], start=2):
            attempt_date = cycle.debit_date + timedelta(days=offset)
            if attempt_date > cycle.period_end:
                break
            result = bank.resolve(world, cyc_id, attempt_date, attempt_no=attempt_idx, rng=rng)
            if result.succeeded:
                bank.apply_debit(world, mandate.customer_id, attempt_date, cycle.amount_paise)
                recovered += 1
                break

    return {
        "recovered": recovered,
        "total_failed": total_failed,
        "recovery_rate": recovered / total_failed if total_failed else 0.0,
    }


def signal_audit(g) -> dict:
    """V3: day-of-month success-rate peak for SALARIED_* segments."""
    results = {}
    for seg in ("SALARIED_MONTH_START", "SALARIED_MONTH_END"):
        cust_ids = [cid for cid, s in g.customer_segment.items() if s == seg]
        ref_amount = 49900  # a representative mid-tier subscription amount, paise
        day_hits: dict[int, int] = defaultdict(int)
        day_total: dict[int, int] = defaultdict(int)
        for cid in cust_ids:
            for d, balance in g.world.funding_calendar[cid].items():
                day_total[d.day] += 1
                if balance >= ref_amount:
                    day_hits[d.day] += 1
        rates = {dom: day_hits[dom] / day_total[dom] for dom in day_total}
        max_rate = max(rates.values())
        mean_rate = sum(rates.values()) / len(rates)
        results[seg] = {
            "max_rate": round(max_rate, 3),
            "mean_rate": round(mean_rate, 3),
            "peak_day": max(rates, key=rates.get),
            "clear_peak": (max_rate - mean_rate) >= 0.15,
        }
    return results


def find_leakage(core_dir: pathlib.Path | None = None) -> list[tuple[str, str]]:
    """V4: core/ must never reference generator-only ground truth."""
    if core_dir is None:
        core_dir = pathlib.Path(__file__).resolve().parents[1] / "core"
    hits = []
    for f in core_dir.rglob("*.py"):
        text = f.read_text()
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, text):
                hits.append((str(f), pat))
    return hits


def validate(seed: int = 42, n_customers: int = 300) -> bool:
    constants = _load_constants()
    g = generate_corpus(seed, n_customers=n_customers, write_to_db=False)

    n_failed = sum(1 for s in g.cycle_status.values() if s == "FAILED")
    print(f"corpus: {g.n_customers} customers, {len(g.mandate_customer)} mandates, "
          f"{len(g.cycle_status)} cycles, {n_failed} failed")
    print(f"cause_mix (realized): {g.cause_mix}")

    oracle = run_oracle(g, constants)
    baseline = run_baseline(g, constants)
    v1_pass = 0.75 <= oracle["recovery_rate"] <= 0.85
    v2_pass = baseline["recovery_rate"] < oracle["recovery_rate"] - 0.10

    print(f"\nV1 oracle:   recovered {oracle['recovered']}/{oracle['total_failed']} "
          f"= {oracle['recovery_rate']:.3f}  -> {'PASS' if v1_pass else 'FAIL'} (target 0.75-0.85)")
    print(f"V2 baseline: recovered {baseline['recovered']}/{baseline['total_failed']} "
          f"= {baseline['recovery_rate']:.3f}  -> {'PASS' if v2_pass else 'FAIL'} "
          f"(must be clearly below oracle)")

    audit = signal_audit(g)
    v3_pass = all(seg["clear_peak"] for seg in audit.values())
    print("\nV3 signal audit (day-of-month success rate):")
    for seg, r in audit.items():
        print(f"  {seg}: peak day {r['peak_day']} rate={r['max_rate']} mean={r['mean_rate']} "
              f"-> {'PASS' if r['clear_peak'] else 'FAIL'}")

    leaks = find_leakage()
    v4_pass = len(leaks) == 0
    print(f"\nV4 leakage grep: {'PASS, no hits' if v4_pass else f'FAIL, hits: {leaks}'}")

    all_pass = v1_pass and v2_pass and v3_pass and v4_pass
    print(f"\n{'ALL CHECKS PASS' if all_pass else 'VALIDATION FAILED'}")
    return all_pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    ok = validate(args.seed, args.n_customers)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
