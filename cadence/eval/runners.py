"""Three arms, one world — docs/10-EVALUATION.md.

BASELINE: fixed T+1/T+3/T+5 retry + a dunning message per failure, no
classification, no gate, no link fallback, still stops at the presentation
cap (a real rail constraint, not optional). Bypasses core/policy and
core/compliance entirely, by design — it's supposed to be what a merchant
does today, not the compliant system.

AGENT: the real thing — core/ingest -> classify -> predict -> policy ->
compliance -> execute, driven day by day exactly like sim/run_a1_e2e.py, just
over the whole corpus.

ORACLE: perfect information, reads funding_calendar directly, skips terminal
cases. The ceiling.

Each arm gets its own deep-copied World so presentments in one arm never
deduct balance the others can see — they must never get a friendlier world
than each other. See docs/02-ARCHITECTURE.md.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from cadence.core.classify.record import classify_and_record
from cadence.core.compliance.config import load_policy_constants
from cadence.core.execute.interfaces import Adapters
from cadence.core.execute.scheduler import run_due_actions
from cadence.core.ingest.normalize import ingest_failure, ingest_success, observed_success_rate_for
from cadence.core.ledger import writer as ledger
from cadence.core.policy import decide
from cadence.models.tables import Attempt, Cycle, Mandate, Message, Run
from cadence.sim import bank
from cadence.sim.adapters import SimMessagingAdapter, SimPaymentLinkAdapter, SimPresentmentAdapter
from cadence.sim.clock import at_simulated_time
from cadence.sim.generator import generate_corpus, ground_truth_root_cause

EXTRA_DAYS = 35  # buffer past the corpus's own DAYS so in-flight recoveries can finish
BASELINE_RETRY_OFFSETS = (1, 3, 5)
TERMINAL_CAUSES = {"MANDATE_DEFECT", "INSTRUMENT_DEFECT", "RISK_BLOCK", "UNKNOWN"}


@dataclass
class ArmResult:
    run_id: str
    mode: str
    corpus_id: str
    seed: int


def _fresh_world(g) -> bank.World:
    return bank.World(
        customers=g.world.customers,
        mandates=g.world.mandates,
        cycles=g.world.cycles,
        funding_calendar=copy.deepcopy(g.world.funding_calendar),
        issuer_days=g.world.issuer_days,
        designed_causes=g.world.designed_causes,
    )


def _cycles_by_debit_date(g):
    by_date: dict = {}
    for cyc_id in g.cycle_order:
        by_date.setdefault(g.world.cycles[cyc_id].debit_date, []).append(cyc_id)
    return by_date


def _date_range(g):
    from cadence.sim.generator import DAYS, START_DATE

    return START_DATE, START_DATE + timedelta(days=DAYS + EXTRA_DAYS)


def load_corpus(seed: int, n_customers: int = 300):
    return generate_corpus(seed, n_customers=n_customers, write_to_db=False)


def _create_run(session, *, mode: str, corpus_id: str, seed: int) -> Run:
    run = Run(mode=mode, corpus_id=corpus_id, seed=seed, policy_config_hash=f"{mode.lower()}-v1")
    session.add(run)
    session.flush()
    return run


def reset_cycles(session, g) -> None:
    """cycles/mandates/customers have no run_id column — they're the shared
    world, not per-run. Each arm must start from the same untouched state
    (the natural first-attempt outcome), or arms run after the first would
    inherit the previous arm's mutations (presentations_used, state, ...).
    Must be called before each arm's run."""
    for cyc_id in g.cycle_order:
        cycle_row = session.get(Cycle, cyc_id)
        cycle_row.presentations_used = 1
        cycle_row.state = "RECOVERED" if g.cycle_status[cyc_id] == "SUCCESS" else "IN_RECOVERY"
        cycle_row.recovered_at = None
        cycle_row.recovered_via = None
        cycle_row.recovered_amount_paise = None
    session.commit()


def run_agent(session, g, seed: int) -> ArmResult:
    reset_cycles(session, g)
    run = _create_run(session, mode="AGENT", corpus_id=g.corpus_id, seed=seed)
    world = _fresh_world(g)
    rng_present = np.random.default_rng(seed * 10 + 1)
    rng_link = np.random.default_rng(seed * 10 + 2)
    adapters = Adapters(
        presentment=SimPresentmentAdapter(world, rng_present),
        messaging=SimMessagingAdapter(),
        payment_link=SimPaymentLinkAdapter(rng_link),
    )
    by_date = _cycles_by_debit_date(g)
    start, end = _date_range(g)

    day = start
    while day <= end:
        now = at_simulated_time(day)
        for cyc_id in by_date.get(day, []):
            cycle = world.cycles[cyc_id]
            mandate = world.mandates[cycle.mandate_id]
            if g.cycle_status[cyc_id] == "SUCCESS":
                ingest_success(session, cycle_id=cyc_id, attempt_no=1, presented_at=now, amount_paise=cycle.amount_paise, run_id=run.id)
            else:
                raw_code = g.cycle_first_code[cyc_id]
                designed = world.designed_causes.get(cyc_id)
                gateway_desc = designed.gateway_desc if designed else None
                fev = ingest_failure(
                    session, mandate_id=cycle.mandate_id, cycle_id=cyc_id, customer_id=mandate.customer_id,
                    attempt_no=1, occurred_at=now, amount_paise=cycle.amount_paise, raw_code=raw_code,
                    gateway_desc=gateway_desc, run_id=run.id,
                )
                observed_rate = observed_success_rate_for(session, mandate.customer_id, day)
                classify_and_record(session, failure_event=fev, gateway_desc=gateway_desc, observed_success_rate=observed_rate, run_id=run.id)
                decide(session, failure_event=fev, run_id=run.id, now=now)
        run_due_actions(session, now=now, run_id=run.id, adapters=adapters)
        session.commit()
        day += timedelta(days=1)

    return ArmResult(run_id=run.id, mode="AGENT", corpus_id=g.corpus_id, seed=seed)


