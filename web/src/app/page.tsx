import Link from "next/link";
import { MarketingNav } from "@/components/MarketingNav";
import { WorkflowPreview } from "@/components/WorkflowPreview";

const STAGES = [
  { n: "01", name: "Ingest", desc: "Normalise the webhook or batch replay into one FailureEvent." },
  { n: "02", name: "Classify", desc: "FailureEvent → root cause and confidence, against the failure taxonomy." },
  { n: "03", name: "Predict", desc: "Customer history + priors → the funding-window curve, day 0–14." },
  { n: "04", name: "Policy", desc: "Root cause + funding window + state → one proposed action." },
  { n: "05", name: "Gate", desc: "Every proposed action is checked against the compliance rules before anything happens." },
  { n: "06", name: "Execute", desc: "Presentment, message, or payment link — logged to an append-only ledger." },
];

const RESULTS = [
  { label: "Recovery rate", baseline: "29.8%", agent: "36.5%", oracle: "79.3%" },
  { label: "Compliance violations", baseline: "855", agent: "0", oracle: "0" },
  { label: "Wasted on terminal cases", baseline: "276", agent: "0", oracle: "0" },
];

export default function LandingPage() {
  return (
    <div>
      <MarketingNav />

      <section className="hero-gradient animated-grid border-b border-[var(--rule)] relative overflow-hidden">
        <div className="max-w-6xl mx-auto px-4 pt-20 pb-24 text-center relative z-10">
          <div className="eyebrow mb-5 reveal">AI Revenue Recovery · Razorpay Buildathon Track 03</div>
          <h1 className="text-5xl md:text-7xl font-semibold tracking-tight text-balance max-w-4xl mx-auto reveal" style={{ animationDelay: "80ms" }}>
            Find revenue at risk and win it back with compliant AI workflows
          </h1>
          <p className="mt-6 text-lg md:text-xl text-[var(--ink-muted)] max-w-3xl mx-auto reveal" style={{ animationDelay: "180ms" }}>
            Cadence closes the loop from payment failure detection to root-cause diagnosis, intervention
            selection, and bounded recovery execution with stopping rules and a full audit trail.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3 reveal" style={{ animationDelay: "260ms" }}>
            <Link
              href="/app"
              className="interactive-btn pulse-glow text-base font-medium px-6 py-3 rounded-full bg-[var(--stamp)] text-[#1C1C1C] hover:opacity-90"
            >
              Open dashboard →
            </Link>
            <a
              href="#how-it-works"
              className="interactive-btn text-base font-medium px-6 py-3 rounded-full border border-[var(--rule)] hover:border-[var(--stamp)]"
            >
              See how it works
            </a>
          </div>
        </div>
        <div className="max-w-4xl mx-auto px-4 pb-20 reveal relative z-10" style={{ animationDelay: "340ms" }}>
          <WorkflowPreview />
        </div>
        <div className="hero-orb w-[20rem] h-[20rem] left-[-6rem] top-[8rem] bg-[radial-gradient(circle,rgba(160,137,230,0.72),rgba(160,137,230,0))]" aria-hidden />
        <div className="hero-orb w-[24rem] h-[24rem] right-[-8rem] top-[2rem] bg-[radial-gradient(circle,rgba(52,211,153,0.3),rgba(52,211,153,0))]" style={{ animationDelay: "1.2s" }} aria-hidden />
        <div className="pointer-events-none absolute -bottom-28 left-1/2 w-[65rem] h-[24rem] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(160,137,230,0.26),rgba(160,137,230,0))]" />
      </section>

      <section id="how-it-works" className="max-w-6xl mx-auto px-4 py-20">
        <div className="eyebrow mb-2 text-center reveal">How it works</div>
        <h2 className="text-3xl md:text-4xl font-semibold text-center mb-12 reveal" style={{ animationDelay: "80ms" }}>Six stages, every one logged</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {STAGES.map((s, idx) => (
            <div key={s.n} className="card p-5 reveal" style={{ animationDelay: `${120 + idx * 60}ms` }}>
              <div className="tabular text-[var(--stamp)] text-sm mb-2">{s.n}</div>
              <div className="font-medium mb-1">{s.name}</div>
              <div className="text-base text-[var(--ink-muted)]">{s.desc}</div>
            </div>
          ))}
        </div>
      </section>

      <section id="compliance" className="max-w-6xl mx-auto px-4 py-20">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card p-8 reveal">
            <h3 className="text-xl font-semibold mb-2">The gate is not advisory</h3>
            <p className="text-base text-[var(--ink-muted)]">
              No code path may present a debit or send a message without passing through the compliance
              gate. A blocked action is a valid, logged outcome — never an exception to swallow. Every
              regulatory constant (presentation caps, notice periods, cooling-off windows) is read from
              config with a cited source, not hardcoded.
            </p>
          </div>
          <div className="card p-8 reveal" style={{ animationDelay: "90ms" }}>
            <h3 className="text-xl font-semibold mb-2">Every decision is explainable</h3>
            <p className="text-base text-[var(--ink-muted)]">
              Any decision the agent makes carries the inputs, the rule or score that fired, and a
              plain-English rationale a judge can read aloud. The ledger is append-only — corrections
              are new rows, never edits. Same seed, same config, identical results, every re-run.
            </p>
          </div>
        </div>
      </section>

      <section id="results" className="max-w-6xl mx-auto px-4 py-20">
        <div className="eyebrow mb-2 text-center reveal">Results</div>
        <h2 className="text-3xl md:text-4xl font-semibold text-center mb-2 reveal" style={{ animationDelay: "80ms" }}>Measured money recovered across the same batch</h2>
        <p className="text-base md:text-lg text-[var(--ink-muted)] text-center mb-10 reveal" style={{ animationDelay: "150ms" }}>
          Baseline, agent, and oracle run on the same corpus and simulator. We report money recovered,
          compliant escalation, stopping behavior, and independent-auditor outcomes side by side.
        </p>
        <div className="card overflow-x-auto reveal" style={{ animationDelay: "220ms" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--rule)] text-left">
                <th className="p-4 eyebrow font-normal">Metric</th>
                <th className="p-4 eyebrow font-normal text-right">Baseline</th>
                <th className="p-4 eyebrow font-normal text-right">Cadence</th>
                <th className="p-4 eyebrow font-normal text-right">Oracle</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {RESULTS.map((r) => (
                <tr key={r.label} className="border-b border-[var(--rule)] last:border-0">
                  <td className="p-4 font-sans">{r.label}</td>
                  <td className="p-4 text-right">{r.baseline}</td>
                  <td className="p-4 text-right font-semibold text-[var(--stamp)]">{r.agent}</td>
                  <td className="p-4 text-right text-[var(--ink-muted)]">{r.oracle}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-center mt-8 reveal" style={{ animationDelay: "300ms" }}>
          <Link href="/app/compare" className="interactive-btn text-sm font-medium text-[var(--stamp)] hover:underline">
            See the live run comparison →
          </Link>
        </div>
      </section>

      <footer className="border-t border-[var(--rule)] py-8">
        <div className="max-w-6xl mx-auto px-4 flex flex-wrap items-center justify-between gap-4 text-sm text-[var(--ink-muted)]">
          <span>Cadence — built for the Razorpay Buildathon, Track 03 (AI Revenue Recovery).</span>
          <Link href="/app" className="text-[var(--stamp)] hover:underline">
            Open dashboard
          </Link>
        </div>
      </footer>
    </div>
  );
}
