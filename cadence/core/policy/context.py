"""The `when` clause a policy rule matches against — docs/05-DECISION-ENGINE.md
Part B: "(root_cause, subtype, attempt_no, cycle_state, days_left_in_cycle,
prediction, prior_blocks)"."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyContext:
    cause: str
    subtype: str
    attempt_no: int
    cycle_state: str
    days_left_in_cycle: int
    feasible_window: bool
    presentations_exhausted: bool
    waited_days: int = 0


def matches(when: dict, ctx: PolicyContext) -> bool:
    for key, expected in when.items():
        if key == "cause":
            if ctx.cause != expected:
                return False
        elif key == "cause_in":
            if ctx.cause not in expected:
                return False
        elif key == "subtype":
            if ctx.subtype != expected:
                return False
        elif key == "subtype_in":
            if ctx.subtype not in expected:
                return False
        elif key == "attempt_no":
            if ctx.attempt_no != expected:
                return False
        elif key == "attempt_no_lte":
            if not ctx.attempt_no <= expected:
                return False
        elif key == "feasible_window":
            if ctx.feasible_window != expected:
                return False
        elif key == "presentations_exhausted":
            if ctx.presentations_exhausted != expected:
                return False
        elif key == "waited_days_gte":
            if not ctx.waited_days >= expected:
                return False
        else:
            raise ValueError(f"unknown policy `when` key: {key}")
    return True
