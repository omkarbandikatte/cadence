"use client";

import { useEffect, useState } from "react";
import { useRuns } from "@/lib/RunContext";

const CASE_IDS = [
  "A1_LATE_MONTH_TIMING",
  "A2_MANDATE_REVOKED",
  "A3_LINK_PAID_CONCURRENT",
  "A4_ISSUER_OUTAGE_OVERLAP",
  "A5_NO_FEASIBLE_WINDOW",
  "A6_CUSTOMER_OPT_OUT",
  "A7_AMOUNT_EXCEEDS_CAP",
  "A8_DUAL_MANDATE_CONTACT_CAP",
  "A9_UNMAPPED_GATEWAY_CODE",
  "A10_CONSECUTIVE_FAILURES_CHURN",
  "A11_QUIET_HOURS_DEFERRAL",
  "A12_DORMANT_REACTIVATION",
];

type InjectResult = {
  injected?: boolean;
  case?: string;
  ledger_ids?: number[];
  note?: string;
  detail?: string;
};

/** Hidden live-demo control panel — docs/12-AGENT-PROMPTS.md M8.
 * Toggle with Cmd/Ctrl+Shift+D. Deliberately not a visible button: a judge
 * should never stumble into "inject a compliance failure" by accident. */
export function DemoPanel() {
  const { runs, agent } = useRuns();
  const [open, setOpen] = useState(false);
  const [runId, setRunId] = useState("");
  const [caseId, setCaseId] = useState(CASE_IDS[1]);
  const [mandateId, setMandateId] = useState("");
  const [result, setResult] = useState<InjectResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "d") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (runId) return;
    if (agent) setRunId(agent.id);
    else if (runs.length > 0) setRunId(runs.find((r) => r.mode === "AGENT")?.id ?? runs[0].id);
  }, [agent, runs, runId]);

  async function fireTick(days: number) {
    if (!runId) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/sim/tick`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId, days }),
        }
      );
      setResult(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function fireInject() {
    if (!runId) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/sim/inject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: runId, case: caseId, mandate_id: mandateId || undefined }),
        }
      );
      setResult(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function firePauseAutomation() {
    setLoading(true);
    setResult(null);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/merchant/pause-automation`,
        { method: "POST" }
      );
      setResult(await r.json());
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-16" onClick={() => setOpen(false)}>
      <div
        className="card w-full max-w-lg p-5 space-y-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="eyebrow">Demo control panel</div>
          <button onClick={() => setOpen(false)} className="text-sm text-[var(--ink-muted)]">
            close (Esc)
          </button>
        </div>

        <label className="block text-sm space-y-1">
          <span className="text-[var(--ink-muted)]">Run</span>
          <select value={runId} onChange={(e) => setRunId(e.target.value)} className="w-full card px-2 py-1">
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.mode} · {r.id.slice(0, 14)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex gap-2">
          <button onClick={() => fireTick(1)} disabled={loading} className="card px-3 py-1.5 text-sm hover:bg-[var(--rule)]">
            Tick +1 day
          </button>
          <button onClick={() => fireTick(7)} disabled={loading} className="card px-3 py-1.5 text-sm hover:bg-[var(--rule)]">
            Tick +7 days
          </button>
          <button onClick={firePauseAutomation} disabled={loading} className="card px-3 py-1.5 text-sm hover:bg-[var(--rule)]">
            Pause all
          </button>
        </div>

        <div className="border-t border-[var(--rule)] pt-3 space-y-2">
          <div className="eyebrow">Inject adversarial case</div>
          <select value={caseId} onChange={(e) => setCaseId(e.target.value)} className="w-full card px-2 py-1 text-sm">
            {CASE_IDS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <input
            value={mandateId}
            onChange={(e) => setMandateId(e.target.value)}
            placeholder="mandate_id (optional — auto-picked if blank)"
            className="w-full card px-2 py-1 text-sm"
          />
          <button
            onClick={fireInject}
            disabled={loading || !runId}
            className="w-full card px-3 py-1.5 text-sm font-medium hover:bg-[var(--rule)] disabled:opacity-50"
          >
            {loading ? "Injecting…" : "Inject"}
          </button>
        </div>

        {result && (
          <div className="border-t border-[var(--rule)] pt-3 text-xs space-y-1">
            {result.note && <p>{result.note}</p>}
            {result.detail && <p className="text-[var(--at-risk)]">{result.detail}</p>}
            {result.ledger_ids && (
              <p className="tabular text-[var(--ink-muted)]">
                ledger ids: {result.ledger_ids.join(", ")}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
