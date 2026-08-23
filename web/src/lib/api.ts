const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type RunMetrics = {
  failed_cycles: number;
  recovered_cycles: number;
  recovered_paise: number;
  at_risk_paise: number;
  recovery_rate: number;
  presentments_total: number;
  presentments_per_recovery: number;
  wasted_presentments: number;
  messages_total: number;
  messages_per_recovery: number;
  mean_days_to_recovery: number;
  checks_run: number;
  actions_blocked: number;
};

export type Run = { id: string; mode: string; corpus_id: string; seed: number; metrics: unknown };

export type CompareRow = {
  metric: string;
  label: string;
  baseline: number;
  agent: number;
  oracle: number;
  unit: string;
  higher_is_better: boolean;
  delta_abs: number;
  delta_rel: number | null;
  captured_of_available: number | null;
};

export type LedgerRow = {
  id: number;
  occurred_at: string;
  event_type: string;
  cycle_id: string | null;
  customer_id: string | null;
  mandate_id: string | null;
  amount_paise: number | null;
  rationale: string;
  payload: unknown;
};

export type ComplianceReport = {
  checks_run: number;
  actions_blocked: number;
  blocked_by_code: Record<string, number>;
  independent_audit: { violations_found: number; rows_audited: number; auditor_version: string };
  constants: { key: string; value: unknown; source: string }[];
};

export type MonthStripData = { day_rates: number[]; failure_day: number | null; attempt_days: number[] };

export type CycleTimeline = {
  cycle: { id: string; amount_paise: number; state: string; presentations_used: number; period_start: string; period_end: string };
  mandate: { id: string; rail: string; status: string } | null;
  customer: { id: string; name: string; issuer_code: string } | null;
  classification: { root_cause: string; confidence: string; matched_rule: string } | null;
  prediction: {
    curve: { day_offset: number; p: number }[];
    best_day_offset: number;
    basis: string;
    feature_contributions: Record<string, number>;
  } | null;
  timeline: { at: string; event_type: string; rationale: string; amount_paise: number | null; channel: string | null }[];
  next_action: { action_type: string; scheduled_for: string; cancellable: boolean } | null;
};

export const api = {
  runs: (mode?: string) => get<{ runs: Run[] }>(`/runs${mode ? `?mode=${mode}` : ""}`),
  runMetrics: (runId: string) => get<RunMetrics>(`/runs/${runId}/metrics`),
  compare: (baseline: string, agent: string, oracle: string) =>
    get<{ rows: CompareRow[]; run_ids: Record<string, string> }>(
      `/runs/compare?baseline=${baseline}&agent=${agent}&oracle=${oracle}`
    ),
  compareExemplar: (baseline: string, agent: string) =>
    get<{ cycle_id: string }>(`/runs/compare/exemplar?baseline=${baseline}&agent=${agent}`),
  monthStrip: (cycleId: string, runId: string) =>
    get<MonthStripData>(`/cycles/${cycleId}/month-strip?run_id=${runId}`),
  portfolio: (runId: string) =>
    get<{
      at_risk_paise: number;
      recovered_paise: number;
      in_recovery_count: number;
      recovered_count: number;
      escalated_to_you: number;
      recovery_rate: number;
      why_failing: { root_cause: string; count: number }[];
      pending_by_action: Record<string, number>;
    }>(`/portfolio?run_id=${runId}`),
  cycles: (runId: string, state?: string) =>
    get<{ rows: unknown[] }>(`/cycles?run_id=${runId}${state ? `&state=${state}` : ""}`),
  cycleTimeline: (cycleId: string, runId: string) => get<CycleTimeline>(`/cycles/${cycleId}?run_id=${runId}`),
  cancelPending: async (cycleId: string, runId: string) => {
    const res = await fetch(`${API_BASE}/cycles/${cycleId}/cancel-pending?run_id=${runId}`, { method: "POST" });
    if (!res.ok) throw new Error(`cancel-pending -> ${res.status}`);
    return res.json() as Promise<{ cancelled: number }>;
  },
  ledger: (params: Record<string, string | number | boolean | undefined>) => {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${v}`)
      .join("&");
    return get<{ rows: LedgerRow[] }>(`/ledger?${qs}`);
  },
  complianceReport: (runId: string) => get<ComplianceReport>(`/compliance/report?run_id=${runId}`),
};

export function formatPaise(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
