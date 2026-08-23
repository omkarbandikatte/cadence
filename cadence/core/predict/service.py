"""DB-facing wrapper around core/predict/model.py. Only invoked for
BALANCE_SHORTFALL / ISSUER_DEGRADED causes — see docs/02-ARCHITECTURE.md."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from cadence.core.ledger import writer as ledger
from cadence.core.predict.config import load_gap_term_prior, load_model_config
from cadence.core.predict.model import PredictionInputs, predict
from cadence.models.tables import Attempt, Cycle, Customer, FailureEvent, IssuerHealth, Mandate, Prediction

IST_OFFSET = timedelta(hours=5, minutes=30)


@dataclass
class PredictionOutcome:
    row: Prediction
    best_day_offset: int | None
    second_best_day_offset: int | None
    basis: str


def _customer_successful_doms(session: Session, customer_id: str, before, run_id: str) -> tuple[int, ...]:
    rows = (
        session.query(Attempt.presented_at)
        .join(Cycle, Attempt.cycle_id == Cycle.id)
        .join(Mandate, Cycle.mandate_id == Mandate.id)
        .filter(
            Mandate.customer_id == customer_id,
            Attempt.succeeded.is_(True),
            Attempt.presented_at < before,
            Attempt.run_id == run_id,
        )
        .all()
    )
    return tuple((presented_at + IST_OFFSET).day for (presented_at,) in rows)


def _issuer_rate_by_offset(session: Session, issuer_code: str, failure_date, days: int = 15) -> dict[int, float]:
    rates: dict[int, float] = {}
    rows = (
        session.query(IssuerHealth.as_of_date, IssuerHealth.observed_success_rate)
        .filter(
            IssuerHealth.issuer_code == issuer_code,
            IssuerHealth.as_of_date >= failure_date,
            IssuerHealth.as_of_date < failure_date + timedelta(days=days),
        )
        .all()
    )
    for as_of_date, rate in rows:
        offset = (as_of_date - failure_date).days
        rates[offset] = float(rate)
    return rates


def predict_for_failure(
    session: Session,
    *,
    failure_event: FailureEvent,
    co_occurring_issuer_degradation: bool,
    run_id: str,
) -> PredictionOutcome:
    cycle = session.get(Cycle, failure_event.cycle_id)
    mandate = session.get(Mandate, failure_event.mandate_id)
    customer = session.get(Customer, failure_event.customer_id)

    cfg = load_model_config()
    failure_date = failure_event.occurred_at.date()

    inputs = PredictionInputs(
        failure_date=failure_date,
        cycle_period_end=cycle.period_end,
        customer_successful_doms=_customer_successful_doms(session, customer.id, failure_event.occurred_at, run_id),
        population_dom_prior=cfg["population_dom_prior"],
        gap_term_prior=load_gap_term_prior(),
        issuer_success_rate_by_offset=_issuer_rate_by_offset(session, customer.issuer_code, failure_date),
        co_occurring_issuer_degradation=co_occurring_issuer_degradation,
        weights=cfg["weights"],
        min_history_successes=cfg["min_history_successes"],
        circular_gaussian_sigma_days=cfg["circular_gaussian_sigma_days"],
        min_cooling_off_days=cfg["min_cooling_off_days"],
        reserve_days_before_cycle_end=cfg["reserve_days_before_cycle_end"],
        pre_debit_notice_hours=cfg["pre_debit_notice_hours"],
    )
    result = predict(inputs)

    row = Prediction(
        failure_event_id=failure_event.id,
        curve=result.curve,
        best_day_offset=result.best_day_offset if result.best_day_offset is not None else -1,
        best_p=str(round(result.best_p, 3)),
        basis=result.basis,
        feature_contributions=result.feature_contributions,
    )
    session.add(row)
    session.flush()

    if result.best_day_offset is None:
        rationale = "No feasible presentment window remains before the cycle closes."
    else:
        target_date = failure_date + timedelta(days=result.best_day_offset)
        rationale = (
            f"Best day to present is {target_date.isoformat()} (+{result.best_day_offset}d), "
            f"basis {result.basis}, p={result.best_p:.2f}."
        )

    ledger.record(
        session,
        event_type="PREDICTED",
        run_id=run_id,
        occurred_at=failure_event.occurred_at,
        rationale=rationale,
        payload={"best_day_offset": result.best_day_offset, "basis": result.basis, "best_p": result.best_p},
        mandate_id=mandate.id,
        cycle_id=cycle.id,
        customer_id=customer.id,
    )

    return PredictionOutcome(
        row=row,
        best_day_offset=result.best_day_offset,
        second_best_day_offset=result.second_best_day_offset,
        basis=result.basis,
    )
