"""core/predict/model.py — docs/05-DECISION-ENGINE.md Part A."""
from __future__ import annotations

from datetime import date

from cadence.core.predict.model import PredictionInputs, predict

BASE_KWARGS = dict(
    population_dom_prior=tuple([1 / 31] * 31),
    gap_term_prior=tuple([1 / 15] * 15),
    issuer_success_rate_by_offset={},
    co_occurring_issuer_degradation=False,
    weights={"w_cust": 1.0, "w_pop": 1.0, "w_gap": 1.0, "w_iss": 1.0, "w_pen": 1.0},
    min_history_successes=3,
    circular_gaussian_sigma_days=1.5,
    min_cooling_off_days=2,
    reserve_days_before_cycle_end=1,
    pre_debit_notice_hours=24,
)


def test_below_min_history_falls_back_to_population_prior():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(2, 3),  # only 2 — below min_history_successes=3
        **BASE_KWARGS,
    )
    result = predict(inputs)
    assert result.basis == "POPULATION_PRIOR"


def test_customer_history_drives_basis_once_enough_successes():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(2, 3, 2, 3),
        **BASE_KWARGS,
    )
    result = predict(inputs)
    assert result.basis in ("CUSTOMER_HISTORY", "BLENDED")


def test_best_day_respects_cooling_off_floor():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(),
        **BASE_KWARGS,
    )
    result = predict(inputs)
    assert result.best_day_offset is not None
    assert result.best_day_offset >= inputs.min_cooling_off_days


def test_best_day_respects_cycle_reserve_ceiling():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 1, 29),  # closes almost immediately
        customer_successful_doms=(),
        **BASE_KWARGS,
    )
    result = predict(inputs)
    # feasible window: offset >= 2 and date <= Jan 28 -> only offset 1 fits calendar-wise,
    # but offset 1 < min_cooling_off_days(2), so nothing is feasible.
    assert result.best_day_offset is None


def test_no_feasible_window_returns_none_not_a_crash():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 1, 28),
        customer_successful_doms=(2, 3, 2, 3),
        **BASE_KWARGS,
    )
    result = predict(inputs)
    assert result.best_day_offset is None
    assert result.feature_contributions == {}


def test_curve_has_fifteen_entries_summing_to_one():
    inputs = PredictionInputs(
        failure_date=date(2026, 1, 27),
        cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(2, 3, 2, 3),
        **BASE_KWARGS,
    )
    result = predict(inputs)
    assert len(result.curve) == 15
    assert abs(sum(c["p"] for c in result.curve) - 1.0) < 1e-3


def test_proximity_penalty_discourages_very_early_days():
    from cadence.core.predict.model import proximity_penalty

    assert proximity_penalty(0) > proximity_penalty(5) > proximity_penalty(10)


def test_issuer_term_only_participates_when_flagged():
    kwargs = dict(BASE_KWARGS)
    kwargs["issuer_success_rate_by_offset"] = {3: 0.9}
    inputs_unflagged = PredictionInputs(
        failure_date=date(2026, 1, 27), cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(), co_occurring_issuer_degradation=False, **{k: v for k, v in kwargs.items() if k != "co_occurring_issuer_degradation"},
    )
    inputs_flagged = PredictionInputs(
        failure_date=date(2026, 1, 27), cycle_period_end=date(2026, 2, 26),
        customer_successful_doms=(), co_occurring_issuer_degradation=True, **{k: v for k, v in kwargs.items() if k != "co_occurring_issuer_degradation"},
    )
    result_unflagged = predict(inputs_unflagged)
    result_flagged = predict(inputs_flagged)
    assert result_flagged.basis == "ISSUER_RECOVERY"
    assert result_unflagged.basis != "ISSUER_RECOVERY"
