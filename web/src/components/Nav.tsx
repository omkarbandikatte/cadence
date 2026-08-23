"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useRuns } from "@/lib/RunContext";

const LINKS = [
  { href: "/", label: "Portfolio" },
  { href: "/compare", label: "Run comparison" },
  { href: "/ledger", label: "Ledger" },
  { href: "/cycles", label: "Cycles" },
];

export function Nav() {
  const pathname = usePathname();
  const { agent, loading, error } = useRuns();

  return (
    <header className="border-b border-[var(--rule)] bg-[var(--paper-2)]">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-6">
        <div className="flex items-center gap-6">
          <span className="font-semibold tracking-tight text-lg">
            CADENCE <span className="eyebrow font-normal">recurring debit recovery</span>
          </span>
          <nav className="flex gap-4">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={clsx(
                  "text-sm px-1 pb-0.5 border-b-2",
                  pathname === l.href
                    ? "border-[var(--stamp)] text-[var(--ink)]"
                    : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink)]"
                )}
              >
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="eyebrow">
          {loading ? "loading runs…" : error ? "no runs found" : agent ? `run ${agent.id.slice(0, 12)}` : "no agent run"}
        </div>
      </div>
    </header>
  );
}
