"""Razorpay webhook signature verification (HMAC-SHA256 of the raw body).
See docs/08-API-CONTRACT.md — never process an unverified webhook."""
from __future__ import annotations

import hashlib
import hmac


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
