import clsx from "clsx";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2", className)}>
      <span
        aria-hidden
        className="inline-block w-6 h-6 rounded-md bg-gradient-to-br from-[var(--stamp)] to-[var(--stamp-deep)]"
      />
      <span className="font-semibold tracking-tight text-[var(--ink)]">Cadence</span>
    </span>
  );
}
