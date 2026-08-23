"""Deterministic rationale templates — one plain-English sentence a judge can
read aloud. CLAUDE.md: an LLM may write this in production, but the fallback
template is mandatory and this build uses the template path only, to keep
every run reproducible from its seed. See docs/05-DECISION-ENGINE.md Part B."""
from __future__ import annotations

from datetime import timedelta


def _money(amount_paise: int | None) -> str:
    if amount_paise is None:
        return "the amount due"
    return f"₹{amount_paise / 100:,.2f}"


def build_rationale(*, candidate, classification, prediction_outcome, gate_decision, failure_date, amount_paise) -> str:
    if gate_decision.result == "BLOCKED":
        reasons = "; ".join(f"{b.code}: {b.message}" for b in gate_decision.blocks)
        return f"Not proceeding with {candidate.action}: {reasons}."

    action = candidate.action
    if action == "SCHEDULE_PRESENTMENT" and prediction_outcome is not None and prediction_outcome.best_day_offset is not None:
        target_date = failure_date + timedelta(days=prediction_outcome.best_day_offset)
        basis_phrase = {
            "CUSTOMER_HISTORY": "own debit history points to this day",
            "POPULATION_PRIOR": "population-level pay-day pattern points to this day (not enough history for this customer yet)",
            "BLENDED": "debit history and issuer signal both point to this day",
            "ISSUER_RECOVERY": "the issuer outage is expected to have cleared by this day",
        }.get(prediction_outcome.basis, "the model's timing signal points to this day")
        return f"Waiting until {target_date.isoformat()} to re-present {_money(amount_paise)} because this customer's {basis_phrase}."
    if action == "PRE_DEBIT_NOTICE":
        return f"Sending a pre-debit notice for {_money(amount_paise)} ahead of the scheduled presentment."
    if action == "TOPUP_NUDGE":
        return "Sending a top-up nudge before the next presentment attempt."
    if action == "PRESENT_NOW":
        return "Presenting again now: the prior failure looks like a transient technical fault, not a balance problem."
    if action == "WAIT_ISSUER_RECOVERY":
        return "Waiting for the issuer outage to clear before presenting again; no customer message needed."
    if action == "SEND_PAYMENT_LINK":
        return f"Presentations are exhausted or no timing window fits; sending a one-time payment link for {_money(amount_paise)}."
    if action == "REQUEST_REAUTH":
        return "Not re-presenting: the mandate is not active. Sent a re-authorisation link instead."
    if action == "REQUEST_INSTRUMENT_UPDATE":
        return "Not re-presenting: the payment instrument needs to be updated first."
    if action == "ESCALATE_TO_MERCHANT":
        cause = classification.root_cause if classification else "this case"
        return f"Escalating to the merchant: {cause} requires a human decision, not an automated retry."
    if action == "STOP_MARK_CHURN":
        return "Stopping automated recovery and flagging this cycle as churned."
    return "No automated action is appropriate for this cycle right now."
