"""Deterministic rules-first classifier — docs/04-FAILURE-TAXONOMY.md.

Turns a raw gateway/bank failure code into (root_cause, subtype, disposition,
confidence). Never touches the DB or generator ground truth — the caller
supplies observed_success_rate (an observable column), never the ground-truth
outage flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from cadence.core.classify.taxonomy import load_taxonomy


@dataclass(frozen=True)
class ClassificationResult:
    root_cause: str
    subtype: str
    disposition: str
    confidence: float
    matched_rule: str
    co_occurring_issuer_degradation: bool = False
    corroboration_note: str | None = None


def classify(
    raw_code: str,
    gateway_desc: str | None = None,
    observed_success_rate: float | None = None,
) -> ClassificationResult:
    tax = load_taxonomy()

    rule = tax.rule_for_code(raw_code)
    confidence_multiplier = 1.0

    if rule is None and gateway_desc:
        desc_lower = gateway_desc.lower()
        for candidate in tax.rules:
            if any(s in desc_lower for s in candidate.desc_contains):
                rule = candidate
                confidence_multiplier = 0.8
                break

    if rule is None:
        d = tax.default
        return ClassificationResult(d.root_cause, d.subtype, d.disposition, d.confidence, "DEFAULT")

    root_cause = rule.root_cause
    confidence = rule.confidence * confidence_multiplier
    matched_rule = rule.id
    co_occurring = False
    note = None

    if (
        root_cause == "ISSUER_DEGRADED"
        and observed_success_rate is not None
        and observed_success_rate >= tax.issuer_normal_success_rate
    ):
        # The issuer looks fine today; a bank blaming its upstream while its
        # upstream is fine is more likely a per-customer problem.
        note = (
            f"issuer observed_success_rate {observed_success_rate:.2f} is within the "
            f"normal band; downgrading the ISSUER_DEGRADED call from rule {rule.id}"
        )
        d = tax.default
        return ClassificationResult(d.root_cause, d.subtype, d.disposition, d.confidence, f"{rule.id}->DOWNGRADED", corroboration_note=note)

    if (
        root_cause == "BALANCE_SHORTFALL"
        and observed_success_rate is not None
        and observed_success_rate <= tax.issuer_collapsed_success_rate
    ):
        co_occurring = True
        note = (
            f"issuer observed_success_rate {observed_success_rate:.2f} has collapsed "
            f"today; flagging a co-occurring issuer degradation alongside {rule.id}"
        )

    return ClassificationResult(
        root_cause=root_cause,
        subtype=rule.subtype,
        disposition=rule.disposition,
        confidence=confidence,
        matched_rule=matched_rule,
        co_occurring_issuer_degradation=co_occurring,
        corroboration_note=note,
    )
