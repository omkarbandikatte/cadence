"""Merchant pause and customer-hold toggles. In-memory, single-process —
docs/03-DATA-MODEL.md has no dedicated table for either, and a hackathon
single-FastAPI-process deployment doesn't need one. Wired to real dashboard
buttons in M7/M8 (POST /merchant/pause-automation, support holds)."""
from __future__ import annotations

_merchant_paused: bool = False
_held_customers: set[str] = set()


def pause_merchant() -> None:
    global _merchant_paused
    _merchant_paused = True


def resume_merchant() -> None:
    global _merchant_paused
    _merchant_paused = False


def is_merchant_paused() -> bool:
    return _merchant_paused


def place_hold(customer_id: str) -> None:
    _held_customers.add(customer_id)


def release_hold(customer_id: str) -> None:
    _held_customers.discard(customer_id)


def is_customer_held(customer_id: str) -> bool:
    return customer_id in _held_customers


def _reset_for_tests() -> None:
    global _merchant_paused
    _merchant_paused = False
    _held_customers.clear()
