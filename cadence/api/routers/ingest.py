"""POST /ingest/replay — batch corpus replay used by the eval harness and the
demo's "load corpus" button. Lives in api/, not core/: this is the only place
allowed to bridge sim/ ground truth into the same ingest+classify functions
core/ uses for live webhooks. See docs/02-ARCHITECTURE.md, docs/08.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cadence.api.deps import get_db
from cadence.core.classify.record import classify_and_record
from cadence.core.ingest.normalize import ingest_failure, ingest_success, observed_success_rate_for
from cadence.core.ingest.schemas import ReplayRequest, ReplayResponse
from cadence.models.tables import CorpusMeta
from cadence.sim.clock import at_simulated_time
from cadence.sim.generator import generate_corpus

router = APIRouter()


@router.post("/ingest/replay", response_model=ReplayResponse)
def replay(req: ReplayRequest, db: Session = Depends(get_db)) -> ReplayResponse:
    corpus_meta = db.get(CorpusMeta, req.corpus_id)
    if corpus_meta is None:
        raise HTTPException(status_code=404, detail=f"unknown corpus_id {req.corpus_id}")

    g = generate_corpus(corpus_meta.seed, n_customers=corpus_meta.n_customers, write_to_db=False)

    events_queued = 0
    for cyc_id in g.cycle_order:
        cycle = g.world.cycles[cyc_id]
        mandate = g.world.mandates[cycle.mandate_id]
        presented_at = at_simulated_time(cycle.debit_date)

        if g.cycle_status[cyc_id] == "SUCCESS":
            ingest_success(
                db,
                cycle_id=cyc_id,
                attempt_no=1,
                presented_at=presented_at,
                amount_paise=cycle.amount_paise,
                run_id=req.run_id,
            )
            continue

        raw_code = g.cycle_first_code[cyc_id]
        designed = g.world.designed_causes.get(cyc_id)
        gateway_desc = designed.gateway_desc if designed else None
        fev = ingest_failure(
            db,
            mandate_id=cycle.mandate_id,
            cycle_id=cyc_id,
            customer_id=mandate.customer_id,
            attempt_no=1,
            occurred_at=presented_at,
            amount_paise=cycle.amount_paise,
            raw_code=raw_code,
            gateway_desc=gateway_desc,
            run_id=req.run_id,
        )
        observed_rate = observed_success_rate_for(db, mandate.customer_id, cycle.debit_date)
        classify_and_record(
            db,
            failure_event=fev,
            gateway_desc=gateway_desc,
            observed_success_rate=observed_rate,
            run_id=req.run_id,
        )
        events_queued += 1

    db.commit()
    return ReplayResponse(run_id=req.run_id, events_queued=events_queued)
