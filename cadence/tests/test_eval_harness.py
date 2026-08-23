"""docs/10-EVALUATION.md: "A test asserts the three runs issue identical
queries to the simulator interface." Verified here as: the natural first
attempt (before any arm-specific policy diverges) is identical in outcome
across all three arms, since they all start from the same corpus and world.

Runs against the dev DB (cadence.db.SessionLocal), same as sim/run_a1_e2e.py —
issuer_health has no corpus-scoping column, so only one corpus can live in the
DB at a time; this test truncates first to guarantee a clean slate.
"""
from __future__ import annotations

from sqlalchemy import text

from cadence.db import SessionLocal
from cadence.eval.report import run_all_arms
from cadence.models.tables import Attempt, Run

SEED = 4242
N_CUSTOMERS = 25  # small corpus keeps this test fast

_TABLES = (
    "ledger", "pending_actions", "decisions", "predictions", "classifications",
    "failure_events", "attempts", "messages", "payment_links", "contact_log",
    "cycles", "mandates", "customers", "issuer_health", "funding_calendar", "corpus_meta", "runs",
)


def _truncate_dev_db():
    session = SessionLocal()
    try:
        session.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
        session.commit()
    finally:
        session.close()


def test_arms_agree_on_first_attempt_and_agent_has_zero_violations():
    _truncate_dev_db()
    result = run_all_arms(SEED, N_CUSTOMERS)

    session = SessionLocal()
    try:
        runs = session.query(Run).filter(Run.corpus_id == result["corpus_id"]).all()
        by_mode = {r.mode: r.id for r in runs}

        first_attempts_by_mode = {}
        for mode, run_id in by_mode.items():
            rows = (
                session.query(Attempt.cycle_id, Attempt.succeeded, Attempt.gateway_code)
                .filter(Attempt.run_id == run_id, Attempt.attempt_no == 1)
                .order_by(Attempt.cycle_id)
                .all()
            )
            first_attempts_by_mode[mode] = {r[0]: (r[1], r[2]) for r in rows}

        baseline_first = first_attempts_by_mode["BASELINE"]
        agent_first = first_attempts_by_mode["AGENT"]
        oracle_first = first_attempts_by_mode["ORACLE"]

        assert set(baseline_first) == set(agent_first) == set(oracle_first)
        for cyc_id in baseline_first:
            assert baseline_first[cyc_id] == agent_first[cyc_id] == oracle_first[cyc_id]
    finally:
        session.close()

    assert len(result["agent_audit"]["violations"]) == 0
