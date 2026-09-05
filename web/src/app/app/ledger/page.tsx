"use client";

import { useEffect, useMemo, useState } from "react";
import { useRuns } from "@/lib/RunContext";
import { api, LedgerRow } from "@/lib/api";

function toCsv(rows: LedgerRow[]): string {
  const header = ["id", "occurred_at", "event_type", "cycle_id", "customer_id", "mandate_id", "amount_paise", "rationale"];
  const lines = [header.join(",")];
  for (const r of rows) {
    const vals = [r.id, r.occurred_at, r.event_type, r.cycle_id ?? "", r.customer_id ?? "", r.mandate_id ?? "", r.amount_paise ?? "", `"${(r.rationale ?? "").replace(/"/g, '""')}"`];
    lines.push(vals.join(","));
  }
  return lines.join("\n");
}

export default function LedgerPage() {
  const { runs, agent, loading: runsLoading } = useRuns();
  const [runId, setRunId] = useState<string>("");
  const [eventType, setEventType] = useState("");
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (agent && !runId) setRunId(agent.id);
  }, [agent, runId]);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    api
      .ledger({ run_id: runId, event_type: eventType || undefined, blocked_only: blockedOnly || undefined, page_size: 200 })
      .then((res) => setRows(res.rows))
      .finally(() => setLoading(false));
  }, [runId, eventType, blockedOnly]);

  const eventTypes = useMemo(() => Array.from(new Set(rows.map((r) => r.event_type))).sort(), [rows]);

  function downloadCsv() {
    const blob = new Blob([toCsv(rows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ledger_${runId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (runsLoading) return <div className="eyebrow">loading…</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold">Ledger</h1>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            className="card px-2 py-1 text-sm tabular"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.mode} · {r.id.slice(0, 10)}
              </option>
            ))}
          </select>
          <select value={eventType} onChange={(e) => setEventType(e.target.value)} className="card px-2 py-1 text-sm">
            <option value="">all events</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <input type="checkbox" checked={blockedOnly} onChange={(e) => setBlockedOnly(e.target.checked)} />
            blocked only
          </label>
          <button onClick={downloadCsv} className="card px-3 py-1 text-sm hover:bg-[var(--rule)]">
            Export CSV
          </button>
        </div>
      </div>

      <div className="card overflow-x-auto">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-[var(--ink-muted)]">
            {loading ? "loading…" : "No ledger rows yet. Run a simulation to populate."}
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[var(--paper-2)]">
              <tr className="border-b border-[var(--rule)] text-left">
                <th className="p-2 eyebrow font-normal">#</th>
                <th className="p-2 eyebrow font-normal">time</th>
                <th className="p-2 eyebrow font-normal">event</th>
                <th className="p-2 eyebrow font-normal">cycle</th>
                <th className="p-2 eyebrow font-normal">customer</th>
                <th className="p-2 eyebrow font-normal text-right">amount</th>
                <th className="p-2 eyebrow font-normal">rationale</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={`border-b border-[var(--rule)] last:border-0 ${r.event_type === "GATE_BLOCKED" ? "text-[var(--blocked)]" : ""}`}
                >
                  <td className="p-2">{r.id}</td>
                  <td className="p-2 whitespace-nowrap">{new Date(r.occurred_at).toISOString().slice(0, 16).replace("T", " ")}</td>
                  <td className="p-2">
                    {r.event_type === "GATE_BLOCKED" ? (
                      <span className="id-cell">BLOCKED</span>
                    ) : (
                      r.event_type
                    )}
                  </td>
                  <td className="p-2">{r.cycle_id && <span className="id-cell">{r.cycle_id.slice(0, 12)}</span>}</td>
                  <td className="p-2">{r.customer_id && <span className="id-cell">{r.customer_id.slice(0, 12)}</span>}</td>
                  <td className="p-2 text-right">{r.amount_paise != null ? `₹${(r.amount_paise / 100).toFixed(0)}` : ""}</td>
                  <td className="p-2 max-w-md truncate" title={r.rationale}>{r.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
