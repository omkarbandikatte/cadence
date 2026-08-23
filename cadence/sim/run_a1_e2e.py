"""M5 verification: run adversarial case A1 end to end and print the ledger
for that cycle. Every row must have a non-empty rationale.
See docs/12-AGENT-PROMPTS.md M5 prompt.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np

from cadence.core.classify.record import classify_and_record
from cadence.core.execute.interfaces import Adapters
from cadence.core.execute.scheduler import run_due_actions
from cadence.core.ingest.normalize import ingest_failure, observed_success_rate_for
from cadence.core.policy import decide
from cadence.db import SessionLocal
from cadence.models.tables import Ledger, Run
from cadence.sim.adapters import SimMessagingAdapter, SimPaymentLinkAdapter, SimPresentmentAdapter
from cadence.sim.clock import at_simulated_time
from cadence.sim.generator import generate_corpus


def main(seed: int = 42, n_customers: int = 300, max_days: int = 40) -> bool:
    g = generate_corpus(seed, n_customers=n_customers, write_to_db=True)
    a1_cycles = g.adversarial_cases.get("A1_LATE_MONTH_FAILURE_EARLY_MONTH_FUNDING", [])
    if not a1_cycles:
        print("no A1 case found in this corpus/seed")
        return False
    cyc_id = a1_cycles[0]
    cycle = g.world.cycles[cyc_id]
    mandate = g.world.mandates[cycle.mandate_id]
    customer_id = mandate.customer_id

    session = SessionLocal()
    try:
        run = Run(mode="AGENT", corpus_id=g.corpus_id, seed=seed, policy_config_hash="a1-e2e")
        session.add(run)
        session.flush()
        run_id = run.id

        occurred_at = at_simulated_time(cycle.debit_date)
        raw_code = g.cycle_first_code[cyc_id]
        fev = ingest_failure(
            session, mandate_id=cycle.mandate_id, cycle_id=cyc_id, customer_id=customer_id, attempt_no=1,
            occurred_at=occurred_at, amount_paise=cycle.amount_paise, raw_code=raw_code, gateway_desc=None, run_id=run_id,
        )
        observed_rate = observed_success_rate_for(session, customer_id, cycle.debit_date)
        classify_and_record(session, failure_event=fev, gateway_desc=None, observed_success_rate=observed_rate, run_id=run_id)
        session.commit()

        decide(session, failure_event=fev, run_id=run_id, now=occurred_at)
        session.commit()

        adapters = Adapters(
            presentment=SimPresentmentAdapter(g.world, np.random.default_rng(0)),
            messaging=SimMessagingAdapter(),
            payment_link=SimPaymentLinkAdapter(np.random.default_rng(1)),
        )

        now = occurred_at
        for _ in range(max_days):
            now = now + timedelta(days=1)
            run_due_actions(session, now=now, run_id=run_id, adapters=adapters)
            session.commit()

        rows = (
            session.query(Ledger)
            .filter(Ledger.run_id == run_id, Ledger.cycle_id == cyc_id)
            .order_by(Ledger.id)
            .all()
        )
        print(f"cycle {cyc_id}  customer {customer_id}  amount {cycle.amount_paise}p  debit_date {cycle.debit_date}")
        print(f"{len(rows)} ledger rows:\n")
        all_have_rationale = True
        for row in rows:
            ok = bool(row.rationale and row.rationale.strip())
            all_have_rationale = all_have_rationale and ok
            print(f"  [{row.occurred_at.date()}] {row.event_type:20s} {row.rationale}")
        print(f"\nevery row has a non-empty rationale: {all_have_rationale}")
        return all_have_rationale
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    ok = main(args.seed, args.n_customers)
    sys.exit(0 if ok else 1)
