"""The synthetic corpus builder — see docs/07-SYNTHETIC-DATA.md.

Builds a world where a smarter policy genuinely wins: four customer funding
segments, correlated issuer outages, and a cause mix across the failure
taxonomy. core/ never sees this module's ground truth directly; it only sees
what generate_corpus() persists as observable columns (failure codes, amounts,
observed_success_rate) — never funding_calendar, segment, or is_outage.
"""
from __future__ import annotations

import argparse
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import hashlib

import numpy as np

from cadence.db import SessionLocal
from cadence.models.tables import (
    Customer,
    Cycle,
    CorpusMeta,
    FundingCalendar,
    IssuerHealth,
    Mandate,
)
from cadence.sim import bank

START_DATE = date(2026, 1, 1)
DAYS = 90
# Cycles are only created for these three months, but the funding calendar
# runs longer (CALENDAR_DAYS) so a late-month failure's recovery window —
# which lands early in the *next* month — has real balance data to search.
MONTHS = [(2026, 1), (2026, 2), (2026, 3)]
CALENDAR_MONTHS = [(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]
CALENDAR_DAYS = 125

ISSUERS = ["HDFC", "SBIN", "ICIC", "AXIS", "PNB", "KKBK"]

SEGMENT_PROPORTIONS = {
    "SALARIED_MONTH_START": 0.40,
    "SALARIED_MONTH_END": 0.20,
    "GIG_IRREGULAR": 0.25,
    "SELF_EMPLOYED_LUMPY": 0.15,
}

SUBSCRIPTION_TIERS_PAISE = [9900, 14900, 19900, 29900, 49900, 99900, 149900, 499900]
SUBSCRIPTION_TIER_WEIGHTS = [0.25, 0.20, 0.15, 0.15, 0.10, 0.08, 0.05, 0.02]

RAILS = ["UPI_AUTOPAY", "ENACH", "CARD_RECURRING"]
RAIL_WEIGHTS = [0.6, 0.3, 0.1]

# Relative shares among the categories that need explicit generator scripting.
# BALANCE_SHORTFALL and MANDATE_DEFECT emerge structurally (funding calendar,
# mandate revocation/expiry/cap) rather than being scripted here.
SCRIPTED_CAUSE_WEIGHTS = {
    "ISSUER_DEGRADED": 12,
    "TECHNICAL_TRANSIENT": 8,
    "INSTRUMENT_DEFECT": 9,
    "RISK_BLOCK": 4,
    "UNKNOWN": 2,
}

INSTRUMENT_SUBTYPES = [
    ("ACCOUNT_CLOSED", "ACCOUNT_CLOSED", "the account behind this instrument is closed"),
    ("ACCOUNT_FROZEN", "ACCOUNT_FROZEN", "the account has been frozen"),
    ("ACCOUNT_DORMANT", "ACCOUNT_DORMANT", "the account is dormant"),
    ("CARD_EXPIRED", "CARD_EXPIRED", "the card on file has expired"),
]


def _shift_sunday(d: date) -> date:
    return d + timedelta(days=1) if d.weekday() == 6 else d


_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _seeded_id(rng: np.random.Generator, prefix: str) -> str:
    """A ULID-shaped id derived from the corpus's own seeded RNG, so
    `generate_corpus(seed, ...)` is byte-reproducible — real `new_id()`
    (models/base.py) embeds wall-clock time and OS randomness and must never
    be used inside the generator."""
    chars = "".join(_CROCKFORD_ALPHABET[i] for i in rng.integers(0, len(_CROCKFORD_ALPHABET), size=26))
    return f"{prefix}_{chars}"


def _salaried_calendar(rng: np.random.Generator, month_end: bool) -> dict[date, int]:
    credit_events: list[tuple[date, int]] = []
    for (y, m) in CALENDAR_MONTHS:
        dim = monthrange(y, m)[1]
        if month_end:
            day = int(np.clip(round(rng.normal(dim - 2, 1)), dim - 4, dim))
            mean_amount = 4_000_000
        else:
            day = int(np.clip(round(rng.normal(2, 1)), 1, 4))
            mean_amount = 4_500_000
        d = _shift_sunday(date(y, m, int(day)))
        amount = max(1_500_000, int(rng.normal(mean_amount, mean_amount * 0.26)))
        credit_events.append((d, amount))

    spike_frac = rng.uniform(0.11, 0.16)
    baseline_frac = rng.uniform(0.014, 0.024)
    spike_windows = [(c, c + timedelta(days=4), amt) for c, amt in credit_events]
    credit_by_date = {c: amt for c, amt in credit_events}

    cal: dict[date, int] = {}
    balance = 0.0
    for i in range(CALENDAR_DAYS):
        cur = START_DATE + timedelta(days=i)
        balance += credit_by_date.get(cur, 0)
        in_spike = next((amt for s, e, amt in spike_windows if s <= cur <= e), None)
        if in_spike is not None:
            spend = in_spike * spike_frac * rng.uniform(0.85, 1.15)
        else:
            past = [amt for c, amt in credit_events if c <= cur]
            ref = past[-1] if past else credit_events[0][1]
            spend = ref * baseline_frac * rng.uniform(0.7, 1.3)
        balance = max(0.0, balance - spend)
        cal[cur] = int(balance)
    return cal


def _gig_irregular_calendar(rng: np.random.Generator) -> dict[date, int]:
    cal: dict[date, int] = {}
    weekly_mean = int(rng.integers(500_000, 900_000))
    next_credit_day = int(rng.integers(0, 4))
    balance = 0.0
    for i in range(CALENDAR_DAYS):
        cur = START_DATE + timedelta(days=i)
        credit = 0
        if i >= next_credit_day:
            credit = max(0, int(rng.gamma(2.0, weekly_mean / 2)))
            next_credit_day = i + int(rng.integers(6, 10))
        spend = max(0.0, rng.normal(weekly_mean / 7 * 1.05, weekly_mean / 7 * 0.5))
        balance = max(0.0, balance + credit - spend)
        cal[cur] = int(balance)
    return cal


def _self_employed_calendar(rng: np.random.Generator) -> dict[date, int]:
    cal: dict[date, int] = {}
    lumpy_mean = int(rng.integers(5_000_000, 9_000_000))
    next_credit_day = int(rng.integers(5, 25))
    balance = 0.0
    for i in range(CALENDAR_DAYS):
        cur = START_DATE + timedelta(days=i)
        credit = 0
        if i >= next_credit_day:
            credit = max(0, int(rng.normal(lumpy_mean, lumpy_mean * 0.3)))
            next_credit_day = i + int(rng.integers(25, 46))
        spend = lumpy_mean / 32 * rng.uniform(0.85, 1.15)
        balance = max(0.0, balance + credit - spend)
        cal[cur] = int(balance)
    return cal


def _build_calendar(rng: np.random.Generator, segment: str) -> dict[date, int]:
    if segment == "SALARIED_MONTH_START":
        return _salaried_calendar(rng, month_end=False)
    if segment == "SALARIED_MONTH_END":
        return _salaried_calendar(rng, month_end=True)
    if segment == "GIG_IRREGULAR":
        return _gig_irregular_calendar(rng)
    return _self_employed_calendar(rng)


@dataclass
class GeneratedCorpus:
    corpus_id: str
    seed: int
    n_customers: int
    world: bank.World
    customer_segment: dict[str, str]
    mandate_customer: dict[str, str]
    cycle_mandate: dict[str, str]
    cycle_order: list[str]
    cycle_status: dict[str, str]  # "SUCCESS" | "FAILED"
    cycle_first_code: dict[str, str]
    train_customer_ids: set[str]
    holdout_customer_ids: set[str]
    adversarial_cases: dict[str, list[str]] = field(default_factory=dict)
    cause_mix: dict[str, int] = field(default_factory=dict)


def ground_truth_root_cause(world: bank.World, cycle_first_code: dict[str, str], cyc_id: str) -> str:
    """The generator's own answer to "why did this fail" — for scoring the
    classifier only. core/ must never call this."""
    designed = world.designed_causes.get(cyc_id)
    if designed is not None:
        return designed.root_cause
    code = cycle_first_code[cyc_id]
    if code in ("MANDATE_EXPIRED", "MANDATE_REVOKED", "AMOUNT_EXCEEDS_MANDATE"):
        return "MANDATE_DEFECT"
    if code == "ISSUER_DOWN":
        return "ISSUER_DEGRADED"
    return "BALANCE_SHORTFALL"


def generate_corpus(seed: int, n_customers: int = 300, write_to_db: bool = True) -> GeneratedCorpus:
    ss = np.random.SeedSequence(seed)
    (rng_cust, rng_cal, rng_mnd, rng_cyc, rng_out, rng_ovr, rng_bank, rng_split, rng_ids) = [
        np.random.default_rng(s) for s in ss.spawn(9)
    ]

    world = bank.World()

    # ---- customers -----------------------------------------------------
    segments = list(SEGMENT_PROPORTIONS.keys())
    seg_p = list(SEGMENT_PROPORTIONS.values())
    customer_ids: list[str] = []
    customer_segment: dict[str, str] = {}
    for i in range(n_customers):
        cid = _seeded_id(rng_ids, "cus")
        segment = rng_cust.choice(segments, p=seg_p)
        issuer = rng_cust.choice(ISSUERS)
        customer_ids.append(cid)
        customer_segment[cid] = segment
        world.customers[cid] = bank.CustomerGT(segment=segment, issuer_code=issuer)
        world.funding_calendar[cid] = _build_calendar(rng_cal, segment)

    # ---- mandates --------------------------------------------------------
    mandate_ids: list[str] = []
    mandate_customer: dict[str, str] = {}
    n_second_mandate = max(0, int(n_customers * 0.33))
    second_mandate_customers = list(
        rng_mnd.choice(customer_ids, size=n_second_mandate, replace=False)
    )
    mandate_customer_source = customer_ids + second_mandate_customers
    for cid in mandate_customer_source:
        mid = _seeded_id(rng_ids, "mnd")
        max_amount = int(rng_mnd.choice(SUBSCRIPTION_TIERS_PAISE, p=SUBSCRIPTION_TIER_WEIGHTS))
        debit_day = int(rng_mnd.integers(1, 29))
        rail = str(rng_mnd.choice(RAILS, p=RAIL_WEIGHTS))
        mandate_ids.append(mid)
        mandate_customer[mid] = cid
        world.mandates[mid] = bank.MandateGT(
            customer_id=cid,
            max_amount_paise=max_amount,
            status="ACTIVE",
            revoked_at=None,
            valid_until=START_DATE + timedelta(days=400),
            debit_day=debit_day,
            rail=rail,
        )

    # ---- structural mandate defects (revoked / expired) -----------------
    n_revoked = max(1, len(mandate_ids) // 50)
    n_expired = max(1, len(mandate_ids) // 100)
    pool = list(mandate_ids)
    rng_mnd.shuffle(pool)
    revoked_ids, pool = pool[:n_revoked], pool[n_revoked:]
    expired_ids, pool = pool[:n_expired], pool[n_expired:]
    for mid in revoked_ids:
        world.mandates[mid].status = "REVOKED"
        world.mandates[mid].revoked_at = START_DATE + timedelta(days=int(rng_mnd.integers(35, 65)))
    for mid in expired_ids:
        world.mandates[mid].valid_until = START_DATE + timedelta(days=int(rng_mnd.integers(40, 70)))

    # ---- cycles ------------------------------------------------------
    cycle_ids: list[str] = []
    cycle_mandate: dict[str, str] = {}
    cap_exceeding_candidates = pool[: max(1, len(mandate_ids) // 50)]
    for mid in mandate_ids:
        mandate = world.mandates[mid]
        # Debit dates for every calendar-month anchor, so a cycle's recovery
        # window can extend into the following month (a late-month failure
        # is recovered against next month's funding, not truncated at the
        # same month's end — see docs/07-SYNTHETIC-DATA.md adversarial case A1).
        debit_dates = []
        for (y, m) in CALENDAR_MONTHS:
            dim = monthrange(y, m)[1]
            debit_dates.append(date(y, m, min(mandate.debit_day, dim)))
        for idx, (y, m) in enumerate(MONTHS):
            debit_date = debit_dates[idx]
            period_start = debit_date
            period_end = debit_dates[idx + 1] - timedelta(days=1)
            amount = mandate.max_amount_paise
            if mid in cap_exceeding_candidates and idx == 1:
                amount = int(mandate.max_amount_paise * 1.5)
            cyc_id = _seeded_id(rng_ids, "cyc")
            cycle_ids.append(cyc_id)
            cycle_mandate[cyc_id] = mid
            world.cycles[cyc_id] = bank.CycleGT(
                mandate_id=mid,
                amount_paise=amount,
                period_start=period_start,
                period_end=period_end,
                debit_date=debit_date,
            )

    # ---- issuer health: background outages -----------------------------
    for issuer in ISSUERS:
        for d in range(CALENDAR_DAYS):
            cur = START_DATE + timedelta(days=d)
            world.issuer_days[(issuer, cur)] = bank.IssuerDayGT(
                observed_success_rate=float(np.clip(rng_out.normal(0.92, 0.03), 0.75, 0.99)),
                is_outage=False,
            )
        n_windows = int(rng_out.integers(1, 4))
        for _ in range(n_windows):
            start_day = int(rng_out.integers(0, DAYS - 2))
            length = int(rng_out.integers(1, 3))
            severity = float(rng_out.uniform(0.3, 0.9))
            for d in range(start_day, min(DAYS, start_day + length)):
                cur = START_DATE + timedelta(days=d)
                world.issuer_days[(issuer, cur)] = bank.IssuerDayGT(
                    observed_success_rate=round(1 - severity, 3), is_outage=True
                )

    # ---- natural pass: resolve every cycle's scheduled debit in order ---
    # Tie-break on creation order (deterministic), never on the ULID string
    # itself — ULIDs embed wall-clock time and are not seed-reproducible.
    cycle_creation_index = {c: i for i, c in enumerate(cycle_ids)}
    cycle_order = sorted(cycle_ids, key=lambda c: (world.cycles[c].debit_date, cycle_creation_index[c]))
    cycle_status: dict[str, str] = {}
    cycle_first_code: dict[str, str] = {}
    for cyc_id in cycle_order:
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        result = bank.resolve(world, cyc_id, cycle.debit_date, attempt_no=1, rng=rng_bank)
        if result.succeeded:
            bank.apply_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
            cycle_status[cyc_id] = "SUCCESS"
            cycle_first_code[cyc_id] = ""
        else:
            cycle_status[cyc_id] = "FAILED"
            cycle_first_code[cyc_id] = result.gateway_code

    natural_fail_count = sum(1 for s in cycle_status.values() if s == "FAILED")
    success_pool = [c for c, s in cycle_status.items() if s == "SUCCESS"]
    rng_ovr.shuffle(success_pool)

    # ---- scripted overrides on top of naturally-successful cycles -------
    total_scripted_weight = sum(SCRIPTED_CAUSE_WEIGHTS.values())
    # Target: scripted categories should be roughly as large, combined, as the
    # remaining share once BALANCE_SHORTFALL (~55%) and MANDATE_DEFECT (~10%)
    # are accounted for — i.e. ~35% of natural_fail_count more on top.
    budget = max(20, int(natural_fail_count * (total_scripted_weight / 55)))
    counts = {
        cause: max(1, round(budget * weight / total_scripted_weight))
        for cause, weight in SCRIPTED_CAUSE_WEIGHTS.items()
    }

    cursor = 0

    def _take(n: int) -> list[str]:
        nonlocal cursor
        chunk = success_pool[cursor : cursor + n]
        cursor += n
        return chunk

    designed_tags: dict[str, list[str]] = {cause: [] for cause in SCRIPTED_CAUSE_WEIGHTS}

    for cyc_id in _take(counts["INSTRUMENT_DEFECT"]):
        subtype, code, desc = INSTRUMENT_SUBTYPES[int(rng_ovr.integers(0, len(INSTRUMENT_SUBTYPES)))]
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        bank.undo_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
        world.designed_causes[cyc_id] = bank.DesignedCause("INSTRUMENT_DEFECT", subtype, code, desc)
        cycle_status[cyc_id] = "FAILED"
        cycle_first_code[cyc_id] = code
        designed_tags["INSTRUMENT_DEFECT"].append(cyc_id)

    for cyc_id in _take(counts["RISK_BLOCK"]):
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        bank.undo_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
        world.designed_causes[cyc_id] = bank.DesignedCause(
            "RISK_BLOCK", "NONE", "DO_NOT_HONOUR", "issuer declined for suspected fraud"
        )
        cycle_status[cyc_id] = "FAILED"
        cycle_first_code[cyc_id] = "DO_NOT_HONOUR"
        designed_tags["RISK_BLOCK"].append(cyc_id)

    for cyc_id in _take(counts["UNKNOWN"]):
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        bank.undo_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
        world.designed_causes[cyc_id] = bank.DesignedCause(
            "UNKNOWN", "NONE", "U99_UNCLASSIFIED", "gateway returned a code absent from the taxonomy"
        )
        cycle_status[cyc_id] = "FAILED"
        cycle_first_code[cyc_id] = "U99_UNCLASSIFIED"
        designed_tags["UNKNOWN"].append(cyc_id)

    for cyc_id in _take(counts["TECHNICAL_TRANSIENT"]):
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        bank.undo_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
        world.designed_causes[cyc_id] = bank.DesignedCause(
            "TECHNICAL_TRANSIENT", "NONE", "GATEWAY_TIMEOUT", "the gateway timed out"
        )
        cycle_status[cyc_id] = "FAILED"
        cycle_first_code[cyc_id] = "GATEWAY_TIMEOUT"
        designed_tags["TECHNICAL_TRANSIENT"].append(cyc_id)

    for cyc_id in _take(counts["ISSUER_DEGRADED"]):
        cycle = world.cycles[cyc_id]
        mandate = world.mandates[cycle.mandate_id]
        customer = world.customers[mandate.customer_id]
        bank.undo_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
        for d in range(-1, 2):
            day = cycle.debit_date + timedelta(days=d)
            world.issuer_days[(customer.issuer_code, day)] = bank.IssuerDayGT(
                observed_success_rate=0.08, is_outage=True
            )
        result = bank.resolve(world, cyc_id, cycle.debit_date, attempt_no=1, rng=rng_bank)
        if result.succeeded:
            bank.apply_debit(world, mandate.customer_id, cycle.debit_date, cycle.amount_paise)
            cycle_status[cyc_id] = "SUCCESS"
            cycle_first_code[cyc_id] = ""
        else:
            world.designed_causes[cyc_id] = bank.DesignedCause(
                "ISSUER_DEGRADED", "ISSUER_DOWN", result.gateway_code, result.gateway_desc
            )
            cycle_status[cyc_id] = "FAILED"
            cycle_first_code[cyc_id] = result.gateway_code
        designed_tags["ISSUER_DEGRADED"].append(cyc_id)

    # ---- adversarial cases (static ones; execution-time ones deferred) --
    adversarial_cases: dict[str, list[str]] = {}

    a1 = [
        c
        for c in cycle_order
        if cycle_status[c] == "FAILED"
        and cycle_first_code[c] == "INSUFFICIENT_FUNDS"
        and customer_segment[mandate_customer[cycle_mandate[c]]] == "SALARIED_MONTH_START"
        and world.cycles[c].debit_date.day >= 25
    ]
    adversarial_cases["A1_LATE_MONTH_FAILURE_EARLY_MONTH_FUNDING"] = a1[:3]

    a4 = [c for c in designed_tags["ISSUER_DEGRADED"] if cycle_status[c] == "FAILED"]
    adversarial_cases["A4_ISSUER_OUTAGE_OVERLAPS_BALANCE_SHORTFALL"] = a4[:3]

    a5 = [
        c
        for c in cycle_order
        if cycle_status[c] == "FAILED"
        and cycle_first_code[c] == "INSUFFICIENT_FUNDS"
        and (world.cycles[c].period_end - world.cycles[c].debit_date).days <= 2
    ]
    adversarial_cases["A5_NO_FEASIBLE_WINDOW_BEFORE_CYCLE_END"] = a5[:3]

    a7 = [c for c in cycle_ids if world.cycles[c].amount_paise > world.mandates[cycle_mandate[c]].max_amount_paise]
    adversarial_cases["A7_AMOUNT_EXCEEDS_MANDATE_CAP"] = a7[:3]

    customer_failed_mandates: dict[str, set[str]] = {}
    for c in cycle_ids:
        if cycle_status[c] == "FAILED":
            mid = cycle_mandate[c]
            cid = mandate_customer[mid]
            customer_failed_mandates.setdefault(cid, set()).add(mid)
    a8 = [cid for cid, mids in customer_failed_mandates.items() if len(mids) >= 2]
    adversarial_cases["A8_SAME_CUSTOMER_TWO_MANDATES_BOTH_FAILING"] = a8[:3]

    a9 = list(designed_tags["UNKNOWN"])
    adversarial_cases["A9_UNMAPPED_GATEWAY_CODE"] = a9[:3]

    mandate_cycle_lists: dict[str, list[str]] = {}
    for c in cycle_order:
        mandate_cycle_lists.setdefault(cycle_mandate[c], []).append(c)
    a10 = []
    for mid, cs in mandate_cycle_lists.items():
        statuses = [cycle_status[c] for c in cs]
        if any(statuses[i] == statuses[i + 1] == "FAILED" for i in range(len(statuses) - 1)):
            a10.append(mid)
    adversarial_cases["A10_TWO_CONSECUTIVE_FAILED_CYCLES"] = a10[:3]

    adversarial_cases["A2_MANDATE_REVOKED_MID_SCHEDULE"] = []  # deferred to M5/M8 (live execution dynamics)
    adversarial_cases["A3_CUSTOMER_PAYS_LINK_WHILE_PENDING"] = []  # deferred to M5/M8
    adversarial_cases["A6_CUSTOMER_OPTS_OUT_MID_RECOVERY"] = []  # deferred to M5/M8
    adversarial_cases["A11_RECOVERY_LANDS_IN_QUIET_HOURS"] = []  # deferred to M5/M8
    adversarial_cases["A12_DORMANT_ACCOUNT_REACTIVATED"] = []  # deferred to M5/M8

    # ---- train/held-out split, BY CUSTOMER --------------------------------
    shuffled_customers = list(customer_ids)
    rng_split.shuffle(shuffled_customers)
    split_point = int(len(shuffled_customers) * 0.4)
    train_customer_ids = set(shuffled_customers[:split_point])
    holdout_customer_ids = set(shuffled_customers[split_point:])

    # ---- cause mix (realized) ---------------------------------------------
    cause_mix: dict[str, int] = {}
    for c in cycle_ids:
        if cycle_status[c] != "FAILED":
            continue
        cause = ground_truth_root_cause(world, cycle_first_code, c)
        cause_mix[cause] = cause_mix.get(cause, 0) + 1

    corpus_id = _seeded_id(rng_ids, "cor")
    generated = GeneratedCorpus(
        corpus_id=corpus_id,
        seed=seed,
        n_customers=n_customers,
        world=world,
        customer_segment=customer_segment,
        mandate_customer=mandate_customer,
        cycle_mandate=cycle_mandate,
        cycle_order=cycle_order,
        cycle_status=cycle_status,
        cycle_first_code=cycle_first_code,
        train_customer_ids=train_customer_ids,
        holdout_customer_ids=holdout_customer_ids,
        adversarial_cases=adversarial_cases,
        cause_mix=cause_mix,
    )

    if write_to_db:
        _persist(generated, customer_ids, mandate_ids, cycle_ids)

    return generated


def _persist(g: GeneratedCorpus, customer_ids, mandate_ids, cycle_ids) -> None:
    session = SessionLocal()
    try:
        for cid in customer_ids:
            cust = g.world.customers[cid]
            digest = int(hashlib.sha256(cid.encode()).hexdigest(), 16)
            session.add(
                Customer(
                    id=cid,
                    name=f"Customer {cid[-6:]}",
                    phone_e164=f"+9198{digest % 100000000:08d}",
                    email=f"{cid.lower()}@example.test",
                    issuer_code=cust.issuer_code,
                    segment=cust.segment,
                )
            )
        session.flush()

        for mid in mandate_ids:
            m = g.world.mandates[mid]
            session.add(
                Mandate(
                    id=mid,
                    customer_id=m.customer_id,
                    rail=m.rail,
                    status=m.status,
                    max_amount_paise=m.max_amount_paise,
                    frequency="MONTHLY",
                    debit_day=m.debit_day,
                    valid_from=START_DATE,
                    valid_until=m.valid_until,
                    revoked_at=(
                        None
                        if m.revoked_at is None
                        else datetime.combine(m.revoked_at, time(), tzinfo=timezone.utc)
                    ),
                )
            )
        session.flush()

        for cyc_id in cycle_ids:
            c = g.world.cycles[cyc_id]
            state = "RECOVERED" if g.cycle_status[cyc_id] == "SUCCESS" else "IN_RECOVERY"
            session.add(
                Cycle(
                    id=cyc_id,
                    mandate_id=c.mandate_id,
                    period_start=c.period_start,
                    period_end=c.period_end,
                    amount_paise=c.amount_paise,
                    state=state,
                    presentations_used=1,
                )
            )
        session.flush()

        for (issuer, day), gt in g.world.issuer_days.items():
            session.add(
                IssuerHealth(
                    issuer_code=issuer,
                    as_of_date=day,
                    observed_success_rate=gt.observed_success_rate,
                    is_outage=gt.is_outage,
                )
            )

        for cid, cal in g.world.funding_calendar.items():
            for day, balance in cal.items():
                session.add(FundingCalendar(customer_id=cid, date=day, balance_paise=balance))

        session.add(
            CorpusMeta(
                id=g.corpus_id,
                seed=g.seed,
                n_customers=g.n_customers,
                n_mandates=len(mandate_ids),
                n_cycles=len(cycle_ids),
                cause_mix=g.cause_mix,
                adversarial_cases={
                    **g.adversarial_cases,
                    "_split": {
                        "train": sorted(g.train_customer_ids),
                        "holdout": sorted(g.holdout_customer_ids),
                    },
                },
            )
        )
        session.commit()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-customers", type=int, default=300)
    args = parser.parse_args()

    g = generate_corpus(args.seed, n_customers=args.n_customers, write_to_db=True)
    n_failed = sum(1 for s in g.cycle_status.values() if s == "FAILED")
    print(f"corpus_id={g.corpus_id} seed={g.seed}")
    print(f"customers={g.n_customers} mandates={len(g.mandate_customer)} cycles={len(g.cycle_status)}")
    print(f"failed_cycles={n_failed}")
    print(f"cause_mix={g.cause_mix}")


if __name__ == "__main__":
    main()
