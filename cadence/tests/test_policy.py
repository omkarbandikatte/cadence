"""core/policy — docs/05-DECISION-ENGINE.md Part B."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from cadence.core.policy.candidates import next_candidate
from cadence.core.policy.config import Candidate
from cadence.core.policy.context import PolicyContext
from cadence.core.policy.schedule import compute_run_at
from cadence.core.predict.service import PredictionOutcome

NOW = datetime(2026, 1, 27, 6, 0, tzinfo=timezone.utc)


def _ctx(**overrides):
    base = dict(
        cause="BALANCE_SHORTFALL", subtype="NONE", attempt_no=1, cycle_state="IN_RECOVERY",
        days_left_in_cycle=20, feasible_window=True, presentations_exhausted=False, waited_days=0,
    )
    base.update(overrides)
    return PolicyContext(**base)


def test_first_matching_rule_wins():
    candidate = next_candidate(_ctx(), rejected=set())
    assert candidate.action == "PRE_DEBIT_NOTICE"


def test_rejected_candidate_is_skipped_within_same_rule():
    candidate = next_candidate(_ctx(), rejected={"PRE_DEBIT_NOTICE"})
    assert candidate.action == "SCHEDULE_PRESENTMENT"


def test_exhausted_rule_returns_none_for_caller_to_fall_back_on():
    candidate = next_candidate(_ctx(), rejected={"PRE_DEBIT_NOTICE", "SCHEDULE_PRESENTMENT"})
    assert candidate is None


def test_forbidden_action_never_returned_for_mandate_defect():
    ctx = _ctx(cause="MANDATE_DEFECT", subtype="REVOKED")
    candidate = next_candidate(ctx, rejected={"REQUEST_REAUTH", "ESCALATE_TO_MERCHANT"})
    assert candidate is None  # never falls back to a forbidden PRESENT_NOW/SCHEDULE_PRESENTMENT


def test_risk_block_only_escalates():
    candidate = next_candidate(_ctx(cause="RISK_BLOCK"), rejected=set())
    assert candidate.action == "ESCALATE_TO_MERCHANT"


def test_presentations_exhausted_routes_to_payment_link():
    candidate = next_candidate(_ctx(attempt_no=4, presentations_exhausted=True), rejected=set())
    assert candidate.action == "SEND_PAYMENT_LINK"


def test_compute_run_at_schedule_presentment_uses_best_day_offset():
    outcome = PredictionOutcome(row=None, best_day_offset=3, second_best_day_offset=5, basis="CUSTOMER_HISTORY")
    candidate = Candidate(action="SCHEDULE_PRESENTMENT", params={})
    run_at = compute_run_at(candidate, now=NOW, failure_date=date(2026, 1, 27), prediction_outcome=outcome)
    assert run_at.date() == date(2026, 1, 30)


def test_compute_run_at_pre_debit_notice_leads_the_presentment():
    outcome = PredictionOutcome(row=None, best_day_offset=5, second_best_day_offset=None, basis="CUSTOMER_HISTORY")
    candidate = Candidate(action="PRE_DEBIT_NOTICE", params={"offset_days_before_presentment": 2})
    run_at = compute_run_at(candidate, now=NOW, failure_date=date(2026, 1, 27), prediction_outcome=outcome)
    assert run_at.date() == date(2026, 1, 30)  # Jan27+5 - 2


def test_compute_run_at_no_feasible_window_falls_back_to_now():
    outcome = PredictionOutcome(row=None, best_day_offset=None, second_best_day_offset=None, basis="POPULATION_PRIOR")
    candidate = Candidate(action="SCHEDULE_PRESENTMENT", params={})
    run_at = compute_run_at(candidate, now=NOW, failure_date=date(2026, 1, 27), prediction_outcome=outcome)
    assert run_at == NOW
