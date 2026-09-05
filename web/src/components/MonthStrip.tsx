"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";

export type MonthStripProps = {
  dayRates: number[]; // 31 values, 0..1 — historical success probability by day-of-month
  baselineDays?: number[]; // hollow markers
  agentDay?: number; // filled violet stamp
  failureDay?: number; // hairline vertical rule
  animate?: boolean;
  height?: number;
};

/** The signature element — docs/09-DASHBOARD.md. One glance shows the whole thesis:
 * baseline's hollow markers clustered in the dead zone, Cadence's stamp on the peak. */
export function MonthStrip({
  dayRates,
  baselineDays = [],
  agentDay,
  failureDay,
  animate = true,
  height = 120,
}: MonthStripProps) {
  const [revealed, setRevealed] = useState(!animate);
  const [showAgent, setShowAgent] = useState(!animate);

  useEffect(() => {
    if (!animate) return;
    const t1 = setTimeout(() => setRevealed(true), 50);
    const t2 = setTimeout(() => setShowAgent(true), 700);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [animate]);

  const max = Math.max(...dayRates, 0.01);

  return (
    <div className="w-full">
      <div className="eyebrow mb-2">Month strip — historical funding probability by day</div>
      <div className="relative flex items-end gap-[2px]" style={{ height }}>
        {dayRates.map((rate, idx) => {
          const day = idx + 1;
          const barHeight = Math.max(2, (rate / max) * height);
          const isBaseline = baselineDays.includes(day);
          const isAgent = agentDay === day;
          const isFailure = failureDay === day;
          return (
            <div key={day} className="relative flex-1 flex flex-col items-center justify-end h-full">
              {isFailure && (
                <div
                  className="absolute top-0 bottom-0 w-px bg-[var(--ink-muted)]"
                  style={{ left: "50%" }}
                  aria-hidden
                />
              )}
              <div
                className="w-full rounded-t-sm bg-[var(--rule)] transition-[height] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
                style={{ height: revealed ? barHeight : 2, transitionDelay: `${idx * 14}ms` }}
                title={`day ${day}: ${(rate * 100).toFixed(0)}%`}
              />
              {isBaseline && (
                <div
                  className={clsx(
                    "absolute w-2.5 h-2.5 rounded-full border-2 border-[var(--ink-muted)] bg-transparent transition-all duration-300",
                    revealed ? "opacity-100 scale-100" : "opacity-0 scale-50"
                  )}
                  style={{ bottom: barHeight + 4, transitionDelay: `${Math.min(idx * 14 + 80, 500)}ms` }}
                  aria-label={`baseline attempt on day ${day}`}
                />
              )}
              {isAgent && (
                <div
                  className={clsx(
                    "absolute w-3 h-3 rounded-full bg-[var(--stamp)] transition-all duration-500",
                    showAgent ? "opacity-100 scale-100" : "opacity-0 scale-50"
                  )}
                  style={{ bottom: barHeight + 4 }}
                  aria-label={`Cadence attempt on day ${day}`}
                />
              )}
              <div className="eyebrow mt-1" style={{ fontSize: 9 }}>
                {day % 5 === 0 || day === 1 ? day : ""}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4 mt-3 text-xs text-[var(--ink-muted)]">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-[var(--ink-muted)]" /> baseline attempt
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--stamp)]" /> Cadence attempt
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-px h-3 bg-[var(--ink-muted)]" /> failure date
        </span>
      </div>
    </div>
  );
}
