"""Loads config/policy.yaml constants. Every constant carries a `source` —
CLAUDE.md rule 7: no hardcoded regulatory constants."""
from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass
from typing import Any

import yaml

POLICY_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "policy.yaml"


@dataclass(frozen=True)
class Constant:
    value: Any
    source: str


@dataclass(frozen=True)
class QuietHours:
    start: str
    end: str
    source: str


@dataclass(frozen=True)
class PolicyConstants:
    constants: dict[str, Constant]
    quiet_hours: QuietHours

    def value(self, name: str) -> Any:
        return self.constants[name].value


@functools.lru_cache(maxsize=1)
def load_policy_constants(path: pathlib.Path | None = None) -> PolicyConstants:
    path = path or POLICY_PATH
    with open(path) as f:
        raw = yaml.safe_load(f)

    constants: dict[str, Constant] = {}
    quiet_hours = None
    for key, entry in raw["constants"].items():
        if key == "quiet_hours_ist":
            quiet_hours = QuietHours(start=entry["start"], end=entry["end"], source=entry["source"])
            continue
        constants[key] = Constant(value=entry["value"], source=entry["source"])

    if quiet_hours is None:
        raise ValueError("policy.yaml is missing quiet_hours_ist")

    return PolicyConstants(constants=constants, quiet_hours=quiet_hours)
