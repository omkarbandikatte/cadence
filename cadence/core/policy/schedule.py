"""When a chosen candidate should actually run — docs/05-DECISION-ENGINE.md
Part B candidate params (`offset_days_before_presentment`, `at`, `after_minutes`,
`after_days`, `max_wait_days`)."""
from __future__ import annotations

from datetime import datetime, timedelta

from cadence.sim.clock import at_simulated_time


def compute_run_at(candidate, *, now: datetime, failure_date, prediction_outcome) -> datetime:
    action = candidate.action
    params = candidate.params

    if action == "SCHEDULE_PRESENTMENT":
        offset = prediction_outcome.best_day_offset if prediction_outcome else None
        if offset is None:
            return now
        return at_simulated_time(failure_date + timedelta(days=offset))

    if action == "PRE_DEBIT_NOTICE":
        offset = prediction_outcome.best_day_offset if prediction_outcome else None
        lead = params.get("offset_days_before_presentment", 2)
        if offset is None:
            return now
        return at_simulated_time(failure_date + timedelta(days=offset)) - timedelta(days=lead)

    if action == "TOPUP_NUDGE":
        offset = prediction_outcome.second_best_day_offset if prediction_outcome else None
        lead = params.get("offset_days_before_presentment", 1)
        if offset is None:
            return now
        return at_simulated_time(failure_date + timedelta(days=offset)) - timedelta(days=lead)

    if action == "PRESENT_NOW":
        return now + timedelta(minutes=params.get("after_minutes", 0))

    if action == "WAIT_ISSUER_RECOVERY":
        return now + timedelta(days=params.get("max_wait_days", 3))

    if action == "STOP_MARK_CHURN":
        return now + timedelta(days=params.get("after_days", 0))

    # REQUEST_REAUTH, REQUEST_INSTRUMENT_UPDATE, SEND_PAYMENT_LINK,
    # ESCALATE_TO_MERCHANT, NO_ACTION — act on the next tick.
    return now
