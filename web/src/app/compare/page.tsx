"use client";

import { useEffect, useState } from "react";
import { useRuns } from "@/lib/RunContext";
import { api, CompareRow, formatPaise, MonthStripData } from "@/lib/api";
import { MonthStrip } from "@/components/MonthStrip";

function formatValue(row: CompareRow, arm: "baseline" | "agent" | "oracle"): string {
  const v = row[arm];
  if (row.unit === "ratio") return `${(v * 100).toFixed(1)}%`;
  if (row.unit === "paise") return formatPaise(v);
  if (Number.isNaN(v)) return "—";
  return Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1);
}

export default function ComparePage() {
  const { baseline, agent, oracle, loading: runsLoading } = useRuns();
  const [rows, setRows] = useState<CompareRow[] | null>(null);
  const [strip, setStrip] = useState<MonthStripData | null>(null);
  const [stripMarkers, setStripMarkers] = useState<{ agentDays: number[]; baselineDays: number[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!baseline || !agent || !oracle) return;
    api
      .compare(baseline.id, agent.id, oracle.id)
      .then((res) => setRows(res.rows))
      .catch((e) => setError(String(e)));

    api
      .compareExemplar(baseline.id, agent.id)
      .then((res) => Promise.all([
        api.monthStrip(res.cycle_id, agent.id),
        api.monthStrip(res.cycle_id, baseline.id),
      ]))
      .then(([agentStrip, baselineStrip]) => {
        setStrip({
          day_rates: agentStrip.day_rates,
          failure_day: agentStrip.failure_day,
          attempt_days: Array.from(new Set([...agentStrip.attempt_days, ...baselineStrip.attempt_days])),
        });
        setStripMarkers({ agentDays: agentStrip.attempt_days, baselineDays: baselineStrip.attempt_days });
      })
      .catch(() => setStrip(null));
  }, [baseline, agent, oracle]);

  if (runsLoading) return <Skeleton />;
  if (!baseline || !agent || !oracle) {
    return (
      <EmptyState message="No baseline/agent/oracle run triple found for the same corpus. Run `make eval SEED=42` to populate one." />
    );
  }

  const recoveryRow = rows?.find((r) => r.metric === "recovery_rate");
  const presentmentsRow = rows?.find((r) => r.metric === "presentments_total");
  const capturedPct = recoveryRow?.captured_of_available;
  const presentmentReduction =
    presentmentsRow && presentmentsRow.baseline
      ? (1 - presentmentsRow.agent / presentmentsRow.baseline) * 100
      : null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold mb-1">Run comparison</h1>
        <p className="text-sm text-[var(--ink-muted)]">
          Fixed-interval retry, no gate (baseline) vs Cadence (agent) vs the ground-truth ceiling (oracle).
        </p>
      </div>

      <div className="card p-5">
        {strip && stripMarkers ? (
          <MonthStrip
            dayRates={strip.day_rates}
            baselineDays={stripMarkers.baselineDays}
            agentDay={stripMarkers.agentDays[0]}
            failureDay={strip.failure_day ?? undefined}
            height={140}
          />
        ) : (
          <div className="eyebrow">No exemplar cycle yet — needs at least one cycle the agent recovered that the baseline did not.</div>
        )}
      </div>

      {error && <div className="text-sm text-[var(--at-risk)]">{error}</div>}

      {rows && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--rule)] text-left">
                <th className="p-3 eyebrow font-normal">Metric</th>
                <th className="p-3 eyebrow font-normal text-right">Baseline</th>
                <th className="p-3 eyebrow font-normal text-right">Cadence</th>
                <th className="p-3 eyebrow font-normal text-right">Oracle</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {rows.map((r) => (
                <tr key={r.metric} className="border-b border-[var(--rule)] last:border-0">
                  <td className="p-3">{r.label}</td>
                  <td className="p-3 text-right">{formatValue(r, "baseline")}</td>
                  <td className="p-3 text-right font-semibold">{formatValue(r, "agent")}</td>
                  <td className="p-3 text-right text-[var(--ink-muted)]">{formatValue(r, "oracle")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {capturedPct !== null && capturedPct !== undefined && presentmentReduction !== null && (
        <p className="text-base">
          Cadence captured{" "}
          <span className="font-semibold text-[var(--stamp)]">{(capturedPct * 100).toFixed(0)}%</span> of the
          headroom the baseline left on the table, using{" "}
          <span className="font-semibold text-[var(--stamp)]">{presentmentReduction.toFixed(0)}%</span> fewer
          regulated presentments.
        </p>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="h-6 w-64 bg-[var(--rule)] rounded" />
      <div className="h-36 card" />
      <div className="h-64 card" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div className="card p-8 text-center text-[var(--ink-muted)]">{message}</div>;
}
