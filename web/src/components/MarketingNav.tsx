import Link from "next/link";
import { Logo } from "@/components/Logo";

const NAV_LINKS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#compliance", label: "Compliance" },
  { href: "#results", label: "Results" },
];

export function MarketingNav() {
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--rule)] bg-[var(--paper)]/80 backdrop-blur">
      <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between gap-6">
        <Logo />
        <nav className="hidden md:flex items-center gap-6">
          {NAV_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-base text-[var(--ink-muted)] hover:text-[var(--ink)] transition-colors duration-200"
            >
              {l.label}
            </a>
          ))}
        </nav>
        <Link
          href="/app"
          className="interactive-btn text-base font-medium px-5 py-2.5 rounded-full bg-[var(--stamp)] text-[#1C1C1C] hover:opacity-90"
        >
          Open dashboard →
        </Link>
      </div>
    </header>
  );
}
