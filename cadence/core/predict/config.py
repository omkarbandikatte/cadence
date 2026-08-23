"""Config for the funding-window model. Weights and the population prior live
in config/policy.yaml; the empirical recovery-gap prior lives in its own file
because it's fit from data, not hand-authored — see sim/fit_predict_weights.py.
"""
from __future__ import annotations

import functools
import pathlib

import yaml

POLICY_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "policy.yaml"
MODEL_WEIGHTS_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "model_weights.yaml"
GAP_TERM_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "gap_term.yaml"

DEFAULT_GAP_TERM_PRIOR = tuple(1 / 15 for _ in range(15))


@functools.lru_cache(maxsize=1)
def load_model_config() -> dict:
    with open(POLICY_PATH) as f:
        raw = yaml.safe_load(f)
    with open(MODEL_WEIGHTS_PATH) as f:
        weights = yaml.safe_load(f)
    constants = {k: v["value"] for k, v in raw["constants"].items() if isinstance(v, dict) and "value" in v}
    return {
        "weights": {k: v for k, v in weights.items() if k.startswith("w_")},
        "min_history_successes": weights["min_history_successes"],
        "circular_gaussian_sigma_days": weights["circular_gaussian_sigma_days"],
        "population_dom_prior": tuple(raw["population_dom_prior"]),
        "min_cooling_off_days": constants["min_cooling_off_days"],
        "reserve_days_before_cycle_end": constants["reserve_days_before_cycle_end"],
        "pre_debit_notice_hours": constants["pre_debit_notice_hours"],
    }


@functools.lru_cache(maxsize=1)
def load_gap_term_prior() -> tuple[float, ...]:
    if not GAP_TERM_PATH.exists():
        return DEFAULT_GAP_TERM_PRIOR
    with open(GAP_TERM_PATH) as f:
        raw = yaml.safe_load(f)
    return tuple(raw["gap_term_prior"])
