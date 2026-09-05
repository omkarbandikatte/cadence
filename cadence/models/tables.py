"""SQLAlchemy 2.0 models for every table in docs/03-DATA-MODEL.md.

Money is paise, BIGINT. Timestamps are TIMESTAMPTZ, stored UTC. IDs are
prefixed ULIDs. Relationships are intentionally omitted — every access pattern
in this project is an explicit query, not a graph walk, so an ORM relationship
graph would be an abstraction used fewer times than it costs.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cadence.models.base import Base, new_id


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("cus"))
    name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    issuer_code: Mapped[str] = mapped_column(Text)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Generator ground truth for corpus construction and post-hoc analysis only.
    # A test asserts core/ never selects this column.
    segment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mandate(Base):
    __tablename__ = "mandates"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("mnd"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    rail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    max_amount_paise: Mapped[int] = mapped_column(BigInteger)
    frequency: Mapped[str] = mapped_column(Text)
    debit_day: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    razorpay_subscription_id: Mapped[str | None] = mapped_column(Text)


class Cycle(Base):
    __tablename__ = "cycles"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("cyc"))
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(Text)
    presentations_used: Mapped[int] = mapped_column(Integer, default=0)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_via: Mapped[str | None] = mapped_column(Text)
    recovered_amount_paise: Mapped[int | None] = mapped_column(BigInteger)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("run"))
    merchant_id: Mapped[str] = mapped_column(Text, index=True, default="demo_merchant")
    mode: Mapped[str] = mapped_column(Text)
    corpus_id: Mapped[str] = mapped_column(Text)
    seed: Mapped[int] = mapped_column(Integer)
    policy_config_hash: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSONB)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("att"))
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    presented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    gateway_code: Mapped[str | None] = mapped_column(Text)
    gateway_desc: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("fev"))
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), unique=True)
    mandate_id: Mapped[str] = mapped_column(Text, index=True)
    cycle_id: Mapped[str] = mapped_column(Text, index=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    raw_code: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("cls"))
    failure_event_id: Mapped[str] = mapped_column(ForeignKey("failure_events.id"), index=True)
    root_cause: Mapped[str] = mapped_column(Text)
    subtype: Mapped[str] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2))
    matched_rule: Mapped[str] = mapped_column(Text)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("prd"))
    failure_event_id: Mapped[str] = mapped_column(ForeignKey("failure_events.id"), index=True)
    curve: Mapped[list] = mapped_column(JSONB)
    best_day_offset: Mapped[int] = mapped_column(Integer)
    best_p: Mapped[float] = mapped_column(Numeric(4, 3))
    basis: Mapped[str] = mapped_column(Text)
    feature_contributions: Mapped[dict] = mapped_column(JSONB)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("dec"))
    failure_event_id: Mapped[str] = mapped_column(ForeignKey("failure_events.id"), index=True)
    action_type: Mapped[str] = mapped_column(Text)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(Text)
    gate_result: Mapped[str] = mapped_column(Text)
    blocked_by: Mapped[list | None] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    inputs_snapshot: Mapped[dict] = mapped_column(JSONB)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("pnd"))
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(Text)
    cancelled_reason: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("msg"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    channel: Mapped[str] = mapped_column(Text)
    template_key: Mapped[str] = mapped_column(Text)
    variables: Mapped[dict] = mapped_column(JSONB)
    body_rendered: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed_reason: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)


class PaymentLink(Base):
    __tablename__ = "payment_links"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("pyl"))
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    razorpay_link_id: Mapped[str | None] = mapped_column(Text)
    short_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)


class IssuerHealth(Base):
    __tablename__ = "issuer_health"

    issuer_code: Mapped[str] = mapped_column(Text, primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # core/predict may read this.
    observed_success_rate: Mapped[float] = mapped_column(Numeric(4, 3))
    # Ground truth, generator only. A test asserts core/ never reads this.
    is_outage: Mapped[bool] = mapped_column(Boolean)


class Ledger(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ulid: Mapped[str] = mapped_column(Text, unique=True, default=lambda: new_id("led"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    wall_clock_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_type: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    mandate_id: Mapped[str | None] = mapped_column(Text)
    cycle_id: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[str | None] = mapped_column(Text)
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.id"))
    amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    channel: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    corrects_ledger_id: Mapped[int | None] = mapped_column(BigInteger)


class ContactLog(Base):
    """Denormalised rate-limit ledger so the gate does one indexed lookup."""

    __tablename__ = "contact_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        Index("ix_contact_log_customer_run_sent", "customer_id", "run_id", "sent_at"),
    )


# ---------------------------------------------------------------------------
# Ground-truth tables — generator only. core/ must never query these.
# A test enforces this by scanning core/ for these table/column names.
# ---------------------------------------------------------------------------


class FundingCalendar(Base):
    __tablename__ = "funding_calendar"

    customer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    balance_paise: Mapped[int] = mapped_column(BigInteger)


class CorpusMeta(Base):
    __tablename__ = "corpus_meta"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: new_id("cor"))
    seed: Mapped[int] = mapped_column(Integer)
    n_customers: Mapped[int] = mapped_column(Integer)
    n_mandates: Mapped[int] = mapped_column(Integer)
    n_cycles: Mapped[int] = mapped_column(Integer)
    cause_mix: Mapped[dict] = mapped_column(JSONB)
    adversarial_cases: Mapped[dict] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
