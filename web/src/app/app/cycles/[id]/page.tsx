"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useRuns } from "@/lib/RunContext";
import { api, CycleTimeline, MonthStripData } from "@/lib/api";
import { MonthStrip } from "@/components/MonthStrip";

const CONTRIBUTION_LABELS: Record<string, string> = {
  customer_term: "customer term",
  gap_term: "gap term",
  population_term: "population",
  issuer_term: "issuer",
  proximity_penalty: "proximity",
};

function PresentmentBoxes({ used, cap }: { used: number; cap: number }) {
  return (
    <span className="tabular">
      {Array.from({ length: cap }).map((_, i) => (
        <span key={i} className={i < used ? "text-[var(--stamp)]" : "text-[var(--rule)]"}>
          {i < used ? "■" : "□"}
        </span>
      ))}
    </span>
  );
}

export default function CycleTimelinePage() {
  const params = useParams<{ id: string }>();
  const { agent, loading: runsLoading } = useRuns();
  const [data, setData] = useState<CycleTimeline | null>(null);
  const [strip, setStrip] = useState<MonthStripData | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runId = agent?.id;

  useEffect(() => {
    if (!runId) return;
    api.cycleTimeline(params.id, runId).then(setData).catch((e) => setError(String(e)));
    api.monthStrip(params.id, runId).then(setStrip).catch(() => setStrip(null));
  }, [params.id, runId]);

  async function handleCancel() {
    if (!runId) return;
    setCancelling(true);
    try {
      await api.cancelPending(params.id, runId);
      const fresh = await api.cycleTimeline(params.id, runId);
      setData(fresh);
    } finally {
      setCancelling(false);
    }
  }

  if (runsLoading || !data) return <div className="eyebrow">loading…</div>;
  if (error) return <div className="text-[var(--at-risk)] text-sm">{error}</div>;

  const { cycle, mandate, customer, classification, prediction, timeline, next_action } = data;
  const contributions = prediction?.feature_contributions ?? {};
  const maxContribution = Math.max(...Object.values(contributions).map(Math.abs), 0.01);

  return (
    <div className="space-y-6">
      <div className="card p-5 flex flex-wrap items-center gap-x-8 gap-y-2">
        <div>
          <div className="eyebrow">customer</div>
          <div className="font-medium">{customer?.name ?? "—"}</div>
        </div>
        <div>
          <div className="eyebrow">amount</div>
          <div className="tabular">₹{(cycle.amount_paise / 100).toFixed(0)}</div>
        </div>
        <div>
          <div className="eyebrow">rail</div>
          <div>{mandate?.rail ?? "—"}</div>
        </div>
        <div>
          <div className="eyebrow">window</div>
          <div className="tabular text-sm">
            {cycle.period_start} → {cycle.period_end}
          </div>
        </div>
        <div>
          <div className="eyebrow">state</div>
          <div>{cycle.state}</div>
        </div>
        <div>
          <div className="eyebrow">presentments used</div>
          <PresentmentBoxes used={cycle.presentations_used} cap={3} />
        </div>
      </div>

      {strip && (
        <div className="card p-4">
          <MonthStrip
            dayRates={strip.day_rates}
            baselineDays={[]}
            agentDay={strip.attempt_days[0]}
            failureDay={strip.failure_day ?? undefined}
            animate={false}
            height={70}
          />
        </div>
      )}

      <div className="card p-5 space-y-3">
        <div className="eyebrow">diagnosis</div>
        {classification ? (
          <div className="grid grid-cols-[140px_1fr] gap-y-1 text-sm">
            <div className="text-[var(--ink-muted)]">root cause</div>
            <div>{classification.root_cause}</div>
            <div className="text-[var(--ink-muted)]">confidence</div>
            <div className="tabular">
              {classification.confidence} <span className="text-[var(--ink-muted)]">matched rule {classification.matched_rule}</span>
            </div>
            {prediction && (
              <>
                <div className="text-[var(--ink-muted)]">basis</div>
                <div>{prediction.basis}</div>
              </>
            )}
          </div>
        ) : (
          <div className="text-sm text-[var(--ink-muted)]">Not yet classified.</div>
        )}

        {prediction && (
          <div className="pt-2 space-y-1">
            <div className="text-xs text-[var(--ink-muted)]">why this day</div>
            {Object.entries(contributions).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2 text-xs">
                <div className="w-24 text-[var(--ink-muted)]">{CONTRIBUTION_LABELS[key] ?? key}</div>
                <div className="tabular w-14 text-right">{value.toFixed(2)}</div>
                <div className="flex-1 h-3 bg-[var(--rule)] rounded-sm overflow-hidden">
                  <div
                    className={value >= 0 ? "h-full bg-[var(--stamp)]" : "h-full bg-[var(--blocked)]"}
                    style={{ width: `${(Math.abs(value) / maxContribution) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card overflow-x-auto">
        <div className="eyebrow p-3 pb-0">timeline</div>
        <table className="w-full text-sm">
          <tbody>
            {timeline.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-[var(--rule)] last:border-0 align-top ${row.event_type === "GATE_BLOCKED" ? "text-[var(--blocked)]" : ""}`}
              >
                <td className="p-3 tabular whitespace-nowrap text-xs">{new Date(row.at).toISOString().slice(0, 16).replace("T", " ")}</td>
                <td className="p-3">
                  {row.event_type === "GATE_BLOCKED" ? <span className="id-cell">BLOCKED</span> : row.event_type}
                </td>
                <td className="p-3">{row.rationale}</td>
                <td className="p-3 tabular text-right">{row.amount_paise != null ? `₹${(row.amount_paise / 100).toFixed(0)}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {next_action && (
        <div className="card p-4 flex items-center justify-between">
          <div>
            <div className="eyebrow">next scheduled action</div>
            <div className="text-sm">
              {next_action.action_type} at{" "}
              <span className="tabular">{new Date(next_action.scheduled_for).toISOString().slice(0, 16).replace("T", " ")}</span>
            </div>
          </div>
          {next_action.cancellable && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="card px-3 py-1.5 text-sm hover:bg-[var(--rule)] disabled:opacity-50"
            >
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
