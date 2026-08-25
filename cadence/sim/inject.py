"""Live demo injection — docs/08-API-CONTRACT.md `POST /sim/inject`, firing
one of docs/07's 12 adversarial cases against an existing run right now.

Every case drives the scenario through the REAL pipeline (ingest -> classify
-> predict -> decide -> gate -> scheduler) — nothing here bypasses the
compliance gate, and no ledger row is faked. Some cases need a small,
disclosed setup mutation (revoking a mandate, shrinking a cycle window,
backdating history, fast-forwarding through an intermediate message step) to
force a precondition into existence on demand instead of waiting for the
90-day corpus to produce it naturally; the resulting decision itself is
always the real gate's.

Lives in sim/, not core/: forcing preconditions (revoking a mandate,
shrinking a window) touches state core/ must never originate itself — core/
only ever reacts to what's already true in the DB.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from cadence.sim.clock import at_simulated_time

from sqlalchemy.orm import Session

from cadence.core.classify.record import classify_and_record
from cadence.core.compliance.config import PolicyConstants, load_policy_constants
from cadence.core.execute.interfaces import Adapters
from cadence.core.execute.scheduler import run_due_actions
from cadence.core.ingest.normalize import ingest_failure, observed_success_rate_for
from cadence.core.ledger import writer as ledger
from cadence.core.policy import engine as policy_engine
from cadence.models.tables import (
    Attempt,
    Customer,
    Cycle,
    Decision,
    FailureEvent,
    IssuerHealth,
    Ledger,
    Mandate,
    PaymentLink,
    PendingAction,
)
from cadence.sim.adapters import SimMessagingAdapter, SimPaymentLinkAdapter, SimPresentmentAdapter

PRESENTMENT_ACTIONS = {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"}
MESSAGE_ACTIONS = {"PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE"}

CASE_IDS = [
    "A1_LATE_MONTH_TIMING",
    "A2_MANDATE_REVOKED",
    "A3_LINK_PAID_CONCURRENT",
    "A4_ISSUER_OUTAGE_OVERLAP",
    "A5_NO_FEASIBLE_WINDOW",
    "A6_CUSTOMER_OPT_OUT",
    "A7_AMOUNT_EXCEEDS_CAP",
    "A8_DUAL_MANDATE_CONTACT_CAP",
    "A9_UNMAPPED_GATEWAY_CODE",
    "A10_CONSECUTIVE_FAILURES_CHURN",
    "A11_QUIET_HOURS_DEFERRAL",
    "A12_DORMANT_REACTIVATION",
]


def _find_cycle(
    session: Session, run_id: str, mandate_id: str | None, *, now: datetime,
    exclude_states=("ABANDONED", "RECOVERED"),
) -> tuple[Cycle, datetime]:
    """Excludes RECOVERED cycles by default — spawning a "new" failure on a
    cycle that already succeeded doesn't make sense and trips the gate's own
    `cycle_already_recovered` check, not the one the case is testing. Also
    requires the mandate to still be genuinely ACTIVE in the ground truth,
    so an unrelated pre-existing designed MANDATE_DEFECT scenario doesn't
    contaminate whatever this case is actually testing (unless the caller
    passes an explicit `mandate_id`, in which case it's respected as given).

    Returns `(cycle, now)`: `now` is re-anchored a few days into the picked
    cycle's own `period_start` rather than the caller's `now` — cycles opened
    in different months close on very different dates, so the original,
    single default `now` can land with almost no runway left in whichever
    cycle happens to get picked, which forces a spurious BAL_NO_WINDOW/
    escalation path unrelated to what the case is testing."""
    q = session.query(Cycle).join(Attempt, Attempt.cycle_id == Cycle.id).filter(Attempt.run_id == run_id)
    if mandate_id:
        q = q.filter(Cycle.mandate_id == mandate_id)
    else:
        q = q.join(Mandate, Cycle.mandate_id == Mandate.id).filter(Mandate.status == "ACTIVE")
    q = q.filter(~Cycle.state.in_(exclude_states))
    cycle = q.order_by(Cycle.amount_paise.desc()).first()
    if cycle is None:
        target = f"mandate {mandate_id}" if mandate_id else "any mandate"
        raise ValueError(f"no suitable open cycle found for run {run_id}, {target}")
    now = at_simulated_time(cycle.period_start + timedelta(days=3))
    return cycle, now


def _stage_cycle_with_notice(session: Session, run_id: str, mandate_id: str | None, *, now: datetime) -> tuple[Cycle, datetime]:
    """For cases that need to reach an actual SCHEDULE_PRESENTMENT: a fresh
    injected failure always lands on attempt_no >= 2 (attempt_no 1 is
    already taken by the corpus's own natural first attempt), and the
    BAL_A2 rule gates its SCHEDULE_PRESENTMENT candidate on a
    `predebit_notice_v1` message already having been sent for this cycle.

    In a completed batch run there is no stable state where a cycle has a
    notice on record but hasn't already gone on to a second real
    presentment attempt (the scheduler runs every pending action to
    completion in the same pass, including the presentment BAL_A1 pairs the
    notice with) — so waiting for one to exist naturally doesn't work. This
    seeds a `predebit_notice_v1` message onto a still-virgin cycle
    (attempt_no 1, active mandate, still open) ourselves, clearly recorded
    as injected setup scaffolding, not a real gated decision — the
    SCHEDULE_PRESENTMENT candidate that follows it is still evaluated by the
    real gate.

    Returns `(cycle, now)` with `now` anchored a few days into THIS cycle's
    own `period_start` — cycles opened in different months close on very
    different dates, so a single global default `now` can land with almost
    no runway left in whichever cycle happens to get picked."""
    from cadence.models.tables import ContactLog, Message

    q = (
        session.query(Cycle)
        .join(Attempt, Attempt.cycle_id == Cycle.id)
        .join(Mandate, Cycle.mandate_id == Mandate.id)
        .filter(
            Attempt.run_id == run_id, Mandate.status == "ACTIVE",
            ~Cycle.state.in_(("ABANDONED", "RECOVERED")), Cycle.presentations_used <= 1,
        )
    )
    if mandate_id:
        q = q.filter(Cycle.mandate_id == mandate_id)
    cycle = q.order_by(Cycle.amount_paise.desc()).first()
    if cycle is None:
        target = f"mandate {mandate_id}" if mandate_id else "any mandate"
        raise ValueError(
            f"no still-open, never-retried cycle found for run {run_id}, {target} — "
            "try a different mandate or a larger corpus"
        )
    now = at_simulated_time(cycle.period_start + timedelta(days=3))
    mandate = session.get(Mandate, cycle.mandate_id)
    sent_at = now - timedelta(hours=26)
    message = Message(
        customer_id=mandate.customer_id, cycle_id=cycle.id, channel="WHATSAPP", template_key="predebit_notice_v1",
        variables={"amount": f"{cycle.amount_paise / 100:,.2f}", "date": now.date().isoformat()},
        body_rendered="(injected setup) pre-debit notice", sent_at=sent_at, suppressed=False, run_id=run_id,
    )
    session.add(message)
    session.add(ContactLog(customer_id=mandate.customer_id, sent_at=sent_at, channel="WHATSAPP", run_id=run_id))
    session.flush()
    return cycle, now


def _spawn_failure(
    session: Session, *, mandate: Mandate, cycle: Cycle, run_id: str, now: datetime,
    raw_code: str, gateway_desc: str | None, constants: PolicyConstants,
) -> tuple[FailureEvent, Decision]:
    attempt_no = cycle.presentations_used + 1
    fev = ingest_failure(
        session, mandate_id=mandate.id, cycle_id=cycle.id, customer_id=mandate.customer_id,
        attempt_no=attempt_no, occurred_at=now, amount_paise=cycle.amount_paise,
        raw_code=raw_code, gateway_desc=gateway_desc, run_id=run_id,
    )
    cycle.presentations_used = attempt_no
    if cycle.state == "SCHEDULED":
        cycle.state = "IN_RECOVERY"
    session.flush()
    observed_rate = observed_success_rate_for(session, mandate.customer_id, now.date())
    classify_and_record(
        session, failure_event=fev, gateway_desc=gateway_desc, observed_success_rate=observed_rate, run_id=run_id
    )
    decision = policy_engine.decide(session, failure_event=fev, run_id=run_id, now=now, constants=constants)
    return fev, decision


def _pending_for(session: Session, failure_event_id: str) -> PendingAction | None:
    return (
        session.query(PendingAction)
        .join(Decision, PendingAction.decision_id == Decision.id)
        .filter(Decision.failure_event_id == failure_event_id, PendingAction.state == "PENDING")
        .order_by(PendingAction.run_at)
        .first()
    )


def _fast_forward_until(session: Session, *, run_id, failure_event_id, constants, adapters, max_steps=4):
    """Advance straight to each of this failure event's own pending action's
    `run_at` and process it for real (gate re-checked, adapters invoked) —
    skips the wall-clock wait, not the logic. Stops once the failure event's
    latest ALLOWED decision is a presentment action, or nothing is pending."""
    for _ in range(max_steps):
        latest_allowed = (
            session.query(Decision)
            .filter(Decision.failure_event_id == failure_event_id, Decision.gate_result == "ALLOWED")
            .order_by(Decision.id.desc())
            .first()
        )
        if latest_allowed is not None and latest_allowed.action_type in PRESENTMENT_ACTIONS:
            return latest_allowed
        pending = _pending_for(session, failure_event_id)
        if pending is None:
            return latest_allowed
        run_due_actions(session, now=pending.run_at, run_id=run_id, adapters=adapters, constants=constants)
    return (
        session.query(Decision)
        .filter(Decision.failure_event_id == failure_event_id, Decision.gate_result == "ALLOWED")
        .order_by(Decision.id.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# The 12 cases — docs/07-SYNTHETIC-DATA.md "Adversarial cases"
# ---------------------------------------------------------------------------


def _case_a1_late_month_timing(session, *, run_id, mandate_id, now, constants, adapters):
    """Failure late in the month; customer's real funding peak is early next
    month. Proves the core thesis: the model should reach past the naive
    T+1/T+3/T+5 window to the customer's actual peak, not retry blindly."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance in linked account", constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Spawned a balance-shortfall failure; policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a2_mandate_revoked(session, *, run_id, mandate_id, now, constants, adapters):
    """The staged refusal. A presentment is already scheduled for the
    future; the mandate gets revoked in between. The gate's execution-time
    re-check (not the scheduling-time check) must catch it."""
    cycle, now = _stage_cycle_with_notice(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)

    # Find (or create) a failure event on this mandate with a still-pending
    # presentment scheduled for the future.
    open_fev = (
        session.query(FailureEvent)
        .join(Attempt, FailureEvent.attempt_id == Attempt.id)
        .filter(FailureEvent.cycle_id == cycle.id, Attempt.run_id == run_id)
        .order_by(FailureEvent.occurred_at.desc())
        .first()
    )
    presentment_decision = None
    if open_fev is not None:
        presentment_decision = (
            session.query(Decision)
            .filter(Decision.failure_event_id == open_fev.id, Decision.action_type.in_(PRESENTMENT_ACTIONS),
                    Decision.gate_result == "ALLOWED")
            .order_by(Decision.id.desc())
            .first()
        )
    already_pending = (
        _pending_for(session, open_fev.id) is not None if open_fev is not None else False
    )
    if presentment_decision is None or not already_pending:
        fev, _ = _spawn_failure(
            session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
            raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
        )
        presentment_decision = _fast_forward_until(session, run_id=run_id, failure_event_id=fev.id, constants=constants, adapters=adapters)
        open_fev = fev

    if presentment_decision is None or presentment_decision.action_type not in PRESENTMENT_ACTIONS:
        raise ValueError("could not stage a pending presentment to revoke against — try a different mandate")

    pending = _pending_for(session, open_fev.id)
    if pending is None:
        raise ValueError("presentment already executed before the mandate could be revoked — try again")

    mandate.status = "REVOKED"
    mandate.revoked_at = now
    session.flush()
    ledger.record(
        session, event_type="MANDATE_REVOKED", run_id=run_id, occurred_at=now,
        rationale="Mandate revoked mid-schedule (injected A2) — a presentment is already pending.",
        payload={"pending_action_id": pending.id}, mandate_id=mandate.id, cycle_id=cycle.id, customer_id=mandate.customer_id,
    )

    executed = run_due_actions(session, now=pending.run_at, run_id=run_id, adapters=adapters, constants=constants)
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": open_fev.id,
        "note": "Revoked the mandate while a presentment was pending; the gate re-check at execution time "
                f"blocked it ({executed}). Check the ledger for a GATE_BLOCKED row and the auto-proposed REQUEST_REAUTH.",
    }


def _case_a3_link_paid_concurrent(session, *, run_id, mandate_id, now, constants, adapters):
    """Customer pays via a payment link while a presentment is still
    pending. The link-payment check must cancel the presentment — no double
    charge."""
    cycle, now = _stage_cycle_with_notice(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    fev, _ = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    presentment_decision = _fast_forward_until(session, run_id=run_id, failure_event_id=fev.id, constants=constants, adapters=adapters)
    if presentment_decision is None or presentment_decision.action_type not in PRESENTMENT_ACTIONS:
        raise ValueError("could not stage a pending presentment for this cycle — try a different mandate")
    pending = _pending_for(session, fev.id)
    if pending is None:
        raise ValueError("presentment already executed — try again")

    link = PaymentLink(
        cycle_id=cycle.id, amount_paise=cycle.amount_paise, razorpay_link_id="injected_a3",
        short_url="https://rzp.io/i/injected", expires_at=now + timedelta(days=5), run_id=run_id,
    )
    session.add(link)
    session.flush()
    check_decision = Decision(
        failure_event_id=fev.id, action_type="LINK_PAYMENT_CHECK", scheduled_for=now, channel="NONE",
        gate_result="ALLOWED", rationale="Injected A3: customer paid via a payment link out of band.",
        inputs_snapshot={"payment_link_id": link.id}, run_id=run_id,
    )
    session.add(check_decision)
    session.flush()
    session.add(PendingAction(decision_id=check_decision.id, run_at=now, state="PENDING"))
    session.flush()

    executed = run_due_actions(session, now=now, run_id=run_id, adapters=adapters, constants=constants)
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Customer paid via link while a presentment was pending ({executed}); the pending presentment "
                "should now show CANCELLED (reason LINK_PAID), and the cycle RECOVERED via PAYMENT_LINK.",
    }


def _case_a4_issuer_outage_overlap(session, *, run_id, mandate_id, now, constants, adapters):
    """A genuine issuer outage overlapping a real balance shortfall — the
    classifier must corroborate cause from BOTH signals, not code-match
    alone."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    customer = session.get(Customer, mandate.customer_id)

    existing = session.get(IssuerHealth, (customer.issuer_code, now.date()))
    if existing is not None:
        existing.observed_success_rate = 0.15
    else:
        session.add(
            IssuerHealth(
                issuer_code=customer.issuer_code, as_of_date=now.date(),
                observed_success_rate=0.15, is_outage=True,
            )
        )
    session.flush()

    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="ISSUER_DOWN", gateway_desc="Issuer processing temporarily unavailable", constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Set {customer.issuer_code}'s observed success rate to 0.15 (outage) and spawned a failure; "
                f"policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a5_no_feasible_window(session, *, run_id, mandate_id, now, constants, adapters):
    """Failure two days before the cycle closes — no day satisfies cooling-
    off + reserve. Must skip straight to a payment link, not force a doomed
    retry."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    cycle.period_end = now.date() + timedelta(days=2)
    session.flush()
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Shrank the cycle window to 2 days and spawned a failure; with no feasible presentment day, "
                f"policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a6_customer_opt_out(session, *, run_id, mandate_id, now, constants, adapters):
    """Customer opts out mid-recovery. All contact must stop immediately."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    customer = session.get(Customer, mandate.customer_id)
    customer.opted_out_at = now
    session.flush()
    ledger.record(
        session, event_type="CUSTOMER_OPTED_OUT", run_id=run_id, occurred_at=now,
        rationale="Customer opted out of all contact (injected A6).",
        customer_id=customer.id, mandate_id=mandate.id, cycle_id=cycle.id,
    )
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Opted the customer out, then spawned a failure; policy proposed {decision.action_type} "
                f"(gate result {decision.gate_result}) — {decision.rationale}",
    }


def _case_a7_amount_exceeds_cap(session, *, run_id, mandate_id, now, constants, adapters):
    """Charge above the mandate's cap. Correctly terminal — escalate, never
    present."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    original_amount = cycle.amount_paise
    cycle.amount_paise = mandate.max_amount_paise + 500_00
    session.flush()
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="AMOUNT_EXCEEDS_MANDATE", gateway_desc="Charge amount exceeds the mandate's authorised cap",
        constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Raised the charge to {cycle.amount_paise}p against a {mandate.max_amount_paise}p cap "
                f"(was {original_amount}p); policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a8_dual_mandate_contact_cap(session, *, run_id, mandate_id, now, constants, adapters):
    """Same customer, two mandates, both failing. The contact cap applies
    per customer, not per mandate — the second failure must not double the
    customer's message allowance."""
    cycle_a, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate_a = session.get(Mandate, cycle_a.mandate_id)
    mandate_b = (
        session.query(Mandate)
        .filter(Mandate.customer_id == mandate_a.customer_id, Mandate.id != mandate_a.id, Mandate.status == "ACTIVE")
        .first()
    )
    if mandate_b is None:
        raise ValueError(f"customer {mandate_a.customer_id} does not hold a second active mandate — try a different one")
    cycle_b, _ = _find_cycle(session, run_id, mandate_b.id, now=now)

    fev_a, decision_a = _spawn_failure(
        session, mandate=mandate_a, cycle=cycle_a, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    fev_b, decision_b = _spawn_failure(
        session, mandate=mandate_b, cycle=cycle_b, run_id=run_id, now=now + timedelta(minutes=1),
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    return {
        "mandate_id": mandate_a.id, "cycle_id": cycle_a.id, "failure_event_id": fev_a.id,
        "note": f"Mandate {mandate_a.id} -> {decision_a.action_type} ({decision_a.gate_result}); "
                f"mandate {mandate_b.id} -> {decision_b.action_type} ({decision_b.gate_result}). "
                "The second should show a contact-cap block if the first already used the customer's message quota.",
    }


def _case_a9_unmapped_gateway_code(session, *, run_id, mandate_id, now, constants, adapters):
    """A gateway code the taxonomy has never seen. Must degrade to
    UNKNOWN/terminal and escalate — never guess."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="XJ_9927_NOVEL_CODE", gateway_desc=None, constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Injected an unmapped gateway code; policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a10_consecutive_failures_churn(session, *, run_id, mandate_id, now, constants, adapters):
    """Two consecutive already-closed, unrecovered cycles on this mandate.
    The hard stopping rule must fire and cease automation, not keep trying."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    prior_cycles = (
        session.query(Cycle)
        .filter(Cycle.mandate_id == mandate.id, Cycle.id != cycle.id, Cycle.period_end < now.date())
        .order_by(Cycle.period_start.desc())
        .limit(2)
        .all()
    )
    max_needed = constants.value("max_consecutive_failed_cycles")
    for c in prior_cycles[: int(max_needed)]:
        c.state = "ABANDONED"
        c.recovered_at = None
        c.recovered_via = None
    session.flush()
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Marked {len(prior_cycles[: int(max_needed)])} prior cycle(s) as abandoned/unrecovered, then "
                f"spawned a new failure; policy proposed {decision.action_type} — {decision.rationale}",
    }


def _case_a11_quiet_hours_deferral(session, *, run_id, mandate_id, now, constants, adapters):
    """A recovery message would land in quiet hours (21:00-09:00 IST). It
    must be deferred to morning, not dropped."""
    cycle, now = _stage_cycle_with_notice(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    # 22:00 UTC = 03:30 IST the next day — well inside the quiet window,
    # regardless of the actual wall-clock time this demo runs at.
    quiet_now = now.replace(hour=22, minute=0, second=0, microsecond=0)
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=quiet_now,
        raw_code="INSUFFICIENT_FUNDS", gateway_desc="Insufficient balance", constants=constants,
    )
    morning_now = quiet_now + timedelta(hours=11)  # 09:00 UTC = 14:30 IST, safely past 09:00 IST
    redecided = policy_engine.decide(session, failure_event=fev, run_id=run_id, now=morning_now, constants=constants)
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"First decision at 03:30 IST: {decision.action_type} ({decision.gate_result}); "
                f"re-decided the next morning: {redecided.action_type} ({redecided.gate_result}) — "
                "the message should defer, not vanish.",
    }


