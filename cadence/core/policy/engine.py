"""The policy decision loop — docs/05-DECISION-ENGINE.md Part B and
docs/02-ARCHITECTURE.md stage 4-5 (POLICY -> GATE). One call to decide() runs
policy against the gate until a candidate is allowed (or every candidate for
the matched rule is exhausted), and always leaves behind exactly one
`Decision` row plus, if allowed, a `PendingAction`.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from cadence.core.compliance.config import PolicyConstants, load_policy_constants
from cadence.core.compliance.gate import ProposedAction, evaluate
from cadence.core.ledger import writer as ledger
from cadence.core.policy.candidates import next_candidate
from cadence.core.policy.config import Candidate
from cadence.core.policy.context import PolicyContext
from cadence.core.policy.rationale import build_rationale
from cadence.core.policy.schedule import compute_run_at
from cadence.core.predict import predict_for_failure
from cadence.models.tables import Classification, Cycle, Decision, FailureEvent, Mandate, PendingAction

TERMINAL_ACTIONS_NO_ADAPTER = {"WAIT_ISSUER_RECOVERY", "ESCALATE_TO_MERCHANT", "STOP_MARK_CHURN", "NO_ACTION"}


def latest_classification(session: Session, failure_event_id: str) -> Classification:
    return (
        session.query(Classification)
        .filter_by(failure_event_id=failure_event_id)
        .order_by(Classification.id.desc())
        .first()
    )


def _consecutive_failed_cycles(session: Session, mandate_id: str, now) -> int:
    """Trailing non-recovered *closed* cycles for this mandate, most recent
    first. Cycles that haven't reached their period_end yet are still in
    progress, not failures."""
    cycles = (
        session.query(Cycle)
        .filter(Cycle.mandate_id == mandate_id, Cycle.period_end < now.date())
        .order_by(Cycle.period_start.desc())
        .all()
    )
    count = 0
    for c in cycles:
        if c.state == "RECOVERED":
            break
        count += 1
    return count


def _build_variables(template_key: str | None, amount_paise: int, target_date, link_url: str | None) -> dict:
    if template_key is None:
        return {}
    amount_str = f"{amount_paise / 100:,.2f}"
    if template_key in ("predebit_notice_v1", "topup_nudge_v1"):
        return {"amount": amount_str, "date": target_date.isoformat() if target_date else "pending"}
    if template_key == "payment_link_v1":
        return {"amount": amount_str, "link": link_url or "pending"}
    if template_key in ("reauth_v1", "instrument_update_v1"):
        return {"link": link_url or "pending"}
    return {}


def propose(
    session: Session,
    *,
    candidate: Candidate,
    failure_event: FailureEvent,
    cycle: Cycle,
    mandate: Mandate,
    classification: Classification,
    prediction_outcome,
    run_id: str,
    now,
    constants: PolicyConstants,
) -> tuple[Decision, object]:
    """Gate-check exactly one candidate and persist the Decision row (allowed
    or blocked). Returns (decision_row, gate_decision)."""
    run_at = compute_run_at(candidate, now=now, failure_date=failure_event.occurred_at.date(), prediction_outcome=prediction_outcome)
    target_date = run_at.date()
    variables = _build_variables(candidate.params.get("template"), cycle.amount_paise, target_date, link_url=None)

    # Check the gate as of the action's own scheduled moment, not "now" — a
    # presentment scheduled 2 days out should be judged against the state it
    # will find then (e.g. the pre-debit notice will have had time to age),
    # not the state at decision time. The scheduler re-checks for real with
    # the actual clock when run_at arrives.
    proposed = ProposedAction(
        action_type=candidate.action,
        run_id=run_id,
        now=run_at,
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=mandate.customer_id,
        amount_paise=cycle.amount_paise,
        channel=candidate.params.get("channel"),
        template_key=candidate.params.get("template"),
        template_variables=variables,
    )
    gate_decision = evaluate(proposed, session, constants)

    rationale = build_rationale(
        candidate=candidate,
        classification=classification,
        prediction_outcome=prediction_outcome,
        gate_decision=gate_decision,
        failure_date=failure_event.occurred_at.date(),
        amount_paise=cycle.amount_paise,
    )

    decision_row = Decision(
        failure_event_id=failure_event.id,
        action_type=candidate.action,
        scheduled_for=run_at if gate_decision.result == "ALLOWED" else None,
        channel=candidate.params.get("channel") or "NONE",
        gate_result=gate_decision.result,
        blocked_by=(
            [{"check": b.check, "code": b.code, "message": b.message} for b in gate_decision.blocks]
            if gate_decision.blocks
            else None
        ),
        rationale=rationale,
        inputs_snapshot={
            "root_cause": classification.root_cause,
            "subtype": classification.subtype,
            "disposition": classification.disposition,
            "attempt_no": cycle.presentations_used + 1,
            "prediction_basis": prediction_outcome.basis if prediction_outcome else None,
            "prediction_best_day_offset": prediction_outcome.best_day_offset if prediction_outcome else None,
        },
        run_id=run_id,
    )
    session.add(decision_row)
    session.flush()

    if gate_decision.result == "ALLOWED":
        pending = PendingAction(decision_id=decision_row.id, run_at=run_at, state="PENDING")
        session.add(pending)
        session.flush()

    return decision_row, gate_decision


def decide(session: Session, *, failure_event: FailureEvent, run_id: str, now, constants: PolicyConstants | None = None) -> Decision:
    constants = constants or load_policy_constants()
    classification = latest_classification(session, failure_event.id)
    cycle = session.get(Cycle, failure_event.cycle_id)
    mandate = session.get(Mandate, failure_event.mandate_id)

    # cycle.presentations_used already counts the original failed attempt, so
    # a cycle with 1 presentation used is about to make its FIRST retry
    # decision (policy attempt_no=1), not its second.
    attempt_no = cycle.presentations_used
    days_left = (cycle.period_end - now.date()).days
    presentations_exhausted = cycle.presentations_used >= constants.value("max_presentations_per_cycle")
    waited_days = (now - failure_event.occurred_at).days

    prediction_outcome = None
    feasible_window = False
    if classification.root_cause in ("BALANCE_SHORTFALL", "ISSUER_DEGRADED"):
        prediction_outcome = predict_for_failure(
            session,
            failure_event=failure_event,
            co_occurring_issuer_degradation=(classification.root_cause == "ISSUER_DEGRADED"),
            run_id=run_id,
        )
        feasible_window = prediction_outcome.best_day_offset is not None

    ctx = PolicyContext(
        cause=classification.root_cause,
        subtype=classification.subtype,
        attempt_no=attempt_no,
        cycle_state=cycle.state,
        days_left_in_cycle=days_left,
        feasible_window=feasible_window,
        presentations_exhausted=presentations_exhausted,
        waited_days=waited_days,
    )

    rejected: set[str] = {
        d.action_type
        for d in session.query(Decision).filter_by(failure_event_id=failure_event.id, gate_result="ALLOWED").all()
    }

    # Hard stopping rule (docs/05 Part B): N consecutive non-recovered cycles
    # on this mandate ends automated recovery outright, bypassing the normal
    # cause-based table.
    if _consecutive_failed_cycles(session, mandate.id, now) >= constants.value("max_consecutive_failed_cycles"):
        decision_row, _ = propose(
            session, candidate=Candidate(action="STOP_MARK_CHURN", params={"after_days": 0}),
            failure_event=failure_event, cycle=cycle, mandate=mandate, classification=classification,
            prediction_outcome=prediction_outcome, run_id=run_id, now=now, constants=constants,
        )
        return decision_row

    while True:
        candidate = next_candidate(ctx, rejected)
        if candidate is None:
            candidate = Candidate(action="NO_ACTION")

        decision_row, gate_decision = propose(
            session,
            candidate=candidate,
            failure_event=failure_event,
            cycle=cycle,
            mandate=mandate,
            classification=classification,
            prediction_outcome=prediction_outcome,
            run_id=run_id,
            now=now,
            constants=constants,
        )

        if gate_decision.result == "ALLOWED":
            return decision_row

        rejected.add(candidate.action)
        if candidate.action == "NO_ACTION":
            return decision_row
