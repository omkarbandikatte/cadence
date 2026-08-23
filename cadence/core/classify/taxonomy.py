"""Loads config/taxonomy.yaml — the source of truth for classification.

If this drifts from models/enums.py, this file wins (CLAUDE.md). A dedicated
test (test_taxonomy_enum_sync.py) checks for drift and fails loudly; this
loader does not — it trusts the YAML.
"""
from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass, field

import yaml

TAXONOMY_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "taxonomy.yaml"


@dataclass(frozen=True)
class Rule:
    id: str
    root_cause: str
    subtype: str
    disposition: str
    confidence: float
    codes: tuple[str, ...] = ()
    desc_contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class Default:
    root_cause: str
    subtype: str
    disposition: str
    confidence: float


@dataclass(frozen=True)
class Taxonomy:
    version: int
    rules: tuple[Rule, ...]
    default: Default
    issuer_normal_success_rate: float
    issuer_collapsed_success_rate: float
    rules_by_code: dict[str, Rule] = field(default_factory=dict)

    def rule_for_code(self, code: str) -> Rule | None:
        return self.rules_by_code.get(code)


@functools.lru_cache(maxsize=1)
def load_taxonomy(path: pathlib.Path | None = None) -> Taxonomy:
    path = path or TAXONOMY_PATH
    with open(path) as f:
        raw = yaml.safe_load(f)

    rules = []
    rules_by_code: dict[str, Rule] = {}
    for r in raw["rules"]:
        rule = Rule(
            id=r["id"],
            root_cause=r["root_cause"],
            subtype=r["subtype"],
            disposition=r["disposition"],
            confidence=float(r["confidence"]),
            codes=tuple(r.get("codes", [])),
            desc_contains=tuple(s.lower() for s in r.get("desc_contains", [])),
        )
        rules.append(rule)
        for code in rule.codes:
            rules_by_code[code] = rule

    default = Default(
        root_cause=raw["default"]["root_cause"],
        subtype=raw["default"]["subtype"],
        disposition=raw["default"]["disposition"],
        confidence=float(raw["default"]["confidence"]),
    )

    corroboration = raw.get("corroboration", {})
    return Taxonomy(
        version=raw["version"],
        rules=tuple(rules),
        default=default,
        issuer_normal_success_rate=float(corroboration.get("issuer_normal_success_rate", 0.75)),
        issuer_collapsed_success_rate=float(corroboration.get("issuer_collapsed_success_rate", 0.55)),
        rules_by_code=rules_by_code,
    )
