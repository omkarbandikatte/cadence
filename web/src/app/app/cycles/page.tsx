"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRuns } from "@/lib/RunContext";
import { api } from "@/lib/api";

type CycleRow = {
  cycle_id: string;
  customer_id: string | null;
  amount_paise: number;
  state: string;
  presentations_used: number;
};

export default function CyclesPage() {
  const { agent, loading: runsLoading } = useRuns();
  const [rows, setRows] = useState<CycleRow[]>([]);
  const [state, setState] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!agent) return;
    setLoading(true);
    api
      .cycles(agent.id, state || undefined)
      .then((res) => setRows(res.rows as CycleRow[]))
      .finally(() => setLoading(false));
  }, [agent, state]);

  if (runsLoading) return <div className="eyebrow">loading…</div>;
  if (!agent) return <div className="card p-8 text-center text-[var(--ink-muted)]">No agent run found.</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Cycles</h1>
        <select value={state} onChange={(e) => setState(e.target.value)} className="card px-2 py-1 text-sm">
          <option value="">all states</option>
          <option value="RECOVERED">recovered</option>
          <option value="IN_RECOVERY">in recovery</option>
          <option value="SCHEDULED">scheduled</option>
          <option value="ABANDONED">abandoned</option>
        </select>
      </div>
      <div className="card overflow-x-auto">
        {rows.length === 0 ? (
          <div className="p-8 text-center text-[var(--ink-muted)]">{loading ? "loading…" : "No cycles found."}</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--rule)] text-left">
                <th className="p-2 eyebrow font-normal">cycle</th>
                <th className="p-2 eyebrow font-normal">customer</th>
                <th className="p-2 eyebrow font-normal text-right">amount</th>
                <th className="p-2 eyebrow font-normal">state</th>
                <th className="p-2 eyebrow font-normal text-right">presentments used</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {rows.map((c) => (
                <tr key={c.cycle_id} className="border-b border-[var(--rule)] last:border-0">
                  <td className="p-2">
                    <Link href={`/cycles/${c.cycle_id}`} className="id-cell hover:bg-[var(--rule)]">
                      {c.cycle_id.slice(0, 14)}
                    </Link>
                  </td>
                  <td className="p-2">{c.customer_id && <span className="id-cell">{c.customer_id.slice(0, 12)}</span>}</td>
                  <td className="p-2 text-right">₹{(c.amount_paise / 100).toFixed(0)}</td>
                  <td className="p-2">{c.state}</td>
                  <td className="p-2 text-right">{c.presentations_used}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
