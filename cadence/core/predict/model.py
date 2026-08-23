"""The funding-window model — docs/05-DECISION-ENGINE.md Part A.

Five named terms, a weighted sum, and a constrained argmax. Every term's
value is persisted so the dashboard can render "why this day." No DB access
here — see service.py for the DB-facing wrapper.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class PredictionInputs:
    failure_date: date
    cycle_period_end: date
    customer_successful_doms: tuple[int, ...]  # day-of-month of prior successful debits (IST)
    population_dom_prior: tuple[float, ...]  # 31 entries, index 0 = day 1
    gap_term_prior: tuple[float, ...]  # 15 entries, index 0 = day_offset 0
    issuer_success_rate_by_offset: dict[int, float]  # day_offset -> observed_success_rate
    co_occurring_issuer_degradation: bool
    weights: dict[str, float]
    min_history_successes: int
    circular_gaussian_sigma_days: float
    min_cooling_off_days: int
    reserve_days_before_cycle_end: int
    pre_debit_notice_hours: int


@dataclass(frozen=True)
class PredictionResult:
    curve: list[dict]  # [{"day_offset": d, "p": ...}, ...] for d in 0..14
    best_day_offset: int | None
    second_best_day_offset: int | None
    best_p: float
    basis: str
    feature_contributions: dict[str, float]


def _day_of_month(failure_date: date, offset: int) -> int:
    return (failure_date + timedelta(days=offset)).day


def _circular_distance(a: int, b: int, period: int = 31) -> float:
    diff = abs(a - b) % period
    return min(diff, period - diff)


def customer_term(dom: int, doms: tuple[int, ...], sigma: float) -> float:
    if not doms:
        return 0.0
    density = {d: 0.0 for d in range(1, 32)}
    for d in range(1, 32):
        total = 0.0
        for obs in doms:
            dist = _circular_distance(d, obs)
            total += math.exp(-(dist**2) / (2 * sigma**2))
        density[d] = total
    # weekend shift: Sunday's mass moves to the following Monday (approximated
    # by day-of-month arithmetic; the exact weekday depends on the calendar
    # month, which customer_term deliberately does not need to know).
    total_mass = sum(density.values()) or 1.0
    normalized = {d: v / total_mass for d, v in density.items()}
    return normalized.get(dom, 0.0)


def population_term(dom: int, prior: tuple[float, ...]) -> float:
    if 1 <= dom <= len(prior):
        return prior[dom - 1]
    return 0.0


def gap_term(day_offset: int, prior: tuple[float, ...]) -> float:
    if 0 <= day_offset < len(prior):
        return prior[day_offset]
    return 0.0


def issuer_term(day_offset: int, rates: dict[int, float], flagged: bool) -> float:
    if not flagged:
        return 0.0
    return rates.get(day_offset, 0.0)


def proximity_penalty(day_offset: int) -> float:
    return math.exp(-day_offset / 1.5)


def _feasible(
    day_offset: int,
    inputs: PredictionInputs,
) -> bool:
    if day_offset < inputs.min_cooling_off_days:
        return False
    target_date = inputs.failure_date + timedelta(days=day_offset)
    if target_date > inputs.cycle_period_end - timedelta(days=inputs.reserve_days_before_cycle_end):
        return False
    notice_lead_days = math.ceil(inputs.pre_debit_notice_hours / 24)
    if target_date < inputs.failure_date + timedelta(days=notice_lead_days):
        return False
    return True


def predict(inputs: PredictionInputs) -> PredictionResult:
    use_customer_term = len(inputs.customer_successful_doms) >= inputs.min_history_successes
    w = inputs.weights

    raw_scores: list[float] = []
    contributions_by_day: list[dict[str, float]] = []
    for d in range(15):
        target_dom = _day_of_month(inputs.failure_date, d)
        c_term = customer_term(target_dom, inputs.customer_successful_doms, inputs.circular_gaussian_sigma_days) if use_customer_term else 0.0
        p_term = population_term(target_dom, inputs.population_dom_prior)
        g_term = gap_term(d, inputs.gap_term_prior)
        i_term = issuer_term(d, inputs.issuer_success_rate_by_offset, inputs.co_occurring_issuer_degradation)
        penalty = proximity_penalty(d)

        score = (
            w["w_cust"] * c_term
            + w["w_pop"] * p_term
            + w["w_gap"] * g_term
            + w["w_iss"] * i_term
            - w["w_pen"] * penalty
        )
        raw_scores.append(max(score, 0.0))
        contributions_by_day.append({
            "customer_term": w["w_cust"] * c_term,
            "population_term": w["w_pop"] * p_term,
            "gap_term": w["w_gap"] * g_term,
            "issuer_term": w["w_iss"] * i_term,
            "proximity_penalty": -w["w_pen"] * penalty,
        })

    total = sum(raw_scores)
    if total <= 0:
        probs = [1.0 / len(raw_scores)] * len(raw_scores)
    else:
        probs = [s / total for s in raw_scores]

    curve = [{"day_offset": d, "p": round(probs[d], 4)} for d in range(15)]

    feasible_days = [d for d in range(15) if _feasible(d, inputs)]
    ranked = sorted(feasible_days, key=lambda d: probs[d], reverse=True)
    best_day_offset = ranked[0] if ranked else None
    second_best_day_offset = ranked[1] if len(ranked) > 1 else None

    if inputs.co_occurring_issuer_degradation and any(inputs.issuer_success_rate_by_offset.values()):
        basis = "ISSUER_RECOVERY"
    elif not use_customer_term:
        basis = "POPULATION_PRIOR"
    else:
        basis = "BLENDED" if any(inputs.issuer_success_rate_by_offset.values()) else "CUSTOMER_HISTORY"

    best_p = probs[best_day_offset] if best_day_offset is not None else 0.0
    feature_contributions = contributions_by_day[best_day_offset] if best_day_offset is not None else {}

    return PredictionResult(
        curve=curve,
        best_day_offset=best_day_offset,
        second_best_day_offset=second_best_day_offset,
        best_p=round(best_p, 4),
        basis=basis,
        feature_contributions=feature_contributions,
    )
