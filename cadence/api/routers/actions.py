"""Mutating merchant-control endpoints — docs/08-API-CONTRACT.md "Actions".

Kept separate from reads.py (read-only) since these write to the ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cadence.api.deps import get_db
from cadence.core.policy.cancellation import cancel_pending_for_cycle
from cadence.models.tables import Cycle

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
