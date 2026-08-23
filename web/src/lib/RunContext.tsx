"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api, Run } from "@/lib/api";

type RunTriple = { baseline?: Run; agent?: Run; oracle?: Run };

type RunContextValue = RunTriple & {
  runs: Run[];
  loading: boolean;
  error?: string;
};

const RunContext = createContext<RunContextValue>({ runs: [], loading: true });

function pickMostRecentTriple(runs: Run[]): RunTriple {
  const byCorpus = new Map<string, RunTriple>();
  const order: string[] = [];
  for (const r of runs) {
    if (!byCorpus.has(r.corpus_id)) {
      byCorpus.set(r.corpus_id, {});
      order.push(r.corpus_id);
    }
    const slot = byCorpus.get(r.corpus_id)!;
    const key = r.mode.toLowerCase() as "baseline" | "agent" | "oracle";
    if ((key === "baseline" || key === "agent" || key === "oracle") && !slot[key]) {
      slot[key] = r;
    }
  }
  for (const cid of order) {
    const g = byCorpus.get(cid)!;
    if (g.baseline && g.agent && g.oracle) return g;
  }
  return {};
}

export function RunProvider({ children }: { children: React.ReactNode }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    api
      .runs()
      .then((res) => setRuns(res.runs))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const triple = pickMostRecentTriple(runs);

  return (
    <RunContext.Provider value={{ runs, loading, error, ...triple }}>{children}</RunContext.Provider>
  );
}

export function useRuns() {
  return useContext(RunContext);
}
