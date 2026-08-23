"""Every compliance check, as a named, independent function. All checks in
the applicable group(s) run for a given action — no short-circuit, so the
ledger records every reason an action was blocked. See docs/06-COMPLIANCE-GATE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from cadence.core.compliance import kill_switch
from cadence.core.compliance.config import PolicyConstants
from cadence.models.tables import (
    Attempt,
    Classification,
    Customer,
    Cycle,
    FailureEvent,
    Mandate,
    Message,
    PaymentLink,
)

IST_OFFSET = timedelta(hours=5, minutes=30)

# docs/04-FAILURE-TAXONOMY.md — "Cause -> permitted actions"
PERMITTED_ACTIONS_FOR_CAUSE: dict[str, set[str]] = {
    "BALANCE_SHORTFALL": {
        "PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "SCHEDULE_PRESENTMENT",
        "SEND_PAYMENT_LINK", "STOP_MARK_CHURN",
    },
    "ISSUER_DEGRADED": {"WAIT_ISSUER_RECOVERY", "SCHEDULE_PRESENTMENT", "SEND_PAYMENT_LINK"},
    "TECHNICAL_TRANSIENT": {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"},
    "MANDATE_DEFECT": {"REQUEST_REAUTH", "SEND_PAYMENT_LINK", "ESCALATE_TO_MERCHANT", "NO_ACTION"},
    "INSTRUMENT_DEFECT": {
        "REQUEST_INSTRUMENT_UPDATE", "SEND_PAYMENT_LINK", "ESCALATE_TO_MERCHANT", "STOP_MARK_CHURN",
    },
    "RISK_BLOCK": {"ESCALATE_TO_MERCHANT", "NO_ACTION"},
    "UNKNOWN": {"ESCALATE_TO_MERCHANT", "NO_ACTION"},
}

TEMPLATE_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "predebit_notice_v1": ("amount", "date"),
    "topup_nudge_v1": ("amount", "date"),
    "payment_link_v1": ("amount", "link"),
    "reauth_v1": ("link",),
    "instrument_update_v1": ("link",),
}
CHANNEL_MAX_LEN = {"WHATSAPP": 1024, "SMS": 160, "EMAIL": 10000}


def _latest_classification(session, cycle_id: str, run_id: str) -> Classification | None:
    fev = (
        session.query(FailureEvent)
        .join(Attempt, FailureEvent.attempt_id == Attempt.id)
        .filter(FailureEvent.cycle_id == cycle_id, Attempt.run_id == run_id)
        .order_by(FailureEvent.occurred_at.desc())
        .first()
    )
    if fev is None:
        return None
    return (
        session.query(Classification)
        .filter_by(failure_event_id=fev.id)
        .order_by(Classification.id.desc())
        .first()
    )


# ---- presentment checks -------------------------------------------------

def mandate_not_active(action, session, constants: PolicyConstants):
    mandate = session.get(Mandate, action.mandate_id)
    if mandate is None or mandate.status != "ACTIVE":
        return "MANDATE_NOT_ACTIVE", "the mandate is not active"
    return None


def mandate_not_in_validity(action, session, constants: PolicyConstants):
    mandate = session.get(Mandate, action.mandate_id)
    if mandate is None:
        return "MANDATE_NOT_IN_VALIDITY", "mandate not found"
    today = action.now.date()
    if not (mandate.valid_from <= today <= mandate.valid_until):
        return "MANDATE_NOT_IN_VALIDITY", "outside the mandate's validity window"
    return None


def amount_exceeds_mandate_cap(action, session, constants: PolicyConstants):
    mandate = session.get(Mandate, action.mandate_id)
    if mandate is not None and action.amount_paise is not None and action.amount_paise > mandate.max_amount_paise:
        return "AMOUNT_EXCEEDS_MANDATE_CAP", "amount exceeds the mandate cap"
    return None


def presentation_cap_exceeded(action, session, constants: PolicyConstants):
    cycle = session.get(Cycle, action.cycle_id)
    cap = constants.value("max_presentations_per_cycle")
    if cycle is not None and cycle.presentations_used >= cap:
        return "PRESENTATION_CAP_EXCEEDED", f"already used {cycle.presentations_used} of {cap} presentations"
    return None


def cooling_off_not_elapsed(action, session, constants: PolicyConstants):
    last = (
        session.query(Attempt)
        .filter_by(cycle_id=action.cycle_id, run_id=action.run_id)
        .order_by(Attempt.presented_at.desc())
        .first()
    )
    if last is None:
        return None
    min_days = constants.value("min_cooling_off_days")
    if action.now - last.presented_at < timedelta(days=min_days):
        return "COOLING_OFF_NOT_ELAPSED", f"fewer than {min_days} days since the last attempt"
    return None


def frequency_violation(action, session, constants: PolicyConstants):
    already_succeeded = (
        session.query(Attempt)
        .filter_by(cycle_id=action.cycle_id, run_id=action.run_id, succeeded=True)
        .first()
    )
    if already_succeeded is not None:
        return "FREQUENCY_VIOLATION", "a successful debit already exists in this cycle's period"
    return None


def pre_debit_notice_missing(action, session, constants: PolicyConstants):
    lead_hours = constants.value("pre_debit_notice_hours")
    cutoff = action.now - timedelta(hours=lead_hours)
    notice = (
        session.query(Message)
        .filter_by(cycle_id=action.cycle_id, run_id=action.run_id, template_key="predebit_notice_v1", suppressed=False)
        .filter(Message.sent_at <= cutoff)
        .first()
    )
    if notice is None:
        return "PRE_DEBIT_NOTICE_MISSING", f"no pre-debit notice sent at least {lead_hours}h before presentment"
    return None


def cycle_closed(action, session, constants: PolicyConstants):
    cycle = session.get(Cycle, action.cycle_id)
    reserve_days = constants.value("reserve_days_before_cycle_end")
    if cycle is not None and action.now.date() > cycle.period_end - timedelta(days=reserve_days):
        return "CYCLE_CLOSED", "past the cycle's presentable window"
    return None


def cycle_already_recovered(action, session, constants: PolicyConstants):
    cycle = session.get(Cycle, action.cycle_id)
    if cycle is not None and cycle.state == "RECOVERED":
        return "CYCLE_ALREADY_RECOVERED", "this cycle has already been recovered"
    return None


def dispute_freeze(action, session, constants: PolicyConstants):
    # No dispute/chargeback modelling in scope (docs/03-DATA-MODEL.md has no
    # disputes table) — always passes. Kept as a named check so the gate's
    # structure and audit trail match docs/06 exactly.
    return None


def terminal_disposition(action, session, constants: PolicyConstants):
    cls = _latest_classification(session, action.cycle_id, action.run_id)
    if cls is not None and cls.disposition == "TERMINAL":
        return "TERMINAL_DISPOSITION", "classification disposition is TERMINAL"
    return None


def action_forbidden_for_cause(action, session, constants: PolicyConstants):
    cls = _latest_classification(session, action.cycle_id, action.run_id)
    if cls is None:
        return None
    permitted = PERMITTED_ACTIONS_FOR_CAUSE.get(cls.root_cause, set())
    if action.action_type not in permitted:
        return "ACTION_FORBIDDEN_FOR_CAUSE", f"{action.action_type} is not permitted for {cls.root_cause}"
    return None


# ---- messaging checks ----------------------------------------------------

def customer_opted_out(action, session, constants: PolicyConstants):
    customer = session.get(Customer, action.customer_id)
    if customer is not None and customer.opted_out_at is not None:
        return "CUSTOMER_OPTED_OUT", "customer has opted out of all contact"
    return None


def quiet_hours(action, session, constants: PolicyConstants):
    ist_now = (action.now + IST_OFFSET).time()
    start = constants.quiet_hours.start
    end = constants.quiet_hours.end
    start_t = _parse_hhmm(start)
    end_t = _parse_hhmm(end)
    in_quiet = (start_t <= ist_now) or (ist_now < end_t) if start_t > end_t else (start_t <= ist_now < end_t)
    if in_quiet:
        return "QUIET_HOURS", f"current IST time is within the quiet window {start}-{end}"
    return None


def _parse_hhmm(s: str):
    from datetime import time as _time

    h, m = s.split(":")
    return _time(int(h), int(m))


def weekly_contact_cap(action, session, constants: PolicyConstants):
    from cadence.models.tables import ContactLog

    cap = constants.value("max_contacts_per_week")
    since = action.now - timedelta(days=7)
    count = (
        session.query(ContactLog)
        .filter(
            ContactLog.customer_id == action.customer_id,
            ContactLog.run_id == action.run_id,
            ContactLog.sent_at >= since,
        )
        .count()
    )
    if count >= cap:
        return "WEEKLY_CONTACT_CAP", f"already contacted {count} times in the trailing 7 days"
    return None


def cycle_contact_cap(action, session, constants: PolicyConstants):
    cap = constants.value("max_contacts_per_cycle")
    count = session.query(Message).filter_by(cycle_id=action.cycle_id, run_id=action.run_id).count()
    if count >= cap:
        return "CYCLE_CONTACT_CAP", f"already sent {count} messages for this cycle"
    return None


def template_not_approved(action, session, constants: PolicyConstants):
    if action.template_key not in TEMPLATE_ALLOWLIST:
        return "TEMPLATE_NOT_APPROVED", f"{action.template_key!r} is not an approved template"
    return None


def template_variables_invalid(action, session, constants: PolicyConstants):
    required = TEMPLATE_ALLOWLIST.get(action.template_key)
    if required is None:
        return None  # TEMPLATE_NOT_APPROVED already covers this case
    variables = action.template_variables or {}
    missing = [v for v in required if not variables.get(v)]
    if missing:
        return "TEMPLATE_VARIABLES_INVALID", f"missing variables: {', '.join(missing)}"
    max_len = CHANNEL_MAX_LEN.get(action.channel, 1024)
    rendered_len = sum(len(str(v)) for v in variables.values())
    if rendered_len > max_len:
        return "TEMPLATE_VARIABLES_INVALID", f"rendered length exceeds the {action.channel} limit"
    return None


def no_contact_for_risk_case(action, session, constants: PolicyConstants):
    cls = _latest_classification(session, action.cycle_id, action.run_id)
    if cls is not None and cls.root_cause == "RISK_BLOCK":
        return "NO_CONTACT_FOR_RISK_CASE", "root cause is RISK_BLOCK; never auto-contact the customer"
    return None


def duplicate_message(action, session, constants: PolicyConstants):
    existing = (
        session.query(Message)
        .filter_by(cycle_id=action.cycle_id, template_key=action.template_key, run_id=action.run_id, suppressed=False)
        .first()
    )
    if existing is not None:
        return "DUPLICATE_MESSAGE", f"an identical {action.template_key} message was already sent for this cycle"
    return None


# ---- payment link checks -------------------------------------------------

def link_already_open(action, session, constants: PolicyConstants):
    existing = (
        session.query(PaymentLink)
        .filter(
            PaymentLink.cycle_id == action.cycle_id,
            PaymentLink.run_id == action.run_id,
            PaymentLink.paid_at.is_(None),
            PaymentLink.expires_at > action.now,
        )
        .first()
    )
    if existing is not None:
        return "LINK_ALREADY_OPEN", "an unexpired unpaid payment link already exists for this cycle"
    return None


def amount_mismatch(action, session, constants: PolicyConstants):
    cycle = session.get(Cycle, action.cycle_id)
    if cycle is not None and action.amount_paise is not None and action.amount_paise != cycle.amount_paise:
        return "AMOUNT_MISMATCH", "link amount does not equal the outstanding cycle amount"
    return None


# ---- global kill switches -------------------------------------------------

def merchant_paused(action, session, constants: PolicyConstants):
    if kill_switch.is_merchant_paused():
        return "MERCHANT_PAUSED", "merchant has paused automation"
    return None


def run_budget_exceeded(action, session, constants: PolicyConstants):
    if action.action_type in PRESENTMENT_ACTION_TYPES:
        cap = constants.value("run_budget_max_presentments")
        count = session.query(Attempt).filter_by(run_id=action.run_id).count()
        if count >= cap:
            return "RUN_BUDGET_EXCEEDED", f"run has issued {count} presentments, at the circuit-breaker cap"
    if action.action_type in MESSAGING_ACTION_TYPES:
        cap = constants.value("run_budget_max_messages")
        count = session.query(Message).filter_by(run_id=action.run_id).count()
        if count >= cap:
            return "RUN_BUDGET_EXCEEDED", f"run has sent {count} messages, at the circuit-breaker cap"
    return None


def customer_manually_held(action, session, constants: PolicyConstants):
    if action.customer_id and kill_switch.is_customer_held(action.customer_id):
        return "CUSTOMER_MANUALLY_HELD", "support has placed a hold on this customer"
    return None


PRESENTMENT_ACTION_TYPES = {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"}
MESSAGING_ACTION_TYPES = {
    "PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "SEND_PAYMENT_LINK", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE",
}
PAYMENT_LINK_ACTION_TYPES = {"SEND_PAYMENT_LINK"}


@dataclass(frozen=True)
class Check:
    name: str
    group: str
    fn: Callable


PRESENTMENT_CHECKS = [
    Check("MANDATE_NOT_ACTIVE", "presentment", mandate_not_active),
    Check("MANDATE_NOT_IN_VALIDITY", "presentment", mandate_not_in_validity),
    Check("AMOUNT_EXCEEDS_MANDATE_CAP", "presentment", amount_exceeds_mandate_cap),
    Check("PRESENTATION_CAP_EXCEEDED", "presentment", presentation_cap_exceeded),
    Check("COOLING_OFF_NOT_ELAPSED", "presentment", cooling_off_not_elapsed),
    Check("FREQUENCY_VIOLATION", "presentment", frequency_violation),
    Check("PRE_DEBIT_NOTICE_MISSING", "presentment", pre_debit_notice_missing),
    Check("CYCLE_CLOSED", "presentment", cycle_closed),
    Check("CYCLE_ALREADY_RECOVERED", "presentment", cycle_already_recovered),
    Check("DISPUTE_FREEZE", "presentment", dispute_freeze),
    Check("TERMINAL_DISPOSITION", "presentment", terminal_disposition),
    Check("ACTION_FORBIDDEN_FOR_CAUSE", "presentment", action_forbidden_for_cause),
]

MESSAGING_CHECKS = [
    Check("CUSTOMER_OPTED_OUT", "messaging", customer_opted_out),
    Check("QUIET_HOURS", "messaging", quiet_hours),
    Check("WEEKLY_CONTACT_CAP", "messaging", weekly_contact_cap),
    Check("CYCLE_CONTACT_CAP", "messaging", cycle_contact_cap),
    Check("TEMPLATE_NOT_APPROVED", "messaging", template_not_approved),
    Check("TEMPLATE_VARIABLES_INVALID", "messaging", template_variables_invalid),
    Check("NO_CONTACT_FOR_RISK_CASE", "messaging", no_contact_for_risk_case),
    Check("DUPLICATE_MESSAGE", "messaging", duplicate_message),
]

PAYMENT_LINK_CHECKS = [
    Check("LINK_ALREADY_OPEN", "payment_link", link_already_open),
    Check("AMOUNT_MISMATCH", "payment_link", amount_mismatch),
    Check("CYCLE_ALREADY_RECOVERED", "payment_link", cycle_already_recovered),
]

GLOBAL_CHECKS = [
    Check("MERCHANT_PAUSED", "global", merchant_paused),
    Check("RUN_BUDGET_EXCEEDED", "global", run_budget_exceeded),
    Check("CUSTOMER_MANUALLY_HELD", "global", customer_manually_held),
]

ALL_CHECKS = PRESENTMENT_CHECKS + MESSAGING_CHECKS + PAYMENT_LINK_CHECKS + GLOBAL_CHECKS
