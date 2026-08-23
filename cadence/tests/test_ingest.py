"""core/ingest normalizer: idempotency and observed-success-rate lookup."""
from __future__ import annotations

from datetime import date, datetime, timezone

from cadence.core.ingest.normalize import ingest_failure, ingest_success, observed_success_rate_for
from cadence.models.tables import Customer, Cycle, IssuerHealth, Mandate, Run

NOW = datetime(2026, 1, 27, tzinfo=timezone.utc)


def _fixtures(session):
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
    )
    session.add(cycle)
    session.flush()
    return run, customer, mandate, cycle


def test_ingest_failure_is_idempotent_on_cycle_attempt_run(session):
    run, customer, mandate, cycle = _fixtures(session)
    fev1 = ingest_failure(
        session,
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=customer.id,
        attempt_no=1,
        occurred_at=NOW,
        amount_paise=100000,
        raw_code="INSUFFICIENT_FUNDS",
        gateway_desc="low balance",
        run_id=run.id,
    )
    fev2 = ingest_failure(
        session,
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=customer.id,
        attempt_no=1,
        occurred_at=NOW,
        amount_paise=100000,
        raw_code="INSUFFICIENT_FUNDS",
        gateway_desc="low balance",
        run_id=run.id,
    )
    assert fev1.id == fev2.id


def test_ingest_success_is_idempotent(session):
    run, customer, mandate, cycle = _fixtures(session)
    a1 = ingest_success(
        session, cycle_id=cycle.id, attempt_no=1, presented_at=NOW, amount_paise=100000, run_id=run.id
    )
    a2 = ingest_success(
        session, cycle_id=cycle.id, attempt_no=1, presented_at=NOW, amount_paise=100000, run_id=run.id
    )
    assert a1.id == a2.id


def test_observed_success_rate_reads_issuer_health(session):
    _, customer, _, _ = _fixtures(session)
    session.add(IssuerHealth(issuer_code="HDFC", as_of_date=date(2026, 1, 27), observed_success_rate="0.42", is_outage=True))
    session.flush()
    rate = observed_success_rate_for(session, customer.id, date(2026, 1, 27))
    assert rate == 0.42
