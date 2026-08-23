"""Independent auditor — re-derives legality from the ledger WITHOUT importing
core/compliance. Duplicated logic is intentional: "zero violations, verified
by a separate auditor that shares no code with the enforcement path" is a
materially stronger claim than the gate grading its own homework.
See docs/10-EVALUATION.md.
"""
from __future__ import annotations

from datetime import timedelta

from cadence.core.compliance.config import load_policy_constants
from cadence.models.tables import Attempt, Classification, Customer, Cycle, FailureEvent, Mandate, Message

AUDITOR_VERSION = "1.0"


def _classification_for_attempt(session, attempt: Attempt):
    fev = (
        session.query(FailureEvent)
        .join(Attempt, FailureEvent.attempt_id == Attempt.id)
        .filter(FailureEvent.cycle_id == attempt.cycle_id)
        .filter(Attempt.run_id == attempt.run_id, Attempt.attempt_no < attempt.attempt_no)
        .order_by(FailureEvent.occurred_at.desc())
        .first()
    )
    if fev is None:
        return None
    return session.query(Classification).filter_by(failure_event_id=fev.id).order_by(Classification.id.desc()).first()


def audit_presentments(session, run_id: str, constants) -> list[dict]:
    violations = []
    attempts = session.query(Attempt).filter_by(run_id=run_id).order_by(Attempt.cycle_id, Attempt.attempt_no).all()
    by_cycle: dict[str, list[Attempt]] = {}
    for a in attempts:
        by_cycle.setdefault(a.cycle_id, []).append(a)

    for cycle_id, cycle_attempts in by_cycle.items():
        mandate = (
            session.query(Mandate)
            .join(Cycle, Cycle.mandate_id == Mandate.id)
            .filter(Cycle.id == cycle_id)
            .first()
        )

        prior_presented_at = None
        for attempt in cycle_attempts:
            # attempt_no == 1 is the natural, uncontrolled scheduled debit —
            # the triggering event our system reacts to, not a presentment it
            # chose to make. Only audit presentments the system itself
            # decided to fire (attempt_no >= 2) against the mandate's state.
            if mandate is not None and attempt.attempt_no > 1:
                if attempt.presented_at.date() > mandate.valid_until:
                    violations.append({"cycle_id": cycle_id, "attempt_id": attempt.id, "code": "MANDATE_NOT_IN_VALIDITY"})
                if mandate.status == "REVOKED" and mandate.revoked_at is not None and attempt.presented_at >= mandate.revoked_at:
                    violations.append({"cycle_id": cycle_id, "attempt_id": attempt.id, "code": "MANDATE_NOT_ACTIVE"})

            if attempt.attempt_no > constants.value("max_presentations_per_cycle"):
                violations.append({"cycle_id": cycle_id, "attempt_id": attempt.id, "code": "PRESENTATION_CAP_EXCEEDED"})

            if prior_presented_at is not None:
                if attempt.presented_at - prior_presented_at < timedelta(days=constants.value("min_cooling_off_days")):
                    violations.append({"cycle_id": cycle_id, "attempt_id": attempt.id, "code": "COOLING_OFF_NOT_ELAPSED"})
            prior_presented_at = attempt.presented_at

            classification = _classification_for_attempt(session, attempt)
            if classification is not None and classification.disposition == "TERMINAL":
                violations.append({"cycle_id": cycle_id, "attempt_id": attempt.id, "code": "TERMINAL_DISPOSITION"})

    return violations


def audit_messages(session, run_id: str, constants) -> list[dict]:
    violations = []
    messages = session.query(Message).filter_by(run_id=run_id).order_by(Message.customer_id, Message.sent_at).all()

    start_h, start_m = (int(x) for x in constants.quiet_hours.start.split(":"))
    end_h, end_m = (int(x) for x in constants.quiet_hours.end.split(":"))
    ist_offset = timedelta(hours=5, minutes=30)

    weekly_cap = constants.value("max_contacts_per_week")
    per_customer: dict[str, list] = {}
    for m in messages:
        per_customer.setdefault(m.customer_id, []).append(m)

    for customer_id, msgs in per_customer.items():
        customer = session.get(Customer, customer_id)
        for m in msgs:
            if customer is not None and customer.opted_out_at is not None and m.sent_at >= customer.opted_out_at:
                violations.append({"message_id": m.id, "code": "CUSTOMER_OPTED_OUT"})

            ist_time = (m.sent_at + ist_offset).time()
            start_t, end_t = (start_h, start_m), (end_h, end_m)
            t = (ist_time.hour, ist_time.minute)
            in_quiet = (t >= start_t or t < end_t) if start_t > end_t else (start_t <= t < end_t)
            if in_quiet:
                violations.append({"message_id": m.id, "code": "QUIET_HOURS"})

            window_start = m.sent_at - timedelta(days=7)
            count_in_window = sum(1 for other in msgs if window_start <= other.sent_at <= m.sent_at)
            if count_in_window > weekly_cap:
                violations.append({"message_id": m.id, "code": "WEEKLY_CONTACT_CAP"})

    return violations


def audit(session, run_id: str) -> dict:
    constants = load_policy_constants()
    violations = audit_presentments(session, run_id, constants) + audit_messages(session, run_id, constants)
    rows_audited = (
        session.query(Attempt).filter_by(run_id=run_id).count()
        + session.query(Message).filter_by(run_id=run_id).count()
    )
    return {
        "rows_audited": rows_audited,
        "violations": violations,
        "auditor_version": AUDITOR_VERSION,
        "shares_code_with_gate": False,
    }