def _case_a12_dormant_reactivation(session, *, run_id, mandate_id, now, constants, adapters):
    """A TOPUP_NUDGE/REQUEST_INSTRUMENT_UPDATE message actually lands and
    the customer completes payment via the follow-up link — the
    recoverable-action path finishing end to end."""
    cycle, now = _find_cycle(session, run_id, mandate_id, now=now)
    mandate = session.get(Mandate, cycle.mandate_id)
    fev, decision = _spawn_failure(
        session, mandate=mandate, cycle=cycle, run_id=run_id, now=now,
        raw_code="CARD_EXPIRED", gateway_desc="Card on file has expired", constants=constants,
    )
    executed: list[str] = []
    for _ in range(3):
        pending = _pending_for(session, fev.id)
        if pending is None:
            break
        executed += run_due_actions(session, now=pending.run_at, run_id=run_id, adapters=adapters, constants=constants)
        if cycle.state == "RECOVERED":
            break
    return {
        "mandate_id": mandate.id, "cycle_id": cycle.id, "failure_event_id": fev.id,
        "note": f"Dormant instrument nudged for reactivation; steps executed: {executed}; "
                f"cycle state now {cycle.state}.",
    }


_CASES = {
    "A1_LATE_MONTH_TIMING": _case_a1_late_month_timing,
    "A2_MANDATE_REVOKED": _case_a2_mandate_revoked,
    "A3_LINK_PAID_CONCURRENT": _case_a3_link_paid_concurrent,
    "A4_ISSUER_OUTAGE_OVERLAP": _case_a4_issuer_outage_overlap,
    "A5_NO_FEASIBLE_WINDOW": _case_a5_no_feasible_window,
    "A6_CUSTOMER_OPT_OUT": _case_a6_customer_opt_out,
    "A7_AMOUNT_EXCEEDS_CAP": _case_a7_amount_exceeds_cap,
    "A8_DUAL_MANDATE_CONTACT_CAP": _case_a8_dual_mandate_contact_cap,
    "A9_UNMAPPED_GATEWAY_CODE": _case_a9_unmapped_gateway_code,
    "A10_CONSECUTIVE_FAILURES_CHURN": _case_a10_consecutive_failures_churn,
    "A11_QUIET_HOURS_DEFERRAL": _case_a11_quiet_hours_deferral,
    "A12_DORMANT_REACTIVATION": _case_a12_dormant_reactivation,
}


