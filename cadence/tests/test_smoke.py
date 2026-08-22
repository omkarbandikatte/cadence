"""One smoke test that creates and reads each model — M0 verification target."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from cadence.models.tables import (
    Attempt,
    Classification,
    ContactLog,
    CorpusMeta,
    Customer,
    Cycle,
    Decision,
    FailureEvent,
    FundingCalendar,
    IssuerHealth,
    Ledger,
    Mandate,
    Message,
    PaymentLink,
    PendingAction,
    Prediction,
    Run,
)

NOW = datetime(2026, 1, 27, tzinfo=timezone.utc)


def test_create_and_read_every_model(session):
    run = Run(mode="AGENT", corpus_id="cor_test", seed=42, policy_config_hash="abc123")
    session.add(run)
    session.flush()

    customer = Customer(
        name="Test Customer",
        phone_e164="+919999999999",
        email="test@example.com",
        issuer_code="HDFC",
        segment="SALARIED_MONTH_START",
    )
    session.add(customer)
    session.flush()

    mandate = Mandate(
        customer_id=customer.id,
        rail="UPI_AUTOPAY",
        status="ACTIVE",
        max_amount_paise=500000,
        frequency="MONTHLY",
        debit_day=27,
        valid_from=date(2026, 1, 1),
        valid_until=date(2027, 1, 1),
    )
    session.add(mandate)
    session.flush()

    cycle = Cycle(
        mandate_id=mandate.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        amount_paise=149900,
        state="IN_RECOVERY",
    )
    session.add(cycle)
    session.flush()

    attempt = Attempt(
        cycle_id=cycle.id,
        attempt_no=1,
        presented_at=NOW,
        succeeded=False,
        gateway_code="INSUFFICIENT_FUNDS",
        gateway_desc="insufficient balance",
        run_id=run.id,
    )
    session.add(attempt)
    session.flush()

    failure_event = FailureEvent(
        attempt_id=attempt.id,
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=customer.id,
        raw_code="INSUFFICIENT_FUNDS",
        amount_paise=149900,
        occurred_at=NOW,
    )
    session.add(failure_event)
    session.flush()

    classification = Classification(
        failure_event_id=failure_event.id,
        root_cause="BALANCE_SHORTFALL",
        subtype="NONE",
        disposition="RECOVERABLE_TIMING",
        confidence="0.95",
        matched_rule="BAL_001",
    )
    session.add(classification)

    prediction = Prediction(
        failure_event_id=failure_event.id,
        curve=[{"day_offset": d, "p": 0.1} for d in range(15)],
        best_day_offset=5,
        best_p="0.610",
        basis="CUSTOMER_HISTORY",
        feature_contributions={"customer_term": 0.61},
    )
    session.add(prediction)

    decision = Decision(
        failure_event_id=failure_event.id,
        action_type="SCHEDULE_PRESENTMENT",
        scheduled_for=NOW + timedelta(days=5),
        channel="WHATSAPP",
        gate_result="ALLOWED",
        blocked_by=None,
        rationale="Waiting until day 5 because this customer's salary lands then.",
        inputs_snapshot={"root_cause": "BALANCE_SHORTFALL"},
        run_id=run.id,
    )
    session.add(decision)
    session.flush()

    pending_action = PendingAction(
        decision_id=decision.id,
        run_at=NOW + timedelta(days=5),
        state="PENDING",
    )
    session.add(pending_action)

    message = Message(
        customer_id=customer.id,
        cycle_id=cycle.id,
        channel="WHATSAPP",
        template_key="predebit_notice_v1",
        variables={"amount": "1,499"},
        body_rendered="Your payment of Rs 1,499 is scheduled for the 2nd.",
        sent_at=NOW,
        suppressed=False,
        run_id=run.id,
    )
    session.add(message)

    payment_link = PaymentLink(
        cycle_id=cycle.id,
        amount_paise=149900,
        expires_at=NOW + timedelta(days=5),
        run_id=run.id,
    )
    session.add(payment_link)

    issuer_health = IssuerHealth(
        issuer_code="HDFC",
        as_of_date=date(2026, 1, 27),
        observed_success_rate="0.910",
        is_outage=False,
    )
    session.add(issuer_health)

    ledger = Ledger(
        occurred_at=NOW,
        event_type="DECISION",
        run_id=run.id,
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=customer.id,
        decision_id=decision.id,
        amount_paise=None,
        channel=None,
        rationale="Waiting until day 5 because this customer's salary lands then.",
        payload={"foo": "bar"},
    )
    session.add(ledger)

    contact_log = ContactLog(
        customer_id=customer.id, sent_at=NOW, channel="WHATSAPP", run_id=run.id
    )
    session.add(contact_log)

    funding_calendar = FundingCalendar(
        customer_id=customer.id, date=date(2026, 1, 27), balance_paise=50000
    )
    session.add(funding_calendar)

    corpus_meta = CorpusMeta(
        seed=42,
        n_customers=1,
        n_mandates=1,
        n_cycles=1,
        cause_mix={"BALANCE_SHORTFALL": 1.0},
    )
    session.add(corpus_meta)

    session.flush()

    assert session.scalar(select(Customer).where(Customer.id == customer.id)) is not None
    assert session.scalar(select(Mandate).where(Mandate.id == mandate.id)) is not None
    assert session.scalar(select(Cycle).where(Cycle.id == cycle.id)) is not None
    assert session.scalar(select(Attempt).where(Attempt.id == attempt.id)) is not None
    assert (
        session.scalar(select(FailureEvent).where(FailureEvent.id == failure_event.id))
        is not None
    )
    assert (
        session.scalar(
            select(Classification).where(Classification.id == classification.id)
        )
        is not None
    )
    assert session.scalar(select(Prediction).where(Prediction.id == prediction.id)) is not None
    assert session.scalar(select(Decision).where(Decision.id == decision.id)) is not None
    assert (
        session.scalar(
            select(PendingAction).where(PendingAction.id == pending_action.id)
        )
        is not None
    )
    assert session.scalar(select(Message).where(Message.id == message.id)) is not None
    assert (
        session.scalar(select(PaymentLink).where(PaymentLink.id == payment_link.id))
        is not None
    )
    assert (
        session.scalar(
            select(IssuerHealth).where(IssuerHealth.issuer_code == "HDFC")
        )
        is not None
    )
    assert session.scalar(select(Ledger).where(Ledger.id == ledger.id)) is not None
    assert (
        session.scalar(select(ContactLog).where(ContactLog.id == contact_log.id))
        is not None
    )
    assert (
        session.scalar(
            select(FundingCalendar).where(FundingCalendar.customer_id == customer.id)
        )
        is not None
    )
    assert (
        session.scalar(select(CorpusMeta).where(CorpusMeta.id == corpus_meta.id))
        is not None
    )
    assert session.scalar(select(Run).where(Run.id == run.id)) is not None
