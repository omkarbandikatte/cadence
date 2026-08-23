"""Adapter interfaces. Real Sim/Live implementations land in M5 — this file's
job for M3 is the GateToken requirement itself: bypassing the gate must be a
type error, not a discipline problem. See docs/06-COMPLIANCE-GATE.md.
"""
from __future__ import annotations

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

    def present(self, token: GateToken, *, mandate_id: str, cycle_id: str, amount_paise: int) -> dict:
        self._require_token(token)
        raise NotImplementedError("Sim/Live presentment adapters land in M5")


class MessagingAdapter(BaseAdapter):
    expected_action_types = {
        "PRE_DEBIT_NOTICE", "TOPUP_NUDGE", "REQUEST_REAUTH", "REQUEST_INSTRUMENT_UPDATE", "SEND_PAYMENT_LINK",
    }

    def send(self, token: GateToken, *, customer_id: str, template_key: str, variables: dict) -> dict:
        self._require_token(token)
        raise NotImplementedError("Sim/Live messaging adapters land in M5")


class PaymentLinkAdapter(BaseAdapter):
    expected_action_types = {"SEND_PAYMENT_LINK"}

    def create_link(self, token: GateToken, *, cycle_id: str, amount_paise: int) -> dict:
        self._require_token(token)
        raise NotImplementedError("Sim/Live payment link adapters land in M5")
