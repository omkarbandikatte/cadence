"""Append-only ledger writer. One entrypoint: record(). See docs/03-DATA-MODEL.md
and docs/06-COMPLIANCE-GATE.md — every state change gets a row, rationale is
never empty, and the table itself refuses UPDATE/DELETE at the DB level.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from cadence.models.tables import Ledger


def record(
    session: Session,
    *,
    event_type: str,
    run_id: str,
    occurred_at: datetime,
    rationale: str,
    payload: dict | None = None,
    mandate_id: str | None = None,
    cycle_id: str | None = None,
    customer_id: str | None = None,
    decision_id: str | None = None,
    amount_paise: int | None = None,
    channel: str | None = None,
) -> Ledger:
    if not rationale:
        raise ValueError("ledger rows must carry a non-empty rationale")
    row = Ledger(
        occurred_at=occurred_at,
        event_type=event_type,
        run_id=run_id,
        mandate_id=mandate_id,
        cycle_id=cycle_id,
        customer_id=customer_id,
        decision_id=decision_id,
        amount_paise=amount_paise,
        channel=channel,
        rationale=rationale,
        payload=payload or {},
    )
    session.add(row)
    return row
