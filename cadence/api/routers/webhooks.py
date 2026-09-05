"""POST /webhooks/razorpay — docs/08-API-CONTRACT.md."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from cadence.api.deps import get_db, get_merchant_id
from cadence.core.classify.record import classify_and_record
from cadence.core.ingest.normalize import ingest_failure, ingest_success, observed_success_rate_for
from cadence.core.ingest.schemas import RazorpayWebhookEvent
from cadence.core.ingest.signature import verify_signature
from cadence.core.ledger import writer as ledger
from cadence.models.tables import Ledger, Run

router = APIRouter()

FAILURE_EVENTS = {"payment.failed", "subscription.pending", "subscription.halted"}
SUCCESS_EVENTS = {"subscription.charged"}


def _get_or_create_live_run(session: Session, merchant_id: str) -> Run:
    run = session.query(Run).filter_by(mode="LIVE", merchant_id=merchant_id).first()
    if run is not None:
        return run
    run = Run(merchant_id=merchant_id, mode="LIVE", corpus_id="live", seed=0, policy_config_hash="live")
    session.add(run)
    session.flush()
    return run


def _already_processed(session: Session, event_id: str, run_id: str) -> bool:
    return (
        session.query(Ledger)
        .filter(Ledger.run_id == run_id, Ledger.payload["webhook_event_id"].astext == event_id)
        .first()
        is not None
    )


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: Session = Depends(get_db),
    merchant_id: str = Depends(get_merchant_id),
):
    raw_body = await request.body()
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    if not verify_signature(raw_body, x_razorpay_signature, secret):
        run = _get_or_create_live_run(db, merchant_id)
        ledger.record(
            db,
            event_type="FAILURE_INGESTED",
            run_id=run.id,
            occurred_at=datetime.now(timezone.utc),
            rationale="Rejected a webhook with an invalid signature.",
            payload={"reason": "INVALID_SIGNATURE"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    event = RazorpayWebhookEvent.model_validate_json(raw_body)
    run = _get_or_create_live_run(db, merchant_id)

    if _already_processed(db, event.event_id, run.id):
        db.commit()
        return {"received": True, "failure_event_id": None}

    occurred_at = datetime.fromisoformat(event.payload.occurred_at)
    failure_event_id = None

    if event.event in SUCCESS_EVENTS or event.payload.succeeded:
        ingest_success(
            db,
            cycle_id=event.payload.cycle_id,
            attempt_no=event.payload.attempt_no,
            presented_at=occurred_at,
            amount_paise=event.payload.amount_paise,
            run_id=run.id,
        )
    elif event.event in FAILURE_EVENTS:
        fev = ingest_failure(
            db,
            mandate_id=event.payload.mandate_id,
            cycle_id=event.payload.cycle_id,
            customer_id=event.payload.customer_id,
            attempt_no=event.payload.attempt_no,
            occurred_at=occurred_at,
            amount_paise=event.payload.amount_paise,
            raw_code=event.payload.raw_code or "UNKNOWN",
            gateway_desc=event.payload.gateway_desc,
            run_id=run.id,
        )
        failure_event_id = fev.id
        observed_rate = observed_success_rate_for(db, event.payload.customer_id, occurred_at.date())
        classify_and_record(
            db,
            failure_event=fev,
            gateway_desc=event.payload.gateway_desc,
            observed_success_rate=observed_rate,
            run_id=run.id,
        )

    # Mark this webhook event as processed regardless of branch taken.
    ledger.record(
        db,
        event_type="WEBHOOK_RECEIVED",
        run_id=run.id,
        occurred_at=occurred_at,
        rationale=f"Webhook {event.event} processed.",
        payload={"webhook_event_id": event.event_id},
    )
    db.commit()
    return {"received": True, "failure_event_id": failure_event_id}
