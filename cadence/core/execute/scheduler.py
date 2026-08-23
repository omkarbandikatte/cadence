"""Executes due PendingActions. Re-evaluates the gate at execution time (the
world moves between scheduling and firing), dispatches to the injected
adapters, and feeds outcomes back into the ledger and — for failed retries —
back into classify/predict/policy. See docs/02-ARCHITECTURE.md stage 6.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from cadence.core.classify.record import classify_and_record
from cadence.core.compliance.config import PolicyConstants, load_policy_constants
from cadence.core.compliance.gate import ProposedAction, evaluate
from cadence.core.execute.interfaces import Adapters
from cadence.core.ingest.normalize import ingest_failure, observed_success_rate_for
from cadence.core.ledger import writer as ledger
from cadence.core.policy import engine as policy_engine
from cadence.core.policy.cancellation import cancel_pending_for_cycle
from cadence.core.policy.config import Candidate
from cadence.models.tables import Attempt, Cycle, Decision, FailureEvent, Mandate, PaymentLink, PendingAction

MANDATE_LIFECYCLE_BLOCK_CODES = {"MANDATE_NOT_ACTIVE", "MANDATE_NOT_IN_VALIDITY"}
PRESENTMENT_ACTIONS = {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"}
MESSAGE_ACTIONS = {"PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE"}


def run_due_actions(
    session: Session,
    *,
    now,
    run_id: str,
    adapters: Adapters,
    constants: PolicyConstants | None = None,
) -> list[str]:
    constants = constants or load_policy_constants()
    executed: list[str] = []

    due = (
        session.query(PendingAction)
        .join(Decision, PendingAction.decision_id == Decision.id)
        .filter(Decision.run_id == run_id, PendingAction.state == "PENDING", PendingAction.run_at <= now)
        .order_by(PendingAction.run_at)
        .all()
    )

    for pending in due:
        decision = session.get(Decision, pending.decision_id)
        failure_event = session.get(FailureEvent, decision.failure_event_id)
        cycle = session.get(Cycle, failure_event.cycle_id)
        mandate = session.get(Mandate, failure_event.mandate_id)

        if decision.action_type == "LINK_PAYMENT_CHECK":
            _execute_link_payment_check(session, pending, decision, cycle, run_id, now)
            executed.append("LINK_PAYMENT_CHECK")
            continue

        if decision.action_type == "WAIT_ISSUER_RECOVERY":
            pending.state = "EXECUTED"
            session.flush()
            policy_engine.decide(session, failure_event=failure_event, run_id=run_id, now=now, constants=constants)
            executed.append("WAIT_ISSUER_RECOVERY")
            continue

        if decision.action_type == "STOP_MARK_CHURN":
            cycle.state = "ABANDONED"
            session.flush()
            ledger.record(
                session, event_type="CHURN_FLAGGED", run_id=run_id, occurred_at=now,
                rationale="Automated recovery stopped; cycle flagged as churned.",
                payload={"decision_id": decision.id}, cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id,
            )
            pending.state = "EXECUTED"
            session.flush()
            executed.append("STOP_MARK_CHURN")
            continue

        if decision.action_type in ("ESCALATE_TO_MERCHANT", "NO_ACTION"):
            pending.state = "EXECUTED"
            session.flush()
            executed.append(decision.action_type)
            continue

        # Re-evaluate the gate at execution time — the world may have moved.
        proposed = ProposedAction(
            action_type=decision.action_type,
            run_id=run_id,
            now=now,
            mandate_id=mandate.id,
            cycle_id=cycle.id,
            customer_id=mandate.customer_id,
            amount_paise=cycle.amount_paise,
            channel=decision.channel if decision.channel != "NONE" else None,
            template_key=_template_for(decision),
            template_variables=_variables_for(decision, cycle, now),
        )
        gate_decision = evaluate(proposed, session, constants)

        if gate_decision.result == "BLOCKED":
            pending.state = "CANCELLED"
            pending.cancelled_reason = "GATE_BLOCKED_AT_EXECUTION"
            session.flush()
            block_codes = {b.code for b in gate_decision.blocks}
            if decision.action_type in PRESENTMENT_ACTIONS and block_codes & MANDATE_LIFECYCLE_BLOCK_CODES:
                _stage_reauth_refusal(session, failure_event=failure_event, cycle=cycle, mandate=mandate, run_id=run_id, now=now, constants=constants)
            executed.append(f"{decision.action_type}:BLOCKED_AT_EXECUTION")
            continue

        if decision.action_type in PRESENTMENT_ACTIONS:
            _execute_presentment(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, constants, gate_decision.token)
        elif decision.action_type in MESSAGE_ACTIONS:
            _execute_message(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, gate_decision.token, constants)
        elif decision.action_type == "SEND_PAYMENT_LINK":
            _execute_payment_link(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, gate_decision.token)
        else:
            pending.state = "EXECUTED"
            session.flush()

        executed.append(decision.action_type)

    return executed


def _template_for(decision: Decision) -> str | None:
    return (decision.inputs_snapshot or {}).get("template_key") or _TEMPLATE_BY_ACTION.get(decision.action_type)


_TEMPLATE_BY_ACTION = {
    "PRE_DEBIT_NOTICE": "predebit_notice_v1",
    "TOPUP_NUDGE": "topup_nudge_v1",
    "REQUEST_REAUTH": "reauth_v1",
    "REQUEST_INSTRUMENT_UPDATE": "instrument_update_v1",
    "SEND_PAYMENT_LINK": "payment_link_v1",
}


def _variables_for(decision: Decision, cycle: Cycle, now) -> dict:
    template_key = _template_for(decision)
    amount_str = f"{cycle.amount_paise / 100:,.2f}"
    if template_key in ("predebit_notice_v1", "topup_nudge_v1"):
        return {"amount": amount_str, "date": (decision.scheduled_for or now).date().isoformat()}
    if template_key == "payment_link_v1":
        return {"amount": amount_str, "link": "pending"}
    if template_key in ("reauth_v1", "instrument_update_v1"):
        return {"link": "pending"}
    return {}


def _execute_presentment(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, constants, token):
    attempt_no = cycle.presentations_used + 1
    result = adapters.presentment.present(
        token,
        mandate_id=mandate.id, cycle_id=cycle.id, amount_paise=cycle.amount_paise,
        attempt_date=now.date(), attempt_no=attempt_no,
    )
    cycle.presentations_used = attempt_no
    session.flush()

    attempt = Attempt(
        cycle_id=cycle.id, attempt_no=attempt_no, presented_at=now, succeeded=result["succeeded"],
        gateway_code=result.get("gateway_code"), gateway_desc=result.get("gateway_desc"), run_id=run_id,
    )
    session.add(attempt)
    session.flush()

    ledger.record(
        session, event_type="PRESENTMENT_SENT", run_id=run_id, occurred_at=now,
        rationale=f"Presented {cycle.amount_paise} paise (attempt {attempt_no}).",
        payload={"attempt_no": attempt_no}, cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id,
        amount_paise=cycle.amount_paise,
    )

    if result["succeeded"]:
        cycle.state = "RECOVERED"
        cycle.recovered_at = now
        cycle.recovered_via = "PRESENTMENT"
        cycle.recovered_amount_paise = cycle.amount_paise
        pending.state = "EXECUTED"
        session.flush()
        ledger.record(
            session, event_type="RECOVERED", run_id=run_id, occurred_at=now,
            rationale=f"Recovered {cycle.amount_paise} paise via presentment on attempt {attempt_no}.",
            payload={"attempt_no": attempt_no}, cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id,
            amount_paise=cycle.amount_paise,
        )
        cancel_pending_for_cycle(session, cycle_id=cycle.id, run_id=run_id, reason="CUSTOMER_PAID", now=now)
        return

    pending.state = "EXECUTED"
    session.flush()

    new_fev = ingest_failure(
        session, mandate_id=mandate.id, cycle_id=cycle.id, customer_id=mandate.customer_id,
        attempt_no=attempt_no, occurred_at=now, amount_paise=cycle.amount_paise,
        raw_code=result.get("gateway_code") or "UNKNOWN", gateway_desc=result.get("gateway_desc"), run_id=run_id,
    )
    observed_rate = observed_success_rate_for(session, mandate.customer_id, now.date())
    classify_and_record(session, failure_event=new_fev, gateway_desc=result.get("gateway_desc"), observed_success_rate=observed_rate, run_id=run_id)
    policy_engine.decide(session, failure_event=new_fev, run_id=run_id, now=now, constants=constants)


def _execute_message(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, token, constants):
    from cadence.models.tables import ContactLog, Message

    template_key = _template_for(decision)
    variables = _variables_for(decision, cycle, now)
    result = adapters.messaging.send(
        token,
        customer_id=mandate.customer_id, channel=decision.channel, template_key=template_key, variables=variables,
    )
    message = Message(
        customer_id=mandate.customer_id, cycle_id=cycle.id, channel=decision.channel, template_key=template_key,
        variables=variables, body_rendered=result.get("body_rendered", ""), sent_at=now, suppressed=False, run_id=run_id,
    )
    session.add(message)
    session.add(ContactLog(customer_id=mandate.customer_id, sent_at=now, channel=decision.channel, run_id=run_id))
    session.flush()

    ledger.record(
        session, event_type="MESSAGE_SENT", run_id=run_id, occurred_at=now,
        rationale=f"Sent {template_key} to the customer.", payload={"template_key": template_key},
        cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id, channel=decision.channel,
    )
    pending.state = "EXECUTED"
    session.flush()

    if decision.action_type in ("PRE_DEBIT_NOTICE", "TOPUP_NUDGE"):
        # These are precursors to a scheduled presentment in the same policy
        # rule (docs/05 BAL_A1/BAL_A2) — re-run policy so it proposes the
        # presentment now that the notice has gone out.
        policy_engine.decide(session, failure_event=failure_event, run_id=run_id, now=now, constants=constants)


def _execute_payment_link(session, pending, decision, failure_event, cycle, mandate, adapters, run_id, now, token):
    from cadence.core.compliance.config import load_policy_constants
    from cadence.models.tables import ContactLog, Message

    constants = load_policy_constants()
    expiry_days = constants.value("payment_link_expiry_days")

    link_result = adapters.payment_link.create_link(
        token, cycle_id=cycle.id, amount_paise=cycle.amount_paise, created_at=now,
    )
    link = PaymentLink(
        cycle_id=cycle.id, amount_paise=cycle.amount_paise, razorpay_link_id=link_result.get("razorpay_link_id"),
        short_url=link_result.get("short_url"), expires_at=now + timedelta(days=expiry_days), run_id=run_id,
    )
    session.add(link)
    session.flush()
    ledger.record(
        session, event_type="LINK_CREATED", run_id=run_id, occurred_at=now,
        rationale=f"Created a payment link for {cycle.amount_paise} paise.", payload={"link_id": link.id},
        cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id, amount_paise=cycle.amount_paise,
    )

    variables = {"amount": f"{cycle.amount_paise / 100:,.2f}", "link": link.short_url or ""}
    msg_result = adapters.messaging.send(
        token, customer_id=mandate.customer_id, channel=decision.channel,
        template_key="payment_link_v1", variables=variables,
    )
    message = Message(
        customer_id=mandate.customer_id, cycle_id=cycle.id, channel=decision.channel, template_key="payment_link_v1",
        variables=variables, body_rendered=msg_result.get("body_rendered", ""), sent_at=now, suppressed=False, run_id=run_id,
    )
    session.add(message)
    session.add(ContactLog(customer_id=mandate.customer_id, sent_at=now, channel=decision.channel, run_id=run_id))
    session.flush()
    ledger.record(
        session, event_type="MESSAGE_SENT", run_id=run_id, occurred_at=now,
        rationale="Sent the payment link to the customer.", payload={"template_key": "payment_link_v1"},
        cycle_id=cycle.id, mandate_id=mandate.id, customer_id=mandate.customer_id, channel=decision.channel,
    )

    pending.state = "EXECUTED"
    session.flush()

    if link_result.get("will_pay"):
        check_decision = Decision(
            failure_event_id=failure_event.id, action_type="LINK_PAYMENT_CHECK", scheduled_for=now,
            channel="NONE", gate_result="ALLOWED", rationale="Internal: check whether the payment link was paid.",
            inputs_snapshot={"payment_link_id": link.id}, run_id=run_id,
        )
        session.add(check_decision)
        session.flush()
        session.add(
            PendingAction(
                decision_id=check_decision.id,
                run_at=now + timedelta(days=link_result["days_to_pay"]),
                state="PENDING",
            )
        )
        session.flush()


def _execute_link_payment_check(session, pending, decision, cycle, run_id, now):
    link_id = (decision.inputs_snapshot or {}).get("payment_link_id")
    link = session.get(PaymentLink, link_id) if link_id else None
    pending.state = "EXECUTED"
    if link is None or cycle.state == "RECOVERED":
        session.flush()
        return
    link.paid_at = now
    cycle.state = "RECOVERED"
    cycle.recovered_at = now
    cycle.recovered_via = "PAYMENT_LINK"
    cycle.recovered_amount_paise = cycle.amount_paise
    session.flush()
    ledger.record(
        session, event_type="LINK_PAID", run_id=run_id, occurred_at=now,
        rationale=f"Payment link paid: {cycle.amount_paise} paise recovered.",
        payload={"link_id": link.id}, cycle_id=cycle.id, amount_paise=cycle.amount_paise,
    )
    ledger.record(
        session, event_type="RECOVERED", run_id=run_id, occurred_at=now,
        rationale=f"Recovered {cycle.amount_paise} paise via payment link.",
        payload={"link_id": link.id}, cycle_id=cycle.id, amount_paise=cycle.amount_paise,
    )
    cancel_pending_for_cycle(session, cycle_id=cycle.id, run_id=run_id, reason="LINK_PAID", now=now)


def _stage_reauth_refusal(session, *, failure_event, cycle, mandate, run_id, now, constants):
    classification_row = policy_engine.latest_classification(session, failure_event.id)
    policy_engine.propose(
        session,
        candidate=Candidate(action="REQUEST_REAUTH", params={"channel": "WHATSAPP", "template": "reauth_v1"}),
        failure_event=failure_event, cycle=cycle, mandate=mandate, classification=classification_row,
        prediction_outcome=None, run_id=run_id, now=now, constants=constants,
    )
