"""V4 from docs/07-SYNTHETIC-DATA.md: core/ must never read generator-only
ground truth. Enforced here so it runs on every `make test`, not just
`make validate-corpus`."""
from __future__ import annotations

from cadence.sim.validate import find_leakage


def test_core_never_references_generator_ground_truth():
    hits = find_leakage()
    assert hits == [], f"core/ references generator-only ground truth: {hits}"
