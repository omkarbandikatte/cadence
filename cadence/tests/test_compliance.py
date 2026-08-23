"""The compliance gate test suite — docs/06-COMPLIANCE-GATE.md."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from cadence.core.compliance import ProposedAction, evaluate
from cadence.core.compliance import kill_switch
from cadence.core.execute.interfaces import MessagingAdapter, PresentmentAdapter
from cadence.models.tables import (
    Attempt,
    Classification,
    ContactLog,
    Customer,
    Cycle,
    FailureEvent,
    Mandate,
    Message,
    PaymentLink,
    Run,
)

NOW = datetime(2026, 1, 27, 6, 0, tzinfo=timezone.utc)  # 11:30 IST — outside quiet hours


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    kill_switch._reset_for_tests()
    yield
    kill_switch._reset_for_tests()


def _world(session, *, root_cause="BALANCE_SHORTFALL", disposition="RECOVERABLE_TIMING"):
    run = Run(mode="AGENT", corpus_id="cor_test", seed=1, policy_config_hash="x")
    session.add(run)
    session.flush()

    customer = Customer(
        name="T", phone_e164="+911", email="t@example.com", issuer_code="HDFC", segment="GIG_IRREGULAR"
    )
    session.add(customer)
    session.flush()

    mandate = Mandate(
        customer_id=customer.id,
        rail="UPI_AUTOPAY",
        status="ACTIVE",
        max_amount_paise=100000,
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
        amount_paise=100000,
        state="IN_RECOVERY",
        presentations_used=0,
    )
    session.add(cycle)
    session.flush()

    attempt = Attempt(
        cycle_id=cycle.id, attempt_no=1, presented_at=NOW - timedelta(days=5), succeeded=False,
        gateway_code="INSUFFICIENT_FUNDS", run_id=run.id,
    )
    session.add(attempt)
    session.flush()

    fev = FailureEvent(
        attempt_id=attempt.id, mandate_id=mandate.id, cycle_id=cycle.id, customer_id=customer.id,
        raw_code="INSUFFICIENT_FUNDS", amount_paise=100000, occurred_at=NOW - timedelta(days=5),
    )
    session.add(fev)
    session.flush()

    cls = Classification(
        failure_event_id=fev.id, root_cause=root_cause, subtype="NONE",
        disposition=disposition, confidence="0.95", matched_rule="BAL_001",
    )
    session.add(cls)
    session.flush()

    return {"run": run, "customer": customer, "mandate": mandate, "cycle": cycle}


def _presentment_action(w, **overrides):
    kwargs = dict(
        action_type="SCHEDULE_PRESENTMENT",
        run_id=w["run"].id,
        now=NOW,
        mandate_id=w["mandate"].id,
        cycle_id=w["cycle"].id,
        customer_id=w["customer"].id,
        amount_paise=w["cycle"].amount_paise,
    )
    kwargs.update(overrides)
    return ProposedAction(**kwargs)


def _messaging_action(w, **overrides):
    kwargs = dict(
        action_type="PRE_DEBIT_NOTICE",
        run_id=w["run"].id,
        now=NOW,
        mandate_id=w["mandate"].id,
        cycle_id=w["cycle"].id,
        customer_id=w["customer"].id,
        channel="WHATSAPP",
        template_key="predebit_notice_v1",
        template_variables={"amount": "1,499", "date": "2 Feb"},
    )
    kwargs.update(overrides)
    return ProposedAction(**kwargs)


def _add_predebit_notice(session, w, sent_at):
    session.add(
        Message(
            customer_id=w["customer"].id, cycle_id=w["cycle"].id, channel="WHATSAPP",
            template_key="predebit_notice_v1", variables={}, body_rendered="x",
            sent_at=sent_at, suppressed=False, run_id=w["run"].id,
        )
    )
    session.flush()


def test_presentment_blocked_when_mandate_revoked(session):
    w = _world(session)
    w["mandate"].status = "REVOKED"
    session.flush()
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    decision = evaluate(_presentment_action(w), session)
    assert decision.result == "BLOCKED"
    assert "MANDATE_NOT_ACTIVE" in [b.code for b in decision.blocks]


def test_presentment_blocked_when_cap_reached(session):
    w = _world(session)
    w["cycle"].presentations_used = 3
    session.flush()
    decision = evaluate(_presentment_action(w), session)
    assert "PRESENTATION_CAP_EXCEEDED" in [b.code for b in decision.blocks]


def test_presentment_blocked_when_cooling_off_not_elapsed(session):
    w = _world(session)
    session.add(
        Attempt(cycle_id=w["cycle"].id, attempt_no=2, presented_at=NOW - timedelta(hours=6),
                succeeded=False, gateway_code="INSUFFICIENT_FUNDS", run_id=w["run"].id)
    )
    session.flush()
    decision = evaluate(_presentment_action(w), session)
    assert "COOLING_OFF_NOT_ELAPSED" in [b.code for b in decision.blocks]


def test_presentment_blocked_without_pre_debit_notice(session):
    w = _world(session)
    decision = evaluate(_presentment_action(w), session)
    assert "PRE_DEBIT_NOTICE_MISSING" in [b.code for b in decision.blocks]


def test_presentment_allowed_with_pre_debit_notice_sent_in_time(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    decision = evaluate(_presentment_action(w), session)
    assert decision.result == "ALLOWED"
    assert decision.token is not None


def test_presentment_blocked_when_amount_over_mandate_cap(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    decision = evaluate(_presentment_action(w, amount_paise=999999999), session)
    assert "AMOUNT_EXCEEDS_MANDATE_CAP" in [b.code for b in decision.blocks]


def test_presentment_blocked_after_cycle_end(session):
    w = _world(session)
    w["cycle"].period_end = date(2026, 1, 20)
    session.flush()
    decision = evaluate(_presentment_action(w), session)
    assert "CYCLE_CLOSED" in [b.code for b in decision.blocks]


def test_presentment_blocked_on_terminal_disposition(session):
    w = _world(session, root_cause="MANDATE_DEFECT", disposition="TERMINAL")
    decision = evaluate(_presentment_action(w), session)
    codes = [b.code for b in decision.blocks]
    assert "TERMINAL_DISPOSITION" in codes
    assert "ACTION_FORBIDDEN_FOR_CAUSE" in codes


def test_message_blocked_in_quiet_hours(session):
    w = _world(session)
    quiet_now = datetime(2026, 1, 27, 16, 0, tzinfo=timezone.utc)  # 21:30 IST
    decision = evaluate(_messaging_action(w, now=quiet_now), session)
    assert "QUIET_HOURS" in [b.code for b in decision.blocks]


def test_message_blocked_when_opted_out(session):
    w = _world(session)
    w["customer"].opted_out_at = NOW
    session.flush()
    decision = evaluate(_messaging_action(w), session)
    assert "CUSTOMER_OPTED_OUT" in [b.code for b in decision.blocks]


def test_message_blocked_at_weekly_cap(session):
    w = _world(session)
    for i in range(3):
        session.add(
            ContactLog(customer_id=w["customer"].id, sent_at=NOW - timedelta(days=i), channel="WHATSAPP", run_id=w["run"].id)
        )
    session.flush()
    decision = evaluate(_messaging_action(w), session)
    assert "WEEKLY_CONTACT_CAP" in [b.code for b in decision.blocks]


def test_message_blocked_for_risk_block_cause(session):
    w = _world(session, root_cause="RISK_BLOCK", disposition="TERMINAL")
    decision = evaluate(_messaging_action(w, action_type="REQUEST_REAUTH"), session)
    assert "NO_CONTACT_FOR_RISK_CASE" in [b.code for b in decision.blocks]


def test_message_blocked_on_unapproved_template(session):
    w = _world(session)
    decision = evaluate(_messaging_action(w, template_key="not_a_real_template"), session)
    assert "TEMPLATE_NOT_APPROVED" in [b.code for b in decision.blocks]


def test_link_blocked_when_open_link_exists(session):
    w = _world(session)
    session.add(
        PaymentLink(
            cycle_id=w["cycle"].id, amount_paise=100000, expires_at=NOW + timedelta(days=1), run_id=w["run"].id
        )
    )
    session.flush()
    action = ProposedAction(
        action_type="SEND_PAYMENT_LINK", run_id=w["run"].id, now=NOW, mandate_id=w["mandate"].id,
        cycle_id=w["cycle"].id, customer_id=w["customer"].id, amount_paise=100000,
        channel="WHATSAPP", template_key="payment_link_v1", template_variables={"amount": "1,499", "link": "http://x"},
    )
    decision = evaluate(action, session)
    assert "LINK_ALREADY_OPEN" in [b.code for b in decision.blocks]


def test_all_blocks_returned_not_just_first(session):
    w = _world(session, root_cause="MANDATE_DEFECT", disposition="TERMINAL")
    w["mandate"].status = "REVOKED"
    w["cycle"].presentations_used = 5
    session.flush()
    decision = evaluate(_presentment_action(w), session)
    codes = {b.code for b in decision.blocks}
    assert {"MANDATE_NOT_ACTIVE", "PRESENTATION_CAP_EXCEEDED", "TERMINAL_DISPOSITION", "ACTION_FORBIDDEN_FOR_CAUSE"} <= codes


def test_gate_reevaluated_at_execution_time_after_state_change(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    first = evaluate(_presentment_action(w), session)
    assert first.result == "ALLOWED"

    w["mandate"].status = "REVOKED"
    session.flush()
    second = evaluate(_presentment_action(w), session)
    assert second.result == "BLOCKED"
    assert "MANDATE_NOT_ACTIVE" in [b.code for b in second.blocks]


def test_blocked_action_writes_ledger_row(session):
    from cadence.models.tables import Ledger

    w = _world(session)
    evaluate(_presentment_action(w), session)
    row = session.query(Ledger).filter_by(event_type="GATE_BLOCKED", cycle_id=w["cycle"].id).first()
    assert row is not None
    assert row.rationale


def test_gate_never_raises_on_policy_violation(session):
    w = _world(session, root_cause="RISK_BLOCK", disposition="TERMINAL")
    w["mandate"].status = "REVOKED"
    w["cycle"].presentations_used = 99
    session.flush()
    decision = evaluate(_presentment_action(w), session)  # must not raise
    assert decision.result == "BLOCKED"


def test_merchant_pause_blocks_everything(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    kill_switch.pause_merchant()
    decision = evaluate(_presentment_action(w), session)
    assert "MERCHANT_PAUSED" in [b.code for b in decision.blocks]


def test_customer_hold_blocks_everything(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    kill_switch.place_hold(w["customer"].id)
    decision = evaluate(_presentment_action(w), session)
    assert "CUSTOMER_MANUALLY_HELD" in [b.code for b in decision.blocks]


def test_no_action_ever_bypasses_gate():
    """Every adapter call must be preceded by a gate pass — a GateToken can
    only be minted by compliance.evaluate()."""
    with pytest.raises(TypeError):
        PresentmentAdapter().present(None, mandate_id="mnd_x", cycle_id="cyc_x", amount_paise=100)
    with pytest.raises(RuntimeError):
        from cadence.core.compliance.gate import GateToken

        GateToken(object(), "SCHEDULE_PRESENTMENT", "cyc_x")


def test_token_scoped_to_its_own_action_type(session):
    w = _world(session)
    _add_predebit_notice(session, w, NOW - timedelta(hours=48))
    decision = evaluate(_presentment_action(w), session)
    assert decision.token is not None
    with pytest.raises(TypeError):
        MessagingAdapter().send(decision.token, customer_id=w["customer"].id, template_key="x", variables={})
