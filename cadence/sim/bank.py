"""The outcome oracle. Given a presentment attempt, resolves success/failure
against ground truth laid down by sim/generator.py. Must never be imported
from cadence/core — see docs/02-ARCHITECTURE.md and docs/07-SYNTHETIC-DATA.md V4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class MandateGT:
    customer_id: str
    max_amount_paise: int
    status: str
    revoked_at: date | None
    valid_until: date
    debit_day: int = 1
    rail: str = "UPI_AUTOPAY"


@dataclass
class CycleGT:
    mandate_id: str
    amount_paise: int
    period_start: date
    period_end: date
    debit_date: date


@dataclass
class CustomerGT:
    segment: str
    issuer_code: str


@dataclass
class IssuerDayGT:
    observed_success_rate: float
    is_outage: bool


@dataclass
class DesignedCause:
    root_cause: str
    subtype: str
    raw_code: str
    gateway_desc: str


@dataclass
class World:
    """The generator's ground truth. Every field here is off-limits to core/."""

    customers: dict[str, CustomerGT] = field(default_factory=dict)
    mandates: dict[str, MandateGT] = field(default_factory=dict)
    cycles: dict[str, CycleGT] = field(default_factory=dict)
    # customer_id -> {date: balance_paise}
    funding_calendar: dict[str, dict[date, int]] = field(default_factory=dict)
    # (issuer_code, date) -> IssuerDayGT
    issuer_days: dict[tuple[str, date], IssuerDayGT] = field(default_factory=dict)
    # cycle_id -> DesignedCause, for causes with no natural schema representation
    designed_causes: dict[str, DesignedCause] = field(default_factory=dict)


@dataclass
class AttemptResult:
    succeeded: bool
    gateway_code: str
    gateway_desc: str


def resolve(world: World, cycle_id: str, attempt_date: date, attempt_no: int, rng) -> AttemptResult:
    """Resolve one presentment attempt against ground truth.

    Check order mirrors what a real gateway would enforce structurally first
    (mandate validity, cap), then scripted per-cycle defects, then the
    probabilistic issuer-outage channel, and finally the balance test.
    """
    cycle = world.cycles[cycle_id]
    mandate = world.mandates[cycle.mandate_id]
    customer = world.customers[mandate.customer_id]

    if attempt_date > mandate.valid_until:
        return AttemptResult(False, "MANDATE_EXPIRED", "mandate validity window has ended")

    if mandate.status == "REVOKED" and mandate.revoked_at is not None and attempt_date >= mandate.revoked_at:
        return AttemptResult(False, "MANDATE_REVOKED", "mandate was revoked by the customer")

    if cycle.amount_paise > mandate.max_amount_paise:
        return AttemptResult(False, "AMOUNT_EXCEEDS_MANDATE", "charge amount exceeds the mandate cap")

    designed = world.designed_causes.get(cycle_id)
    if designed is not None and designed.root_cause in ("INSTRUMENT_DEFECT", "RISK_BLOCK", "UNKNOWN"):
        return AttemptResult(False, designed.raw_code, designed.gateway_desc)

    if designed is not None and designed.root_cause == "TECHNICAL_TRANSIENT":
        if attempt_no <= 1:
            return AttemptResult(False, designed.raw_code, designed.gateway_desc)
        # transient fault has cleared by the next attempt; fall through to the
        # normal balance test below.

    issuer_day = world.issuer_days.get((customer.issuer_code, attempt_date))
    if issuer_day is not None and issuer_day.is_outage:
        if rng.random() > issuer_day.observed_success_rate:
            return AttemptResult(False, "ISSUER_DOWN", "issuer's upstream rail was degraded")

    calendar = world.funding_calendar[mandate.customer_id]
    balance = calendar.get(attempt_date, 0)
    if balance >= cycle.amount_paise:
        return AttemptResult(True, "", "")
    return AttemptResult(False, "INSUFFICIENT_FUNDS", "account balance was below the debit amount")


def apply_debit(world: World, customer_id: str, from_date: date, amount_paise: int) -> None:
    """Money that leaves the account stays gone for every later day."""
    calendar = world.funding_calendar[customer_id]
    for d in sorted(day for day in calendar if day >= from_date):
        calendar[d] = max(0, calendar[d] - amount_paise)


def undo_debit(world: World, customer_id: str, from_date: date, amount_paise: int) -> None:
    """Refund a debit that generation later decided should not have happened
    (used when overriding a naturally-successful cycle to a designed failure)."""
    calendar = world.funding_calendar[customer_id]
    for d in sorted(day for day in calendar if day >= from_date):
        calendar[d] = calendar[d] + amount_paise
