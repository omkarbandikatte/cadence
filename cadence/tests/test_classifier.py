"""One test per taxonomy rule, plus the default/unmapped path and both
corroboration directions — docs/04-FAILURE-TAXONOMY.md, docs/12 M2 prompt."""
from __future__ import annotations

from cadence.core.classify.classifier import classify
from cadence.core.classify.taxonomy import load_taxonomy


def test_every_taxonomy_rule_classifies_by_exact_code():
    tax = load_taxonomy()
    for rule in tax.rules:
        for code in rule.codes:
            result = classify(code)
            assert result.root_cause == rule.root_cause
            assert result.subtype == rule.subtype
            assert result.disposition == rule.disposition
            assert result.matched_rule == rule.id
            assert result.confidence == rule.confidence


def test_unmapped_code_degrades_to_unknown_terminal():
    result = classify("SOME_CODE_NOT_IN_TAXONOMY")
    assert result.root_cause == "UNKNOWN"
    assert result.disposition == "TERMINAL"
    assert result.confidence == 0.0
    assert result.matched_rule == "DEFAULT"


def test_description_substring_fallback_at_reduced_confidence():
    result = classify("SOME_UNMAPPED_CODE", gateway_desc="Account has insufficient balance today")
    assert result.root_cause == "BALANCE_SHORTFALL"
    assert result.matched_rule == "BAL_001"
    assert result.confidence == 0.95 * 0.8


def test_corroboration_downgrades_issuer_degraded_when_issuer_looks_normal():
    result = classify("ISSUER_DOWN", observed_success_rate=0.95)
    assert result.root_cause == "UNKNOWN"
    assert result.disposition == "TERMINAL"
    assert result.matched_rule == "ISS_001->DOWNGRADED"
    assert result.corroboration_note is not None


def test_corroboration_does_not_downgrade_when_issuer_is_degraded():
    result = classify("ISSUER_DOWN", observed_success_rate=0.10)
    assert result.root_cause == "ISSUER_DEGRADED"
    assert result.matched_rule == "ISS_001"


def test_corroboration_flags_cooccurring_outage_on_balance_shortfall():
    result = classify("INSUFFICIENT_FUNDS", observed_success_rate=0.20)
    assert result.root_cause == "BALANCE_SHORTFALL"
    assert result.co_occurring_issuer_degradation is True
    assert result.corroboration_note is not None


def test_corroboration_silent_when_issuer_healthy_for_balance_shortfall():
    result = classify("INSUFFICIENT_FUNDS", observed_success_rate=0.92)
    assert result.root_cause == "BALANCE_SHORTFALL"
    assert result.co_occurring_issuer_degradation is False
    assert result.corroboration_note is None
