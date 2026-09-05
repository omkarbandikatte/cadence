const COLUMNS: { title: string; accent?: boolean; cards: { id: string; amount: string; tag: string }[] }[] = [
  {
    title: "Failed",
    cards: [
      { id: "cyc_9F2K…", amount: "₹2,400", tag: "balance shortfall" },
      { id: "cyc_1QRT…", amount: "₹899", tag: "instrument defect" },
    ],
  },
  {
    title: "In recovery",
    cards: [
      { id: "cyc_7XPL…", amount: "₹5,100", tag: "pre-debit notice sent" },
      { id: "cyc_2HDW…", amount: "₹1,250", tag: "retry scheduled day 4" },
    ],
  },
  {
    title: "Recovered",
    accent: true,
    cards: [
      { id: "cyc_4MNB…", amount: "₹3,600", tag: "recovered on day 3" },
    ],
  },
];

/** Adapted preview of the portfolio board — same shape as the real /app/cycles view. */
export function WorkflowPreview() {
  return (
    <div className="card p-4 md:p-6 shadow-2xl shadow-black/40 reveal" style={{ animationDelay: "420ms" }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {COLUMNS.map((col, colIdx) => (
          <div key={col.title} className="space-y-3 reveal" style={{ animationDelay: `${500 + colIdx * 90}ms` }}>
            <div className="eyebrow flex items-center gap-2">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ background: col.accent ? "var(--recovered)" : "var(--ink-muted)" }}
              />
              {col.title}
            </div>
            <div className="space-y-2">
              {col.cards.map((card, cardIdx) => (
                <div
                  key={card.id}
                  className="rounded-lg border border-[var(--rule)] bg-[var(--paper-3)] p-3 transition-all duration-200 hover:border-[var(--stamp)] hover:translate-y-[-1px]"
                  style={{ animationDelay: `${560 + colIdx * 90 + cardIdx * 70}ms` }}
                >
                  <div className="flex items-center justify-between">
                    <span className="id-cell">{card.id}</span>
                    <span className="tabular text-sm font-medium">{card.amount}</span>
                  </div>
                  <div className="text-xs text-[var(--ink-muted)] mt-2">{card.tag}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
