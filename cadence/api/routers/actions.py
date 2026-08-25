"""Mutating merchant-control endpoints — docs/08-API-CONTRACT.md "Actions".

Kept separate from reads.py (read-only) since these write to the ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cadence.api.deps import get_db
from cadence.core.compliance import kill_switch
from cadence.core.ledger import writer as ledger
from cadence.core.policy.cancellation import cancel_pending_for_cycle
from cadence.models.tables import Customer, Cycle

router = APIRouter()


@router.post("/cycles/{cycle_id}/cancel-pending")
def cancel_pending(cycle_id: str, run_id: str, db: Session = Depends(get_db)):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail=f"unknown cycle_id {cycle_id}")
    cancelled = cancel_pending_for_cycle(
        db,
        cycle_id=cycle_id,
        run_id=run_id,
        reason="MERCHANT_CANCELLED",
        now=datetime.now(timezone.utc),
    )
    db.commit()
    return {"cancelled": cancelled}


@router.post("/customers/{customer_id}/opt-out")
def opt_out(customer_id: str, run_id: str, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"unknown customer_id {customer_id}")
    now = datetime.now(timezone.utc)
    customer.opted_out_at = now
    ledger.record(
        db, event_type="CUSTOMER_OPTED_OUT", run_id=run_id, occurred_at=now,
        rationale="Customer opted out of all contact via the merchant dashboard.",
        customer_id=customer.id,
    )
    db.commit()
    return {"opted_out_at": now}


@router.post("/merchant/pause-automation")
def pause_automation():
    kill_switch.pause_merchant()
    return {"paused": True}


@router.post("/merchant/resume-automation")
def resume_automation():
    kill_switch.resume_merchant()
    return {"paused": False}
