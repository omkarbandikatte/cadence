"""Adapter interfaces. Real Sim implementations live in sim/adapters.py (they
resolve against generator ground truth, which core/ must never import); Live
implementations live in core/execute/live.py (they call the real Razorpay
test-mode API and touch no ground truth, so they may live in core/). Every
adapter method requires a GateToken — bypassing the gate is a type error, not
a discipline problem. See docs/06-COMPLIANCE-GATE.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from cadence.core.compliance.gate import GateToken


class BaseAdapter:
    expected_action_types: set[str] = set()

    def _require_token(self, token: GateToken) -> None:
        if not isinstance(token, GateToken):
            raise TypeError("adapter calls require a GateToken minted by compliance.evaluate()")
        if self.expected_action_types and token.action_type not in self.expected_action_types:
            raise TypeError(
                f"GateToken minted for {token.action_type} cannot authorize this adapter"
            )


class PresentmentAdapter(BaseAdapter):
    expected_action_types = {"PRESENT_NOW", "SCHEDULE_PRESENTMENT"}

    def present(
        self, token: GateToken, *, mandate_id: str, cycle_id: str, amount_paise: int,
        attempt_date: date, attempt_no: int,
    ) -> dict:
        self._require_token(token)
        raise NotImplementedError


class MessagingAdapter(BaseAdapter):
    expected_action_types = {
        "PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE", "SEND_PAYMENT_LINK",
    }

    def send(
        self, token: GateToken, *, customer_id: str, channel: str, template_key: str, variables: dict,
    ) -> dict:
        self._require_token(token)
        raise NotImplementedError


class PaymentLinkAdapter(BaseAdapter):
    expected_action_types = {"SEND_PAYMENT_LINK"}

    def create_link(
        self, token: GateToken, *, cycle_id: str, amount_paise: int, created_at: datetime,
    ) -> dict:
        self._require_token(token)
        raise NotImplementedError


@dataclass
class Adapters:
    presentment: PresentmentAdapter
    messaging: MessagingAdapter
    payment_link: PaymentLinkAdapter

