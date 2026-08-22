"""The ledger is append-only — docs/03-DATA-MODEL.md, CLAUDE.md rule 3."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import ProgrammingError

from cadence.models.tables import Ledger, Run


def _make_ledger_row(session) -> Ledger:
    run = Run(mode="AGENT", corpus_id="cor_test", seed=1, policy_config_hash="x")
    session.add(run)
    session.flush()
    row = Ledger(
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_type="DECISION",
        run_id=run.id,
        rationale="test row",
        payload={},
    )
    session.add(row)
    session.flush()
    return row


def test_ledger_update_is_rejected(session):
    row = _make_ledger_row(session)
    row.rationale = "mutated"
    with pytest.raises(ProgrammingError, match="append-only"):
        session.flush()


def test_ledger_delete_is_rejected(session):
    row = _make_ledger_row(session)
    session.delete(row)
    with pytest.raises(ProgrammingError, match="append-only"):
        session.flush()
