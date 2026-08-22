"""Same seed must reproduce identical corpus statistics — docs/07 Reproducibility.
ULIDs themselves are not required to match (they embed wall-clock time); every
measurable value they wrap around must."""
from __future__ import annotations

from cadence.sim.generator import generate_corpus


def _fingerprint(seed: int) -> tuple:
    g = generate_corpus(seed, n_customers=60, write_to_db=False)
    n_failed = sum(1 for s in g.cycle_status.values() if s == "FAILED")
    return (
        len(g.mandate_customer),
        len(g.cycle_status),
        n_failed,
        tuple(sorted(g.cause_mix.items())),
    )


def test_same_seed_is_reproducible():
    assert _fingerprint(123) == _fingerprint(123)


def test_different_seeds_diverge():
    assert _fingerprint(1) != _fingerprint(2)