def run_baseline(session, g, seed: int) -> ArmResult:
    reset_cycles(session, g)
    run = _create_run(session, mode="BASELINE", corpus_id=g.corpus_id, seed=seed)
    world = _fresh_world(g)
    rng = np.random.default_rng(seed * 10 + 3)
    constants = load_policy_constants()
    max_presentations = constants.value("max_presentations_per_cycle")
    by_date = _cycles_by_debit_date(g)
    start, end = _date_range(g)

    # cycle_id -> list of pending retry dates still owed
    pending_retries: dict[str, list] = {}

    day = start
    while day <= end:
        now = at_simulated_time(day)

        for cyc_id in by_date.get(day, []):
            cycle = world.cycles[cyc_id]
            mandate = world.mandates[cycle.mandate_id]
            if g.cycle_status[cyc_id] == "SUCCESS":
                ingest_success(session, cycle_id=cyc_id, attempt_no=1, presented_at=now, amount_paise=cycle.amount_paise, run_id=run.id)
            else:
                raw_code = g.cycle_first_code[cyc_id]
                designed = world.designed_causes.get(cyc_id)
                gateway_desc = designed.gateway_desc if designed else None
                ingest_failure(
                    session, mandate_id=cycle.mandate_id, cycle_id=cyc_id, customer_id=mandate.customer_id,
                    attempt_no=1, occurred_at=now, amount_paise=cycle.amount_paise, raw_code=raw_code,
                    gateway_desc=gateway_desc, run_id=run.id,
                )
                _send_dunning(session, cycle_id=cyc_id, mandate_id=cycle.mandate_id, customer_id=mandate.customer_id, amount_paise=cycle.amount_paise, run_id=run.id, now=now)
                pending_retries[cyc_id] = [cycle.debit_date + timedelta(days=o) for o in BASELINE_RETRY_OFFSETS]

        for cyc_id, retry_dates in list(pending_retries.items()):
            if not retry_dates or retry_dates[0] != day:
                continue
            retry_dates.pop(0)
            cycle_row = session.get(Cycle, cyc_id)
            if cycle_row.state == "RECOVERED" or cycle_row.presentations_used >= max_presentations:
                pending_retries.pop(cyc_id, None)
                continue
            mandate_row = session.get(Mandate, cycle_row.mandate_id)
            attempt_no = cycle_row.presentations_used + 1
            result = bank.resolve(world, cyc_id, day, attempt_no, rng)
            cycle_row.presentations_used = attempt_no
            attempt = Attempt(
                cycle_id=cyc_id, attempt_no=attempt_no, presented_at=now, succeeded=result.succeeded,
                gateway_code=result.gateway_code, gateway_desc=result.gateway_desc, run_id=run.id,
            )
            session.add(attempt)
            session.flush()
            ledger.record(
                session, event_type="PRESENTMENT_SENT", run_id=run.id, occurred_at=now,
                rationale=f"Baseline fixed-interval retry, attempt {attempt_no}.",
                payload={"attempt_no": attempt_no}, cycle_id=cyc_id, mandate_id=mandate_row.id,
                customer_id=mandate_row.customer_id, amount_paise=cycle_row.amount_paise,
            )
            if result.succeeded:
                bank.apply_debit(world, mandate_row.customer_id, day, cycle_row.amount_paise)
                cycle_row.state = "RECOVERED"
                cycle_row.recovered_at = now
                cycle_row.recovered_via = "PRESENTMENT"
                cycle_row.recovered_amount_paise = cycle_row.amount_paise
                session.flush()
                ledger.record(
                    session, event_type="RECOVERED", run_id=run.id, occurred_at=now,
                    rationale=f"Baseline recovered {cycle_row.amount_paise} paise on attempt {attempt_no}.",
                    payload={"attempt_no": attempt_no}, cycle_id=cyc_id, mandate_id=mandate_row.id,
                    customer_id=mandate_row.customer_id, amount_paise=cycle_row.amount_paise,
                )
                pending_retries.pop(cyc_id, None)
            else:
                _send_dunning(session, cycle_id=cycle_row.id, mandate_id=mandate_row.id, customer_id=mandate_row.customer_id, amount_paise=cycle_row.amount_paise, run_id=run.id, now=now)
        session.commit()
        day += timedelta(days=1)

    return ArmResult(run_id=run.id, mode="BASELINE", corpus_id=g.corpus_id, seed=seed)


