"""Loads config/policy.yaml's decision table — docs/05-DECISION-ENGINE.md Part B."""
from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

POLICY_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "policy.yaml"


@dataclass(frozen=True)
class Candidate:
    action: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    id: str
    when: dict[str, Any]
    candidates: tuple[Candidate, ...]
    forbid: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyTable:
    version: int
    rules: tuple[Rule, ...]
    fallback: tuple[Candidate, ...]


@functools.lru_cache(maxsize=1)
def load_policy_table(path: pathlib.Path | None = None) -> PolicyTable:
    path = path or POLICY_PATH
    with open(path) as f:
        raw = yaml.safe_load(f)

    rules = []
    for r in raw["rules"]:
        candidates = tuple(
            Candidate(action=c["action"], params={k: v for k, v in c.items() if k != "action"})
            for c in r["candidates"]
        )
        rules.append(Rule(id=r["id"], when=r["when"], candidates=candidates, forbid=tuple(r.get("forbid", []))))

    fallback = tuple(
        Candidate(action=c["action"], params={k: v for k, v in c.items() if k != "action"})
        for c in raw["fallback"]["candidates"]
    )
    return PolicyTable(version=raw["policy_version"], rules=tuple(rules), fallback=fallback)
