"""Candidate selection: the first rule whose `when` matches, filtered to
exclude anything already rejected by the gate this round or forbidden for
this cause. Re-invoked on gate rejection — see docs/05-DECISION-ENGINE.md
Part B and the M5 prompt in docs/12-AGENT-PROMPTS.md."""
from __future__ import annotations

from cadence.core.policy.config import Candidate, load_policy_table
from cadence.core.policy.context import PolicyContext, matches


def next_candidate(ctx: PolicyContext, rejected: set[str]) -> Candidate | None:
    table = load_policy_table()
    for rule in table.rules:
        if not matches(rule.when, ctx):
            continue
        for candidate in rule.candidates:
            if candidate.action in rejected or candidate.action in rule.forbid:
                continue
            return candidate
        return None  # rule matched but every one of its candidates is exhausted
    for candidate in table.fallback:
        if candidate.action not in rejected:
            return candidate
    return None
