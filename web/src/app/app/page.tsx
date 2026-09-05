"use client";

import { useEffect, useState } from "react";
import { useRuns } from "@/lib/RunContext";
import { api, formatPaise } from "@/lib/api";

const ROOT_CAUSE_LABELS: Record<string, string> = {
  BALANCE_SHORTFALL: "balance shortfall",
  MANDATE_DEFECT: "mandate defect",
  INSTRUMENT_DEFECT: "instrument defect",
  ISSUER_DEGRADED: "issuer degraded",
  TECHNICAL_TRANSIENT: "technical",
  RISK_BLOCK: "risk block",
  UNKNOWN: "unknown",
};

const ACTION_LABELS: Record<string, string> = {
  PRESENT_NOW: "presentments",
  SCHEDULE_PRESENTMENT: "presentments",
  PRE_DEBIT_NOTICE: "reminders",
  TOPUP_NUDGE: "reminders",
  REQUEST_REAUTH: "reminders",
  REQUEST_INSTRUMENT_UPDATE: "reminders",
  SEND_PAYMENT_LINK: "links",
};

export default function PortfolioPage() {
  const { agent, loading: runsLoading } = useRuns();
  const [data, setData] = useState<Awaited<ReturnType<typeof api.portfolio>> | null>(null);

  useEffect(() => {
    if (!agent) return;
    api.portfolio(agent.id).then(setData);
  }, [agent]);

  if (runsLoading) return <div className="eyebrow">loading…</div>;
  if (!agent) {
    return (
      <div className="card p-8 text-center text-[var(--ink-muted)]">
        No agent run found. Run <code>make eval SEED=42</code> to populate one.
      </div>
    );
  }
  if (!data) return <div className="eyebrow">loading portfolio…</div>;

  const maxCause = Math.max(...data.why_failing.map((r) => r.count), 1);
  const actionTotals: Record<string, number> = {};
  for (const [actionType, count] of Object.entries(data.pending_by_action)) {
    const label = ACTION_LABELS[actionType] ?? actionType.toLowerCase();
    actionTotals[label] = (actionTotals[label] ?? 0) + count;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Portfolio</h1>
        <button className="card px-3 py-1.5 text-sm hover:bg-[var(--rule)]">Pause all</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="At risk" value={formatPaise(data.at_risk_paise)} sub={`${data.in_recovery_count + data.recovered_count} cycles`} />
        <StatCard label="In recovery" value={`${data.in_recovery_count}`} sub="cycles" />
        <StatCard
          label="Recovered"
          value={formatPaise(data.recovered_paise)}
          sub={`${(data.recovery_rate * 100).toFixed(1)}%`}
          accent="recovered"
        />
        <StatCard label="Needs you" value={`${data.escalated_to_you}`} sub="cycles" accent="at-risk" />
      </div>

      <div className="card p-5">
        <div className="eyebrow mb-3">Why debits are failing</div>
        <div className="space-y-2">
          {data.why_failing.length === 0 && <div className="text-sm text-[var(--ink-muted)]">No classified failures yet.</div>}
          {data.why_failing.map((r) => (
            <div key={r.root_cause} className="flex items-center gap-3 text-sm">
              <div className="w-40 text-[var(--ink-muted)]">{ROOT_CAUSE_LABELS[r.root_cause] ?? r.root_cause.toLowerCase()}</div>
              <div className="flex-1 h-3 bg-[var(--rule)] rounded-sm overflow-hidden">
                <div className="h-full bg-[var(--stamp)]" style={{ width: `${(r.count / maxCause) * 100}%` }} />
              </div>
              <div className="tabular w-10 text-right">{r.count}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-5">
        <div className="eyebrow mb-3">Upcoming work</div>
        <div className="flex gap-6 text-sm tabular">
          {Object.entries(actionTotals).length === 0 && <span className="text-[var(--ink-muted)]">Nothing scheduled.</span>}
          {Object.entries(actionTotals).map(([label, count]) => (
            <span key={label}>
              <span className="font-semibold">{count}</span> <span className="text-[var(--ink-muted)]">{label}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "recovered" | "at-risk";
}) {
  return (
    <div className="card p-4">
      <div className="eyebrow mb-1">{label}</div>
      <div className={`text-2xl font-semibold tabular ${accent ? `text-[var(--${accent})]` : ""}`}>{value}</div>
      {sub && <div className="text-xs text-[var(--ink-muted)] mt-1">{sub}</div>}
    </div>
  );
}

