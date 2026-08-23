"""Normalises a raw presentment outcome into FailureEvent/Attempt rows.

Idempotent on (cycle_id, attempt_no, run_id) — see docs/02-ARCHITECTURE.md.
Callers (webhook handler in live mode, replay orchestration in eval mode)
pass primitive values only; this module never touches sim/ ground truth.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from cadence.core.ledger import writer as ledger
from cadence.models.tables import Attempt, Customer, FailureEvent, IssuerHealth


def _find_attempt(session: Session, cycle_id: str, attempt_no: int, run_id: str) -> Attempt | None:
    return (
        session.query(Attempt)
        .filter_by(cycle_id=cycle_id, attempt_no=attempt_no, run_id=run_id)
        .one_or_none()
    )


def ingest_success(
    session: Session,
    *,
    cycle_id: str,
    attempt_no: int,
    presented_at: datetime,
    amount_paise: int,
    run_id: str,
) -> Attempt:
    existing = _find_attempt(session, cycle_id, attempt_no, run_id)
    if existing is not None:
        return existing

    attempt = Attempt(
        cycle_id=cycle_id,
        attempt_no=attempt_no,
        presented_at=presented_at,
        succeeded=True,
        run_id=run_id,
    )
    session.add(attempt)
    session.flush()

    ledger.record(
        session,
        event_type="PRESENTMENT_RESULT",
        run_id=run_id,
        occurred_at=presented_at,
        rationale=f"Presentment succeeded for {amount_paise} paise on attempt {attempt_no}.",
        payload={"succeeded": True, "amount_paise": amount_paise, "attempt_no": attempt_no},
        cycle_id=cycle_id,
        amount_paise=amount_paise,
    )
    return attempt


def ingest_failure(
    session: Session,
    *,
    mandate_id: str,
    cycle_id: str,
    customer_id: str,
    attempt_no: int,
    occurred_at: datetime,
    amount_paise: int,
    raw_code: str,
    gateway_desc: str | None,
    run_id: str,
) -> FailureEvent:
    existing_attempt = _find_attempt(session, cycle_id, attempt_no, run_id)
    if existing_attempt is not None:
        existing_fev = (
            session.query(FailureEvent).filter_by(attempt_id=existing_attempt.id).one_or_none()
        )
        if existing_fev is not None:
            return existing_fev
        attempt = existing_attempt
    else:
        attempt = Attempt(
            cycle_id=cycle_id,
            attempt_no=attempt_no,
            presented_at=occurred_at,
            succeeded=False,
            gateway_code=raw_code,
            gateway_desc=gateway_desc,
            run_id=run_id,
        )
        session.add(attempt)
        session.flush()

    fev = FailureEvent(
        attempt_id=attempt.id,
        mandate_id=mandate_id,
        cycle_id=cycle_id,
        customer_id=customer_id,
        raw_code=raw_code,
        amount_paise=amount_paise,
        occurred_at=occurred_at,
    )
    session.add(fev)
    session.flush()

    ledger.record(
        session,
        event_type="FAILURE_INGESTED",
        run_id=run_id,
        occurred_at=occurred_at,
        rationale=f"Presentment failed: {raw_code}.",
        payload={"raw_code": raw_code, "gateway_desc": gateway_desc, "attempt_no": attempt_no},
        mandate_id=mandate_id,
        cycle_id=cycle_id,
        customer_id=customer_id,
        amount_paise=amount_paise,
    )
    return fev


def observed_success_rate_for(session: Session, customer_id: str, on_date: date) -> float | None:
    """The only issuer-health signal core/ may read — never the ground-truth outage flag."""
    customer = session.get(Customer, customer_id)
    if customer is None:
        return None
    row = (
        session.query(IssuerHealth)
        .filter_by(issuer_code=customer.issuer_code, as_of_date=on_date)
        .one_or_none()
    )
    return float(row.observed_success_rate) if row is not None else None
