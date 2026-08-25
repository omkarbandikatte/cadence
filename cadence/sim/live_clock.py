"""In-memory per-run virtual clock for the live demo — `POST /sim/tick`.

Not persisted (no `Run.current_time` column in docs/03, and a single-process
FastAPI dev/demo deployment doesn't need one). Resets on server restart,
which is fine for a live demo: the first tick for a run seeds itself from
that run's own last ledger event.
"""
from __future__ import annotations

from datetime import datetime

_LIVE_NOW: dict[str, datetime] = {}


def get_now(run_id: str, default: datetime) -> datetime:
    return _LIVE_NOW.get(run_id, default)


def set_now(run_id: str, now: datetime) -> None:
    _LIVE_NOW[run_id] = now
