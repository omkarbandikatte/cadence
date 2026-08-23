"""Persists a Classification row for a FailureEvent and writes the ledger row."""
from __future__ import annotations

from sqlalchemy.orm import Session

from cadence.core.classify.classifier import classify
from cadence.core.ledger import writer as ledger
from cadence.models.tables import Classification, FailureEvent


def classify_and_record(
    session: Session,
    *,
    failure_event: FailureEvent,
    gateway_desc: str | None,
    observed_success_rate: float | None,
    run_id: str,
) -> Classification:
    result = classify(failure_event.raw_code, gateway_desc, observed_success_rate)

    row = Classification(
        failure_event_id=failure_event.id,
        root_cause=result.root_cause,
        subtype=result.subtype,
        disposition=result.disposition,
        confidence=str(round(result.confidence, 2)),
        matched_rule=result.matched_rule,
    )
    session.add(row)
    session.flush()

    rationale = (
        f"Classified as {result.root_cause} ({result.disposition}) via rule "
        f"{result.matched_rule}, confidence {result.confidence:.2f}."
    )
    if result.corroboration_note:
        rationale += " " + result.corroboration_note

    ledger.record(
        session,
        event_type="CLASSIFIED",
        run_id=run_id,
        occurred_at=failure_event.occurred_at,
        rationale=rationale,
        payload={
            "root_cause": result.root_cause,
            "subtype": result.subtype,
            "disposition": result.disposition,
            "confidence": result.confidence,
            "matched_rule": result.matched_rule,
            "co_occurring_issuer_degradation": result.co_occurring_issuer_degradation,
        },
        mandate_id=failure_event.mandate_id,
        cycle_id=failure_event.cycle_id,
        customer_id=failure_event.customer_id,
    )
    return row
