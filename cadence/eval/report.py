"""Report generator — docs/10-EVALUATION.md "Report generation"."""
from __future__ import annotations

import pathlib
import statistics

import numpy as np
from sqlalchemy import text

from cadence.db import SessionLocal
from cadence.eval.auditor import audit
from cadence.eval.metrics import captured_of_headroom, compute_run_metrics
from cadence.eval.runners import load_corpus, run_agent, run_baseline, run_oracle
from cadence.models.tables import CorpusMeta
from cadence.sim.generator import generate_corpus, ground_truth_root_cause

REPORTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "reports"

_TABLES = (
    "ledger", "pending_actions", "decisions", "predictions", "classifications",
    "failure_events", "attempts", "messages", "payment_links", "contact_log",
    "cycles", "mandates", "customers", "issuer_health", "funding_calendar", "corpus_meta", "runs",
)


def _ensure_corpus_persisted(seed: int, n_customers: int) -> None:
    """Only one corpus lives in the DB at a time (issuer_health has no
    corpus-scoping column) — truncate before loading a different one."""
    session = SessionLocal()
    try:
        exists = session.query(CorpusMeta).filter_by(seed=seed, n_customers=n_customers).first()
        if exists is None:
            session.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
            session.commit()
    finally:
        session.close()
    if exists is None:
        generate_corpus(seed, n_customers=n_customers, write_to_db=True)


def run_all_arms(seed: int, n_customers: int = 300) -> dict:
    _ensure_corpus_persisted(seed, n_customers)
    g = load_corpus(seed, n_customers=n_customers)
    terminal_cycle_ids = {
        cyc_id
        for cyc_id in g.cycle_order
        if g.cycle_status[cyc_id] == "FAILED"
        and ground_truth_root_cause(g.world, g.cycle_first_code, cyc_id)
        in ("MANDATE_DEFECT", "INSTRUMENT_DEFECT", "RISK_BLOCK", "UNKNOWN")
    }
    session = SessionLocal()
    try:
        baseline = run_baseline(session, g, seed)
        agent = run_agent(session, g, seed)
        oracle = run_oracle(session, g, seed)

        metrics = {
            "BASELINE": compute_run_metrics(session, baseline.run_id, terminal_cycle_ids),
            "AGENT": compute_run_metrics(session, agent.run_id, terminal_cycle_ids),
            "ORACLE": compute_run_metrics(session, oracle.run_id, terminal_cycle_ids),
        }
        agent_audit = audit(session, agent.run_id)
        baseline_audit = audit(session, baseline.run_id)

        metrics["captured_of_headroom"] = captured_of_headroom(
            metrics["BASELINE"]["recovery_rate"], metrics["AGENT"]["recovery_rate"], metrics["ORACLE"]["recovery_rate"]
        )
        return {
            "seed": seed,
            "corpus_id": g.corpus_id,
            "metrics": metrics,
            "agent_audit": agent_audit,
            "baseline_audit": baseline_audit,
            "cause_mix": g.cause_mix,
        }
    finally:
        session.close()


def print_comparison_table(result: dict) -> None:
    m = result["metrics"]
    rows = [
        ("Recovery rate", "recovery_rate", "{:.1%}"),
        ("Recovered (paise)", "recovered_paise", "{:,.0f}"),
        ("Presentments used", "presentments_total", "{:.0f}"),
        ("Per successful recovery", "presentments_per_recovery", "{:.2f}"),
        ("Messages sent", "messages_total", "{:.0f}"),
        ("Per successful recovery", "messages_per_recovery", "{:.2f}"),
        ("Wasted on terminal cases", "wasted_presentments", "{:.0f}"),
    ]
    print(f"\n=== seed {result['seed']} — corpus {result['corpus_id']} ===")
    print(f"{'metric':28s}{'BASELINE':>14s}{'AGENT':>14s}{'ORACLE':>14s}")
    for label, key, fmt in rows:
        vals = [fmt.format(m[arm][key]) for arm in ("BASELINE", "AGENT", "ORACLE")]
        print(f"{label:28s}{vals[0]:>14s}{vals[1]:>14s}{vals[2]:>14s}")
    print(f"{'Compliance violations':28s}{len(result['baseline_audit']['violations']):>14d}"
          f"{len(result['agent_audit']['violations']):>14d}{'0':>14s}")
    print(f"\ncaptured_of_headroom (agent vs baseline, oracle = ceiling): {m['captured_of_headroom']:.1%}")
    print(f"agent independent-audit violations: {len(result['agent_audit']['violations'])} "
          f"(rows_audited={result['agent_audit']['rows_audited']}, auditor_version={result['agent_audit']['auditor_version']})")