def _send_dunning(session, *, cycle_id: str, mandate_id: str, customer_id: str, amount_paise: int, run_id: str, now) -> None:
    from cadence.models.tables import ContactLog

    variables = {"amount": f"{amount_paise / 100:,.2f}"}
    message = Message(
        customer_id=customer_id, cycle_id=cycle_id, channel="EMAIL", template_key="dunning_generic",
        variables=variables, body_rendered=f"Your payment of Rs {variables['amount']} failed. We'll retry.",
        sent_at=now, suppressed=False, run_id=run_id,
    )
    session.add(message)
    session.add(ContactLog(customer_id=customer_id, sent_at=now, channel="EMAIL", run_id=run_id))
    session.flush()
    ledger.record(
        session, event_type="MESSAGE_SENT", run_id=run_id, occurred_at=now,
        rationale="Baseline sent a generic dunning message on failure.", payload={"template_key": "dunning_generic"},
        cycle_id=cycle_id, mandate_id=mandate_id, customer_id=customer_id, channel="EMAIL",
    )


def run_oracle(session, g, seed: int) -> ArmResult:
    reset_cycles(session, g)
    run = _create_run(session, mode="ORACLE", corpus_id=g.corpus_id, seed=seed)
    world = _fresh_world(g)
    constants = load_policy_constants()
    min_cooling_off = constants.value("min_cooling_off_days")
    reserve_days = constants.value("reserve_days_before_cycle_end")
    rng = np.random.default_rng(seed * 10 + 4)

    for cyc_id in g.cycle_order:
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        now0 = at_simulated_time(cycle.debit_date)

        if g.cycle_status[cyc_id] == "SUCCESS":
            ingest_success(session, cycle_id=cyc_id, attempt_no=1, presented_at=now0, amount_paise=cycle.amount_paise, run_id=run.id)
            continue

        raw_code = g.cycle_first_code[cyc_id]
        cause = ground_truth_root_cause(world, g.cycle_first_code, cyc_id)
        ingest_failure(
            session, mandate_id=cycle.mandate_id, cycle_id=cyc_id, customer_id=mandate.customer_id,
            attempt_no=1, occurred_at=now0, amount_paise=cycle.amount_paise, raw_code=raw_code, gateway_desc=None, run_id=run.id,
        )
        if cause in TERMINAL_CAUSES:
            continue

        start = cycle.debit_date + timedelta(days=min_cooling_off)
        end = cycle.period_end - timedelta(days=reserve_days)
        customer = world.customers[mandate.customer_id]
        chosen = None
        d = start
        while d <= end:
            balance = world.funding_calendar[mandate.customer_id].get(d, 0)
            outage = world.issuer_days.get((customer.issuer_code, d))
            if balance >= cycle.amount_paise and not (outage and outage.is_outage):
                chosen = d
                break
            d += timedelta(days=1)
        if chosen is None:
            continue

        now = at_simulated_time(chosen)
        result = bank.resolve(world, cyc_id, chosen, 2, rng)
        cycle_row = session.get(Cycle, cyc_id)
        cycle_row.presentations_used = 2
        attempt = Attempt(
            cycle_id=cyc_id, attempt_no=2, presented_at=now, succeeded=result.succeeded,
            gateway_code=result.gateway_code, gateway_desc=result.gateway_desc, run_id=run.id,
        )
        session.add(attempt)
        session.flush()
        ledger.record(
            session, event_type="PRESENTMENT_SENT", run_id=run.id, occurred_at=now,
            rationale="Oracle presents with perfect information on the best available day.",
            payload={"attempt_no": 2}, cycle_id=cyc_id, mandate_id=cycle.mandate_id, customer_id=mandate.customer_id,
            amount_paise=cycle.amount_paise,
        )
        if result.succeeded:
            bank.apply_debit(world, mandate.customer_id, chosen, cycle.amount_paise)
            cycle_row.state = "RECOVERED"
            cycle_row.recovered_at = now
            cycle_row.recovered_via = "PRESENTMENT"
            cycle_row.recovered_amount_paise = cycle.amount_paise
            session.flush()
            ledger.record(
                session, event_type="RECOVERED", run_id=run.id, occurred_at=now,
                rationale=f"Oracle recovered {cycle.amount_paise} paise.", payload={"attempt_no": 2},
                cycle_id=cyc_id, mandate_id=cycle.mandate_id, customer_id=mandate.customer_id, amount_paise=cycle.amount_paise,
            )
        session.commit()

    return ArmResult(run_id=run.id, mode="ORACLE", corpus_id=g.corpus_id, seed=seed)
