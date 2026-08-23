"""Read-model endpoints for the dashboard — docs/08-API-CONTRACT.md."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from cadence.api.deps import get_db
from cadence.eval.auditor import audit
from cadence.eval.metrics import captured_of_headroom, compute_run_metrics
from cadence.models.tables import (
    Classification,
    Cycle,
    Customer,
    Decision,
    FailureEvent,
    Ledger,
    Mandate,
    Prediction,
    Run,
)

router = APIRouter()


@router.get("/runs")
def list_runs(mode: str | None = None, limit: int = 20, db: Session = Depends(get_db)):
    q = db.query(Run)
    if mode:
        q = q.filter(Run.mode == mode)
    runs = q.order_by(desc(Run.started_at)).limit(limit).all()
    return {
        "runs": [
            {"id": r.id, "mode": r.mode, "corpus_id": r.corpus_id, "seed": r.seed, "metrics": r.metrics}
            for r in runs
        ]
    }


@router.get("/runs/{run_id}/metrics")
def run_metrics(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")
    return compute_run_metrics(db, run_id)


@router.get("/runs/compare")
def compare_runs(baseline: str, agent: str, oracle: str, db: Session = Depends(get_db)):
    for run_id in (baseline, agent, oracle):
        if db.get(Run, run_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")

    def _clean(v):
        return None if isinstance(v, float) and (v != v) else v  # NaN check, no import needed

    m_baseline = compute_run_metrics(db, baseline)
    m_agent = compute_run_metrics(db, agent)
    m_oracle = compute_run_metrics(db, oracle)

    violations = {
        run_id: len(audit(db, run_id)["violations"]) for run_id in (baseline, agent, oracle)
    }

    def row(metric, label, unit="ratio", higher_is_better=True):
        b, a, o = m_baseline[metric], m_agent[metric], m_oracle[metric]
        captured = captured_of_headroom(b, a, o)
        return {
            "metric": metric, "label": label, "baseline": _clean(b), "agent": _clean(a), "oracle": _clean(o),
            "unit": unit, "higher_is_better": higher_is_better,
            "delta_abs": _clean(a - b), "delta_rel": _clean((a - b) / b) if b else None,
            "captured_of_available": _clean(captured),
        }

    return {
        "rows": [
            row("recovery_rate", "Recovery rate"),
            row("recovered_paise", "Recovered", unit="paise"),
            row("presentments_total", "Presentments used", unit="count", higher_is_better=False),
            row("presentments_per_recovery", "Per successful recovery", unit="count", higher_is_better=False),
            row("messages_total", "Messages sent", unit="count", higher_is_better=False),
            row("messages_per_recovery", "Per successful recovery", unit="count", higher_is_better=False),
            row("wasted_presentments", "Wasted on terminal cases", unit="count", higher_is_better=False),
            {
                "metric": "compliance_violations", "label": "Compliance violations",
                "baseline": violations[baseline], "agent": violations[agent], "oracle": violations[oracle],
                "unit": "count", "higher_is_better": False,
                "delta_abs": violations[agent] - violations[baseline], "delta_rel": None,
                "captured_of_available": None,
            },
        ],
        "run_ids": {"baseline": baseline, "agent": agent, "oracle": oracle},
    }


@router.get("/portfolio")
def portfolio(run_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import func

    from cadence.models.tables import Attempt, PendingAction

    m = compute_run_metrics(db, run_id)
    needs_you = (
        db.query(Decision)
        .filter(Decision.run_id == run_id, Decision.action_type == "ESCALATE_TO_MERCHANT")
        .count()
    )

    root_cause_counts = (
        db.query(Classification.root_cause, func.count(Classification.id))
        .join(FailureEvent, Classification.failure_event_id == FailureEvent.id)
        .join(Attempt, FailureEvent.attempt_id == Attempt.id)
        .filter(Attempt.run_id == run_id)
        .group_by(Classification.root_cause)
        .order_by(func.count(Classification.id).desc())
        .all()
    )

    # Not a literal wall-clock "next 48 hours" (this is a completed batch
    # simulation on a virtual clock) — counts of work still open at the end
    # of the run, grouped the same way the doc's "NEXT 48 HOURS" panel does.
    pending_by_action = (
        db.query(Decision.action_type, func.count(PendingAction.id))
        .join(PendingAction, PendingAction.decision_id == Decision.id)
        .filter(Decision.run_id == run_id, PendingAction.state == "PENDING")
        .group_by(Decision.action_type)
        .all()
    )

    return {
        "at_risk_paise": m["at_risk_paise"],
        "recovered_paise": m["recovered_paise"],
        "in_recovery_count": m["failed_cycles"] - m["recovered_cycles"],
        "recovered_count": m["recovered_cycles"],
        "escalated_to_you": needs_you,
        "recovery_rate": m["recovery_rate"],
        "why_failing": [{"root_cause": rc, "count": c} for rc, c in root_cause_counts],
        "pending_by_action": {action_type: c for action_type, c in pending_by_action},
    }


@router.get("/cycles/{cycle_id}/month-strip")
def cycle_month_strip(cycle_id: str, run_id: str, db: Session = Depends(get_db)):
    """The signature element's data source — docs/09-DASHBOARD.md.

    Day-of-month success density for this customer (blended customer/population
    term, same math as core/predict/model.py), plus this run's own presentment
    attempt days for the cycle and the failure date.
    """
    from cadence.core.predict.config import load_model_config
    from cadence.core.predict.model import customer_term, population_term
    from cadence.core.predict.service import IST_OFFSET, _customer_successful_doms
    from cadence.models.tables import Attempt

    cycle = db.get(Cycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail=f"unknown cycle_id {cycle_id}")
    mandate = db.get(Mandate, cycle.mandate_id)
    customer = db.get(Customer, mandate.customer_id) if mandate else None

    fev = (
        db.query(FailureEvent)
        .join(Attempt, FailureEvent.attempt_id == Attempt.id)
        .filter(FailureEvent.cycle_id == cycle_id, Attempt.run_id == run_id)
        .order_by(FailureEvent.occurred_at)
        .first()
    )
    failure_day = None
    day_rates = [0.0] * 31
    if fev is not None and customer is not None:
        cfg = load_model_config()
        failure_day = (fev.occurred_at + IST_OFFSET).day
        doms = _customer_successful_doms(db, customer.id, fev.occurred_at, run_id)
        use_customer = len(doms) >= cfg["min_history_successes"]
        for d in range(1, 32):
            c = customer_term(d, doms, cfg["circular_gaussian_sigma_days"]) if use_customer else 0.0
            p = population_term(d, cfg["population_dom_prior"])
            day_rates[d - 1] = (0.7 * c + 0.3 * p) if use_customer else p

    attempt_rows = (
        db.query(Attempt.presented_at)
        .filter(Attempt.cycle_id == cycle_id, Attempt.run_id == run_id, Attempt.attempt_no > 1)
        .all()
    )
    attempt_days = sorted({(presented_at + IST_OFFSET).day for (presented_at,) in attempt_rows})

    return {"day_rates": day_rates, "failure_day": failure_day, "attempt_days": attempt_days}


@router.get("/runs/compare/exemplar")
def compare_exemplar(baseline: str, agent: str, db: Session = Depends(get_db)):
    """Picks the cycle for the comparison screen's hero month strip: one the
    agent recovered and the baseline did not, preferring the most baseline
    attempts (the starkest hollow-markers-in-the-dead-zone contrast)."""
    from cadence.models.tables import Attempt

    agent_recovered = {
        row[0]
        for row in db.query(Ledger.cycle_id).filter(Ledger.run_id == agent, Ledger.event_type == "RECOVERED").all()
    }
    baseline_recovered = {
        row[0]
        for row in db.query(Ledger.cycle_id).filter(Ledger.run_id == baseline, Ledger.event_type == "RECOVERED").all()
    }
    candidates = agent_recovered - baseline_recovered

    best_cycle_id = None
    best_score = -1
    for cid in candidates:
        n_baseline_attempts = (
            db.query(Attempt)
            .filter(Attempt.cycle_id == cid, Attempt.run_id == baseline, Attempt.attempt_no > 1)
            .count()
        )
        if n_baseline_attempts > best_score:
            best_score = n_baseline_attempts
            best_cycle_id = cid

    if best_cycle_id is None:
        raise HTTPException(status_code=404, detail="no exemplar cycle found (agent recovered, baseline did not)")
    return {"cycle_id": best_cycle_id}


@router.get("/cycles")
def list_cycles(
    run_id: str,
    state: str | None = None,
    sort: str = "amount_desc",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    from cadence.models.tables import Attempt

    cycle_ids = [
        row[0]
        for row in db.query(Attempt.cycle_id).filter(Attempt.run_id == run_id).distinct().all()
    ]
    q = db.query(Cycle).filter(Cycle.id.in_(cycle_ids))
    if state:
        q = q.filter(Cycle.state == state)
    if sort == "amount_desc":
        q = q.order_by(desc(Cycle.amount_paise))
    cycles = q.offset((page - 1) * page_size).limit(page_size).all()

    rows = []
    for c in cycles:
        mandate = db.get(Mandate, c.mandate_id)
        rows.append({
            "cycle_id": c.id, "customer_id": mandate.customer_id if mandate else None,
            "amount_paise": c.amount_paise, "state": c.state,
            "presentations_used": c.presentations_used,
        })
    return {"rows": rows, "page": page, "page_size": page_size}


@router.get("/cycles/{cycle_id}")
def cycle_timeline(cycle_id: str, run_id: str, db: Session = Depends(get_db)):
    cycle = db.get(Cycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail=f"unknown cycle_id {cycle_id}")
    mandate = db.get(Mandate, cycle.mandate_id)
    customer = db.get(Customer, mandate.customer_id) if mandate else None

    from cadence.models.tables import Attempt as _Attempt

    # FailureEvent has no run_id column directly, but each run creates its
    # own Attempt (and therefore its own FailureEvent row via the unique
    # attempt_id FK) even for "the same" real-world failure — so this MUST
    # be scoped through Attempt.run_id, or we can silently pick a different
    # arm's (e.g. baseline's, never-classified) FailureEvent row.
    fev = (
        db.query(FailureEvent)
        .join(_Attempt, FailureEvent.attempt_id == _Attempt.id)
        .filter(FailureEvent.cycle_id == cycle_id, _Attempt.run_id == run_id)
        .order_by(FailureEvent.occurred_at)
        .first()
    )
    classification = None
    prediction = None
    if fev is not None:
        classification = db.query(Classification).filter_by(failure_event_id=fev.id).first()
        prediction = db.query(Prediction).filter_by(failure_event_id=fev.id).order_by(desc(Prediction.id)).first()

    ledger_rows = (
        db.query(Ledger)
        .filter(Ledger.run_id == run_id, Ledger.cycle_id == cycle_id)
        .order_by(Ledger.id)
        .all()
    )

    from cadence.models.tables import Decision, PendingAction

    next_pending = None
    if fev is not None:
        next_pending = (
            db.query(PendingAction)
            .join(Decision, PendingAction.decision_id == Decision.id)
            .filter(Decision.run_id == run_id, Decision.failure_event_id == fev.id, PendingAction.state == "PENDING")
            .order_by(PendingAction.run_at)
            .first()
        )
    next_action = None
    if next_pending is not None:
        decision = db.get(Decision, next_pending.decision_id)
        next_action = {
            "action_type": decision.action_type,
            "scheduled_for": next_pending.run_at,
            "cancellable": True,
        }

    return {
        "cycle": {"id": cycle.id, "amount_paise": cycle.amount_paise, "state": cycle.state,
                  "presentations_used": cycle.presentations_used, "period_start": cycle.period_start,
                  "period_end": cycle.period_end},
        "mandate": {"id": mandate.id, "rail": mandate.rail, "status": mandate.status} if mandate else None,
        "customer": {"id": customer.id, "name": customer.name, "issuer_code": customer.issuer_code} if customer else None,
        "classification": (
            {"root_cause": classification.root_cause, "confidence": str(classification.confidence),
             "matched_rule": classification.matched_rule}
            if classification else None
        ),
        "prediction": (
            {"curve": prediction.curve, "best_day_offset": prediction.best_day_offset,
             "basis": prediction.basis, "feature_contributions": prediction.feature_contributions}
            if prediction else None
        ),
        "timeline": [
            {"at": row.occurred_at, "event_type": row.event_type, "rationale": row.rationale,
             "amount_paise": row.amount_paise, "channel": row.channel}
            for row in ledger_rows
        ],
        "next_action": next_action,
    }


@router.get("/ledger")
def ledger_view(
    run_id: str | None = None,
    cycle_id: str | None = None,
    customer_id: str | None = None,
    event_type: str | None = None,
    blocked_only: bool = False,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Ledger)
    if run_id:
        q = q.filter(Ledger.run_id == run_id)
    if cycle_id:
        q = q.filter(Ledger.cycle_id == cycle_id)
    if customer_id:
        q = q.filter(Ledger.customer_id == customer_id)
    if event_type:
        q = q.filter(Ledger.event_type == event_type)
    if blocked_only:
        q = q.filter(Ledger.event_type == "GATE_BLOCKED")
    rows = q.order_by(desc(Ledger.id)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "rows": [
            {"id": r.id, "occurred_at": r.occurred_at, "event_type": r.event_type, "cycle_id": r.cycle_id,
             "customer_id": r.customer_id, "mandate_id": r.mandate_id, "amount_paise": r.amount_paise,
             "rationale": r.rationale, "payload": r.payload}
            for r in rows
        ],
        "page": page, "page_size": page_size,
    }


@router.get("/compliance/report")
def compliance_report(run_id: str, db: Session = Depends(get_db)):
    from cadence.core.compliance.config import load_policy_constants

    checks_run = db.query(Ledger).filter(Ledger.run_id == run_id, Ledger.event_type.in_(["DECISION", "GATE_BLOCKED"])).count()
    blocked_rows = db.query(Ledger).filter(Ledger.run_id == run_id, Ledger.event_type == "GATE_BLOCKED").all()
    by_code: dict[str, int] = {}
    for row in blocked_rows:
        for block in (row.payload or {}).get("blocks", []):
            by_code[block["code"]] = by_code.get(block["code"], 0) + 1

    audit_result = audit(db, run_id)
    constants = load_policy_constants()

    return {
        "checks_run": checks_run,
        "actions_blocked": len(blocked_rows),
        "blocked_by_code": by_code,
        "independent_audit": {
            "violations_found": len(audit_result["violations"]),
            "rows_audited": audit_result["rows_audited"],
            "auditor_version": audit_result["auditor_version"],
        },
        "constants": [
            {"key": k, "value": c.value, "source": c.source} for k, c in constants.constants.items()
        ],
    }
