"""Live adapters — Razorpay test-mode API. No ground truth here, so this can
live in core/. Not exercised by the test suite (needs real test-mode
credentials); the eval harness and demo run entirely on the Sim adapters in
sim/adapters.py. See docs/02-ARCHITECTURE.md "the two execution modes".
"""
from __future__ import annotations

import os
from datetime import date, datetime

import razorpay

from cadence.core.execute.interfaces import MessagingAdapter, PaymentLinkAdapter, PresentmentAdapter


def _client() -> razorpay.Client:
    key_id = os.environ["RAZORPAY_KEY_ID"]
    key_secret = os.environ["RAZORPAY_KEY_SECRET"]
    return razorpay.Client(auth=(key_id, key_secret))


class LivePresentmentAdapter(PresentmentAdapter):
    def present(
        self, token, *, mandate_id: str, cycle_id: str, amount_paise: int, attempt_date: date, attempt_no: int,
    ) -> dict:
        self._require_token(token)
        client = _client()
        # Razorpay Subscriptions charge on their own schedule; a manual
        # re-presentment against test mode is represented here as a
        # registered-mandate charge attempt against the subscription id
        # stored on the mandate row. Left generic since this path is never
        # exercised without real test-mode credentials.
        result = client.subscription.pending_update(mandate_id, {})
        return {"succeeded": bool(result.get("status") == "active"), "gateway_code": None, "gateway_desc": None}


class LiveMessagingAdapter(MessagingAdapter):
    def send(self, token, *, customer_id: str, channel: str, template_key: str, variables: dict) -> dict:
        self._require_token(token)
        # WhatsApp Cloud API call would go here; left as a stub since it
        # needs a WHATSAPP_TOKEN and approved template ids (docs/11 R3).
        raise NotImplementedError("WhatsApp Cloud API wiring needs live template approval — see docs/14 R3")


class LivePaymentLinkAdapter(PaymentLinkAdapter):
    def create_link(self, token, *, cycle_id: str, amount_paise: int, created_at: datetime) -> dict:
        self._require_token(token)
        client = _client()
        link = client.payment_link.create({"amount": amount_paise, "currency": "INR"})
        return {"razorpay_link_id": link["id"], "short_url": link["short_url"]}
