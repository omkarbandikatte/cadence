"""FastAPI dependency wiring."""
from __future__ import annotations

from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from cadence.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_merchant_id(x_merchant_id: str | None = Header(default=None, alias="x-merchant-id")) -> str:
    merchant_id = (x_merchant_id or "demo_merchant").strip()
    return merchant_id or "demo_merchant"
