"""Shared fixtures. Every test runs against the real Postgres from docker-compose
(no sqlite substitution — the ledger trigger is a Postgres feature)."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from cadence.db import SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def _check_db_reachable():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    yield


@pytest.fixture()
def session() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.rollback()
    finally:
        db.close()
