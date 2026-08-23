"""Request/response shapes for ingest endpoints — docs/08-API-CONTRACT.md."""
from __future__ import annotations

from pydantic import BaseModel


class RazorpayFailurePayload(BaseModel):
    mandate_id: str
    cycle_id: str
    customer_id: str
    attempt_no: int
    amount_paise: int
    raw_code: str | None = None
    gateway_desc: str | None = None
    occurred_at: str  # ISO-8601
    succeeded: bool = False


class RazorpayWebhookEvent(BaseModel):
    event: str
    event_id: str
    payload: RazorpayFailurePayload


class ReplayRequest(BaseModel):
    corpus_id: str
    run_id: str
    mode: str


class ReplayResponse(BaseModel):
    run_id: str
    events_queued: int
