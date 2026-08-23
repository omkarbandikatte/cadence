"""Scoring — docs/10-EVALUATION.md "Metrics".

cycles/mandates/customers have no run_id column (docs/03 — they're the
shared world, not per-run), so "was this cycle recovered in THIS run" can
never be read off `Cycle.state` once more than one arm has touched the row.
The ledger is the only run-scoped source of truth for outcomes.
"""
from __future__ import annotations

from cadence.models.tables import Attempt, Cycle, Ledger, Message


def compute_run_metrics(session, run_id: str, terminal_cycle_ids: set[str] | None = None) -> dict:
    failed_cycle_ids = {
        row[0]
        for row in session.query(Attempt.cycle_id).filter(Attempt.run_id == run_id, Attempt.succeeded.is_(False)).distinct().all()
    }
    recovered_rows = (
        session.query(Ledger)
        .filter(Ledger.run_id == run_id, Ledger.event_type == "RECOVERED")
        .all()
    )
    recovered_by_cycle = {row.cycle_id: row for row in recovered_rows if row.cycle_id in failed_cycle_ids}

    failed_cycles = session.query(Cycle).filter(Cycle.id.in_(failed_cycle_ids)).all() if failed_cycle_ids else []
    amount_by_cycle = {c.id: c.amount_paise for c in failed_cycles}

    recovered_paise = sum(row.amount_paise or 0 for row in recovered_by_cycle.values())
    at_risk_paise = sum(amount_by_cycle.values())
    recovery_rate = len(recovered_by_cycle) / len(failed_cycle_ids) if failed_cycle_ids else 0.0

    presentments_total = session.query(Attempt).filter(Attempt.run_id == run_id).count()
    presentments_per_recovery = presentments_total / len(recovered_by_cycle) if recovered_by_cycle else float("nan")

    # wasted_presentments: RETRIES (attempt_no > 1) against cycles that are
    # genuinely terminal (ground truth, supplied by the caller from the
    # corpus) — the unavoidable first attempt that discovers a terminal
    # cause isn't itself "wasted." Ground truth (not each arm's own,
    # possibly-wrong classification) so BASELINE — which never classifies
    # anything — is scored on the same basis as AGENT.
    terminal_cycle_ids = terminal_cycle_ids or set()
    wasted_presentments = (
        session.query(Attempt)
        .filter(Attempt.run_id == run_id, Attempt.cycle_id.in_(terminal_cycle_ids), Attempt.attempt_no > 1)
        .count()
        if terminal_cycle_ids
        else 0
    )

    messages_total = session.query(Message).filter(Message.run_id == run_id, Message.suppressed.is_(False)).count()
    messages_per_recovery = messages_total / len(recovered_by_cycle) if recovered_by_cycle else float("nan")

    recovery_days = [
        (row.occurred_at.date() - _first_failure_date(session, cyc_id, run_id)).days
        for cyc_id, row in recovered_by_cycle.items()
    ]
    mean_days_to_recovery = sum(recovery_days) / len(recovery_days) if recovery_days else float("nan")

    checks_run = session.query(Ledger).filter(Ledger.run_id == run_id, Ledger.event_type.in_(["DECISION", "GATE_BLOCKED"])).count()
    blocked = session.query(Ledger).filter(Ledger.run_id == run_id, Ledger.event_type == "GATE_BLOCKED").count()

    return {
        "failed_cycles": len(failed_cycle_ids),
        "recovered_cycles": len(recovered_by_cycle),
        "recovered_paise": recovered_paise,
        "at_risk_paise": at_risk_paise,
        "recovery_rate": recovery_rate,
        "presentments_total": presentments_total,
        "presentments_per_recovery": presentments_per_recovery,
        "wasted_presentments": wasted_presentments,
        "messages_total": messages_total,
        "messages_per_recovery": messages_per_recovery,
        "mean_days_to_recovery": mean_days_to_recovery,
        "checks_run": checks_run,
        "actions_blocked": blocked,
    }


def _first_failure_date(session, cycle_id: str, run_id: str):
    first = (
        session.query(Attempt)
        .filter(Attempt.cycle_id == cycle_id, Attempt.run_id == run_id, Attempt.succeeded.is_(False))
        .order_by(Attempt.presented_at)
        .first()
    )
    return first.presented_at.date()


def captured_of_headroom(baseline_rate: float, agent_rate: float, oracle_rate: float) -> float:
    denom = oracle_rate - baseline_rate
    if denom == 0:
        return float("nan")
    return (agent_rate - baseline_rate) / denom