def _bootstrap_ci(deltas: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    boots = [np.mean(rng.choice(deltas, size=len(deltas), replace=True)) for _ in range(n_boot)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def run_multi_seed(seeds: list[int], n_customers: int = 300) -> dict:
    results = [run_all_arms(seed, n_customers) for seed in seeds]
    baseline_rates = [r["metrics"]["BASELINE"]["recovery_rate"] for r in results]
    agent_rates = [r["metrics"]["AGENT"]["recovery_rate"] for r in results]
    oracle_rates = [r["metrics"]["ORACLE"]["recovery_rate"] for r in results]
    deltas = [a - b for a, b in zip(agent_rates, baseline_rates)]

    summary = {
        "seeds": seeds,
        "results": results,
        "baseline_mean": statistics.mean(baseline_rates),
        "baseline_spread": statistics.pstdev(baseline_rates) if len(baseline_rates) > 1 else 0.0,
        "agent_mean": statistics.mean(agent_rates),
        "agent_spread": statistics.pstdev(agent_rates) if len(agent_rates) > 1 else 0.0,
        "oracle_mean": statistics.mean(oracle_rates),
        "oracle_spread": statistics.pstdev(oracle_rates) if len(oracle_rates) > 1 else 0.0,
        "delta_mean": statistics.mean(deltas),
        "delta_ci": _bootstrap_ci(deltas) if len(deltas) > 1 else (deltas[0], deltas[0]),
    }
    return summary


def print_multi_seed_summary(summary: dict) -> None:
    print(f"\n=== {len(summary['seeds'])}-seed summary (seeds={summary['seeds']}) ===")
    print(f"BASELINE recovery rate: {summary['baseline_mean']:.1%} ± {summary['baseline_spread']:.1%}")
    print(f"AGENT    recovery rate: {summary['agent_mean']:.1%} ± {summary['agent_spread']:.1%}")
    print(f"ORACLE   recovery rate: {summary['oracle_mean']:.1%} ± {summary['oracle_spread']:.1%}")
    lo, hi = summary["delta_ci"]
    print(f"AGENT-BASELINE delta: {summary['delta_mean']:+.1%}  95% bootstrap CI [{lo:+.1%}, {hi:+.1%}]"
          f"{'  (crosses zero!)' if lo <= 0 <= hi else ''}")


def generate_html_report(summary: dict, out_dir: pathlib.Path | None = None) -> pathlib.Path:
    out_dir = pathlib.Path(out_dir) if out_dir else (REPORTS_DIR / "latest")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"

    first = summary["results"][0]
    m = first["metrics"]

    def fmt_row(label, key, fmt):
        return (
            f"<tr><td>{label}</td><td>{fmt.format(m['BASELINE'][key])}</td>"
            f"<td>{fmt.format(m['AGENT'][key])}</td><td>{fmt.format(m['ORACLE'][key])}</td></tr>"
        )

    rows_html = "".join([
        fmt_row("Recovery rate", "recovery_rate", "{:.1%}"),
        fmt_row("Recovered (paise)", "recovered_paise", "{:,.0f}"),
        fmt_row("Presentments used", "presentments_total", "{:.0f}"),
        fmt_row("Per successful recovery", "presentments_per_recovery", "{:.2f}"),
        fmt_row("Messages sent", "messages_total", "{:.0f}"),
        fmt_row("Wasted on terminal cases", "wasted_presentments", "{:.0f}"),
    ])

    lo, hi = summary["delta_ci"]
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Cadence — evaluation report</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #EEF2EA; color: #1B2432; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; max-width: 820px; }}
td, th {{ border: 1px solid #C9D2C4; padding: 6px 12px; font-variant-numeric: tabular-nums; }}
th {{ background: #F7F9F5; text-align: left; }}
h1, h2 {{ color: #1B2432; }}
.stamp {{ color: #5B3FA8; }}
</style></head><body>
<h1>Cadence — evaluation report</h1>
<h2>1. Corpus summary</h2>
<p>Seeds: {summary['seeds']} — cause mix (seed {first['seed']}): {first['cause_mix']}</p>

<h2>2. Three-arm comparison</h2>
<table><tr><th>Metric</th><th>Baseline</th><th>Agent</th><th>Oracle</th></tr>
{rows_html}
</table>
<p class="stamp">captured_of_headroom: {m['captured_of_headroom']:.1%}</p>

<h2>3. Multi-seed statistical honesty</h2>
<p>BASELINE {summary['baseline_mean']:.1%} ± {summary['baseline_spread']:.1%},
   AGENT {summary['agent_mean']:.1%} ± {summary['agent_spread']:.1%},
   ORACLE {summary['oracle_mean']:.1%} ± {summary['oracle_spread']:.1%}</p>
<p>AGENT-BASELINE delta: {summary['delta_mean']:+.1%}, 95% bootstrap CI [{lo:+.1%}, {hi:+.1%}]
   {'— crosses zero, interpret with caution' if lo <= 0 <= hi else '— clearly nonzero'}</p>

<h2>4. Compliance</h2>
<p>Agent independent-audit violations: {len(first['agent_audit']['violations'])}
   (rows_audited={first['agent_audit']['rows_audited']}, auditor_version={first['agent_audit']['auditor_version']},
   shares_code_with_gate={first['agent_audit']['shares_code_with_gate']})</p>
<p>Baseline independent-audit violations: {len(first['baseline_audit']['violations'])} (expected — no gate)</p>

<h2>5. Config appendix</h2>
<p>See config/policy.yaml, config/taxonomy.yaml, config/model_weights.yaml, config/gap_term.yaml for the full
   constants, taxonomy rules, and fitted weights (each constant carries a <code>source</code> field).</p>
</body></html>"""
    path.write_text(html)
    return path
