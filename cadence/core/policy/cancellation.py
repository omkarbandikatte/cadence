"""Cancellation rules — docs/05-DECISION-ENGINE.md Part B."""
from __future__ import annotations

from sqlalchemy.orm import Session

from cadence.core.ledger import writer as ledger
from cadence.models.tables import Decision, FailureEvent, PendingAction

PRESENTMENT_ACTIONS = {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"}
MESSAGE_ACTIONS = {"PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE"}


def cancel_pending_for_cycle(
    session: Session,
    *,
    cycle_id: str,
    run_id: str,
    reason: str,
    now,
    only_action_types: set[str] | None = None,
) -> int:
    pendings = (
        session.query(PendingAction)
        .join(Decision, PendingAction.decision_id == Decision.id)
        .join(FailureEvent, Decision.failure_event_id == FailureEvent.id)
        .filter(FailureEvent.cycle_id == cycle_id, Decision.run_id == run_id, PendingAction.state == "PENDING")
        .all()
    )
    cancelled = 0
    for pending in pendings:
        decision = session.get(Decision, pending.decision_id)
        if only_action_types is not None and decision.action_type not in only_action_types:
            continue
        pending.state = "CANCELLED"
        pending.cancelled_reason = reason
        cancelled += 1
        ledger.record(
            session,
            event_type="ABANDONED" if reason == "CYCLE_CLOSED" else "GATE_BLOCKED",
            run_id=run_id,
            occurred_at=now,
            rationale=f"Cancelled scheduled {decision.action_type}: {reason}.",
            payload={"cancelled_reason": reason, "decision_id": decision.id},
            cycle_id=cycle_id,
        )
    session.flush()
    return cancelled
