"""The single choke point. No presentment and no message reaches an adapter
without passing evaluate(). See docs/06-COMPLIANCE-GATE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from cadence.core.compliance.checks import ALL_CHECKS
from cadence.core.compliance.config import PolicyConstants, load_policy_constants
from cadence.core.ledger import writer as ledger

ACTION_CHECK_GROUPS: dict[str, set[str]] = {
    "PRESENT_NOW": {"presentment"},
    "SCHEDULE_PRESENTMENT": {"presentment"},
    "PRE_DEBIT_NOTICE": {"messaging"},
    "TOPUP_NUDGE": {"messaging"},
    "REQUEST_REAUTH": {"messaging"},
    "REQUEST_INSTRUMENT_UPDATE": {"messaging"},
    "SEND_PAYMENT_LINK": {"messaging", "payment_link"},
    "WAIT_ISSUER_RECOVERY": set(),
    "ESCALATE_TO_MERCHANT": set(),
    "STOP_MARK_CHURN": set(),
    "NO_ACTION": set(),
}


@dataclass(frozen=True)
class ProposedAction:
    action_type: str
    run_id: str
    now: datetime
    mandate_id: str | None = None
    cycle_id: str | None = None
    customer_id: str | None = None
    amount_paise: int | None = None
    channel: str | None = None
    template_key: str | None = None
    template_variables: dict | None = None


@dataclass(frozen=True)
class Block:
    check: str
    code: str
    message: str


class GateToken:
    """Only compliance.evaluate() can construct this. Adapters in core/execute
    require one, so calling an adapter without passing the gate is a type error."""

    _MINT_KEY = object()

    def __init__(self, mint_key: object, action_type: str, cycle_id: str | None):
        if mint_key is not GateToken._MINT_KEY:
            raise RuntimeError("GateToken can only be minted by compliance.evaluate()")
        self.action_type = action_type
        self.cycle_id = cycle_id


@dataclass(frozen=True)
class GateDecision:
    result: str  # GateResult: ALLOWED | BLOCKED
    blocks: list[Block]
    checks_run: list[str]
    evaluated_at: datetime
    token: GateToken | None = None

    def __post_init__(self):
        if self.blocks and self.result != "BLOCKED":
            raise AssertionError("a non-empty blocks list must imply result == BLOCKED")


def evaluate(
    action: ProposedAction,
    session: Session,
    constants: PolicyConstants | None = None,
) -> GateDecision:
    """Never raises for a policy violation — a block is a normal return.
    Re-run this at execution time, not only at decision time: the world moves
    between scheduling and firing."""
    constants = constants or load_policy_constants()
    groups = ACTION_CHECK_GROUPS.get(action.action_type, set()) | {"global"}
    applicable = [c for c in ALL_CHECKS if c.group in groups]

    blocks: list[Block] = []
    checks_run: list[str] = []
    for check in applicable:
        checks_run.append(check.name)
        outcome = check.fn(action, session, constants)
        if outcome is not None:
            code, message = outcome
            blocks.append(Block(check=check.name, code=code, message=message))

    result = "BLOCKED" if blocks else "ALLOWED"
    token = GateToken(GateToken._MINT_KEY, action.action_type, action.cycle_id) if result == "ALLOWED" else None
    decision = GateDecision(result=result, blocks=blocks, checks_run=checks_run, evaluated_at=action.now, token=token)

    if result == "ALLOWED":
        rationale = f"Gate allowed {action.action_type}: all {len(checks_run)} checks passed."
    else:
        codes = ", ".join(b.code for b in blocks)
        rationale = f"Gate blocked {action.action_type}: {codes}."

    ledger.record(
        session,
        event_type="DECISION" if result == "ALLOWED" else "GATE_BLOCKED",
        run_id=action.run_id,
        occurred_at=action.now,
        rationale=rationale,
        payload={
            "action_type": action.action_type,
            "checks_run": checks_run,
            "blocks": [{"check": b.check, "code": b.code, "message": b.message} for b in blocks],
        },
        mandate_id=action.mandate_id,
        cycle_id=action.cycle_id,
        customer_id=action.customer_id,
        channel=action.channel,
    )
    session.flush()

    return decision