def _build_adapters(session: Session, run_id: str):
    """Reconstruct the run's corpus World (same pattern as `/ingest/replay` in
    cadence/api/routers/ingest.py) so the Sim presentment/payment-link
    adapters have real generator ground truth to resolve against — an
    injected presentment is judged by the same bank simulator as every
    other attempt in this run, not faked."""
    import numpy as np

    from cadence.models.tables import CorpusMeta, Run
    from cadence.sim.generator import generate_corpus

    run = session.get(Run, run_id)
    if run is None:
        raise ValueError(f"unknown run_id {run_id}")
    meta = session.get(CorpusMeta, run.corpus_id)
    n_customers = meta.n_customers if meta is not None else 300
    g = generate_corpus(run.seed, n_customers=n_customers, write_to_db=False)
    rng_present = np.random.default_rng(run.seed * 10 + 97)
    rng_link = np.random.default_rng(run.seed * 10 + 98)
    return Adapters(
        presentment=SimPresentmentAdapter(g.world, rng_present),
        messaging=SimMessagingAdapter(),
        payment_link=SimPaymentLinkAdapter(rng_link),
    )


def _default_injection_now() -> datetime:
    """Injected scenarios must land inside the corpus's own generated
    calendar window (`sim/generator.py`'s `START_DATE`..`START_DATE +
    CALENDAR_DAYS`) — the funding calendar and issuer-health history the
    prediction model and the bank simulator read from simply don't exist
    outside it. Anchor a few days past the normal 90-day run window so
    there's a fresh, still-open corner of the calendar to work in, rather
    than using the real wall-clock date (which is nowhere near the
    generated corpus's Jan-2026 window)."""
    from cadence.sim.generator import DAYS, START_DATE

    return at_simulated_time(START_DATE + timedelta(days=DAYS + 3))


def inject_case(session: Session, *, run_id: str, case: str, mandate_id: str | None, now: datetime | None = None) -> dict:
    handler = _CASES.get(case)
    if handler is None:
        raise ValueError(f"unknown case id {case!r}; must be one of {CASE_IDS}")
    constants = load_policy_constants()
    adapters = _build_adapters(session, run_id)
    now = now or _default_injection_now()

    before_max_id = (
        session.query(Ledger.id).filter(Ledger.run_id == run_id).order_by(Ledger.id.desc()).limit(1).scalar()
    ) or 0

    result = handler(session, run_id=run_id, mandate_id=mandate_id, now=now, constants=constants, adapters=adapters)
    session.commit()

    ledger_ids = [
        row[0]
        for row in session.query(Ledger.id)
        .filter(Ledger.run_id == run_id, Ledger.id > before_max_id)
        .order_by(Ledger.id)
        .all()
    ]
    return {"case": case, "ledger_ids": ledger_ids, **result}
