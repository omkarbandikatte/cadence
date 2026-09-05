"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useRuns } from "@/lib/RunContext";
import { getMerchantId } from "@/lib/api";
import { Logo } from "@/components/Logo";

const LINKS = [
  { href: "/app", label: "Portfolio" },
  { href: "/app/compare", label: "Run comparison" },
  { href: "/app/ledger", label: "Ledger" },
  { href: "/app/cycles", label: "Cycles" },
];

export function Nav() {
  const pathname = usePathname();
  const { agent, loading, error } = useRuns();
  const merchantId = getMerchantId();

  return (
    <header className="border-b border-[var(--rule)] bg-[var(--paper-2)]">
      <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between gap-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="shrink-0">
            <Logo />
          </Link>
          <nav className="flex gap-4">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={clsx(
                  "text-base px-1 pb-0.5 border-b-2 transition-colors duration-200",
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
        <div className="eyebrow text-right">
          <div>{loading ? "loading runs…" : error ? "no runs found" : agent ? `run ${agent.id.slice(0, 12)}` : "no agent run"}</div>
          <div>merchant {merchantId}</div>
        </div>
      </div>
    </header>
  );
}
