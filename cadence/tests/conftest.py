"""Shared fixtures. Tests run against a dedicated Postgres database
(TEST_DATABASE_URL), separate from the dev corpus DB — no sqlite substitution,
since the ledger append-only trigger is a Postgres feature."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://cadence:cadence@localhost:5432/cadence_test"
)
engine = create_engine(TEST_DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


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
