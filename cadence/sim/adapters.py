"""Sim adapters — resolve against generator ground truth via sim/bank.py.
Never imported from core/; injected into core/execute/scheduler.py by the
eval harness. See docs/02-ARCHITECTURE.md "the two execution modes"."""
from __future__ import annotations

from datetime import date, datetime

from cadence.core.execute.interfaces import MessagingAdapter, PaymentLinkAdapter, PresentmentAdapter
from cadence.sim import bank


class SimPresentmentAdapter(PresentmentAdapter):
    def __init__(self, world: bank.World, rng):
        self.world = world
        self.rng = rng

    def present(
        self, token, *, mandate_id: str, cycle_id: str, amount_paise: int, attempt_date: date, attempt_no: int,
    ) -> dict:
        self._require_token(token)
        result = bank.resolve(self.world, cycle_id, attempt_date, attempt_no, self.rng)
        if result.succeeded:
            mandate = self.world.mandates[self.world.cycles[cycle_id].mandate_id]
            bank.apply_debit(self.world, mandate.customer_id, attempt_date, amount_paise)
        return {"succeeded": result.succeeded, "gateway_code": result.gateway_code, "gateway_desc": result.gateway_desc}


class SimMessagingAdapter(MessagingAdapter):
    """Records that a message was sent; never touches the network."""

    def send(self, token, *, customer_id: str, channel: str, template_key: str, variables: dict) -> dict:
        self._require_token(token)
        body = _render_template(template_key, variables)
        return {"body_rendered": body}


class SimPaymentLinkAdapter(PaymentLinkAdapter):
    """Scripted pay-rate: a fixed conversion probability and delay, seeded."""

    def __init__(self, rng, pay_probability: float = 0.55, max_days_to_pay: int = 4):
        self.rng = rng
        self.pay_probability = pay_probability
        self.max_days_to_pay = max_days_to_pay

    def create_link(self, token, *, cycle_id: str, amount_paise: int, created_at: datetime) -> dict:
        self._require_token(token)
        will_pay = self.rng.random() < self.pay_probability
        days_to_pay = int(self.rng.integers(1, self.max_days_to_pay + 1)) if will_pay else None
        return {
            "razorpay_link_id": None,
            "short_url": f"https://rzp.io/l/sim-{cycle_id[-8:]}",
            "will_pay": will_pay,
            "days_to_pay": days_to_pay,
        }


_TEMPLATE_BODIES = {
    "predebit_notice_v1": "Your payment of ₹{amount} is scheduled for {date}. Reply STOP to opt out.",
    "topup_nudge_v1": "A top-up before {date} will help your payment of ₹{amount} go through.",
    "payment_link_v1": "Pay ₹{amount} now: {link}",
    "reauth_v1": "Your mandate needs re-authorisation: {link}",
    "instrument_update_v1": "Please update your payment method: {link}",
}


def _render_template(template_key: str, variables: dict) -> str:
    template = _TEMPLATE_BODIES.get(template_key, "{amount}")
    try:
        return template.format(**variables)
    except (KeyError, IndexError):
        return template
