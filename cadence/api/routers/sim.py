"""Simulation control — docs/08-API-CONTRACT.md "Simulation control".

`POST /sim/corpus` and `POST /sim/run` wrap the same generator/eval-harness
machinery `make corpus`/`make eval` use, so the dashboard's "load corpus" /
"run" buttons produce byte-identical results to the CLI path.

`POST /sim/tick` and `POST /sim/inject` are the live-demo controls — M8.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cadence.api.deps import get_db
from cadence.core.execute.scheduler import run_due_actions
from cadence.eval.report import _ensure_corpus_persisted
from cadence.eval.runners import load_corpus, run_agent, run_baseline, run_oracle
from cadence.models.tables import CorpusMeta, Ledger, Run
from cadence.sim import live_clock
from cadence.sim.clock import at_simulated_time
from cadence.sim.generator import DAYS, START_DATE
from cadence.sim.inject import CASE_IDS, _build_adapters, inject_case

router = APIRouter()


class CorpusRequest(BaseModel):
    seed: int = 42
    n_customers: int = 300


@router.post("/sim/corpus", status_code=201)
def create_corpus(body: CorpusRequest, db: Session = Depends(get_db)):
    _ensure_corpus_persisted(body.seed, body.n_customers)
    meta = db.query(CorpusMeta).filter_by(seed=body.seed, n_customers=body.n_customers).first()
    if meta is None:
        raise HTTPException(status_code=500, detail="corpus generation did not persist corpus_meta")
    return {
        "corpus_id": meta.id,
        "stats": {
            "n_customers": meta.n_customers, "n_mandates": meta.n_mandates,
            "n_cycles": meta.n_cycles, "cause_mix": meta.cause_mix,
        },
    }


class RunRequest(BaseModel):
    corpus_id: str
    mode: str
    seed: int
    n_customers: int = 300


@router.post("/sim/run", status_code=201)
def create_run(body: RunRequest, db: Session = Depends(get_db)):
    if body.mode not in ("BASELINE", "AGENT", "ORACLE"):
        raise HTTPException(status_code=400, detail="mode must be BASELINE, AGENT, or ORACLE")
    meta = db.get(CorpusMeta, body.corpus_id)
    if meta is None or meta.seed != body.seed:
        raise HTTPException(
            status_code=404,
            detail=f"corpus {body.corpus_id} not found for seed {body.seed} — call POST /sim/corpus first",
        )

    g = load_corpus(body.seed, n_customers=meta.n_customers)
    runner = {"BASELINE": run_baseline, "AGENT": run_agent, "ORACLE": run_oracle}[body.mode]
    result = runner(db, g, body.seed)

    from cadence.eval.metrics import compute_run_metrics

    metrics = compute_run_metrics(db, result.run_id)
    run_row = db.get(Run, result.run_id)
    run_row.metrics = metrics
    db.commit()
    return {"run_id": result.run_id, "metrics": metrics}


class TickRequest(BaseModel):
    run_id: str
    days: int = 1


@router.post("/sim/tick")
def tick(body: TickRequest, db: Session = Depends(get_db)):
    run = db.get(Run, body.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id {body.run_id}")

    default_start = at_simulated_time(START_DATE + timedelta(days=DAYS + 3))
    current = live_clock.get_now(body.run_id, default=default_start)
    new_now = current + timedelta(days=body.days)

    before_max_id = (
        db.query(Ledger.id).filter(Ledger.run_id == body.run_id).order_by(Ledger.id.desc()).limit(1).scalar()
    ) or 0

    adapters = _build_adapters(db, body.run_id)
    executed = run_due_actions(db, now=new_now, run_id=body.run_id, adapters=adapters)
    db.commit()
    live_clock.set_now(body.run_id, new_now)

    events = [
        {"id": row.id, "event_type": row.event_type, "rationale": row.rationale, "cycle_id": row.cycle_id}
        for row in db.query(Ledger)
        .filter(Ledger.run_id == body.run_id, Ledger.id > before_max_id)
        .order_by(Ledger.id)
        .all()
    ]
    return {"now": new_now, "executed": executed, "events": events}


class InjectRequest(BaseModel):
    run_id: str
    case: str
    mandate_id: str | None = None


@router.post("/sim/inject")
def inject(body: InjectRequest, db: Session = Depends(get_db)):
    if body.case not in CASE_IDS:
        raise HTTPException(status_code=400, detail=f"unknown case {body.case!r}; must be one of {CASE_IDS}")
    default_start = at_simulated_time(START_DATE + timedelta(days=DAYS + 3))
    now = live_clock.get_now(body.run_id, default=default_start)
    try:
        result = inject_case(db, run_id=body.run_id, case=body.case, mandate_id=body.mandate_id, now=now)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    live_clock.set_now(body.run_id, now)
    return {"injected": True, **result}
