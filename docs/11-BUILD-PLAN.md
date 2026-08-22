# 11 — Build Plan

Written for **48 hours, team of 4**. Scaling notes at the end for other shapes.
Adjust once you know your actual constraints.

## Roles

| Role | Owns |
|---|---|
| **A — Core** | ingest, classify, policy, compliance gate, ledger |
| **B — Sim & Eval** | clock, generator, bank oracle, runners, metrics, auditor, report |
| **C — Model & Integrations** | funding-window model, Razorpay adapters, WhatsApp, payment links |
| **D — Frontend & Story** | dashboard, month strip, demo script, deck |

The critical path runs through **B**. If the corpus is late, nobody can measure
anything and the whole submission stalls. B starts first and B's milestones are
the ones that must not slip.

---

## Hour 0–2 — Foundations, everyone together

Do not split up yet. Two hours in one room saves ten later.

- [ ] Agree the schema in `03` line by line. Changing it on hour 20 is a disaster.
- [ ] Repo scaffold, `docker-compose` with Postgres, Alembic initial migration
- [ ] `Clock` protocol, `RealClock`, `VirtualClock` — **before anything else**
- [ ] `config/policy.yaml`, `config/taxonomy.yaml` skeletons committed
- [ ] `make` targets stubbed: `corpus`, `eval`, `report`, `demo`, `test`
- [ ] `.env.example`, Razorpay **test** keys in a shared secret store
- [ ] One person starts WhatsApp template submission **now** — see the note below

### ⚠️ Start the WhatsApp templates in hour 0

Templates need Meta review and that is not instant. Submit all four in hour one:
`predebit_notice_v1`, `topup_nudge_v1`, `payment_link_v1`, `reauth_v1`.

If approval has not landed by demo time, the `SimMessaging` adapter renders the
exact approved-format body into the UI and you narrate that live sending is
gated on Meta review. That is a fine answer *if you prepared for it*, and a
visibly broken demo if you did not. You have been through this review process
before — use that head start.

---

## Hour 2–10 — Parallel foundations

**B (critical path):**
- [ ] Customer segments and funding calendar generator
- [ ] Issuer outage generator with correlated windows
- [ ] `bank.py` oracle
- [ ] `make corpus SEED=42` produces 300 customers / ~1,200 cycles
- [ ] **V1 oracle run** — tune until the ceiling sits at 75–85%
- [ ] **V2** — confirm fixed-interval baseline underperforms clearly
- [ ] **V3** — plot success rate by day-of-month, confirm the peak exists

**Do not proceed past hour 10 until V1–V3 pass.** Everything downstream is
worthless if the world has no timing signal. This is the single most important
checkpoint in the build.

**A:**
- [ ] Models, migrations, ledger append-only trigger
- [ ] Ingest normaliser and idempotency
- [ ] Classifier with `taxonomy.yaml` loader
- [ ] Compliance gate skeleton with the `GateToken` type

**C:**
- [ ] Razorpay test-mode sandbox: create a subscription, trigger a failure, catch
      the webhook. Prove the round trip before building on it.
- [ ] Adapter interfaces plus `Sim` implementations

**D:**
- [ ] Next.js scaffold, tokens from `09`, the month strip component against
      hardcoded data. Build the signature element early — it is the artifact.

---

## Hour 10–22 — The loop closes

**A:**
- [ ] Policy table engine reading `policy.yaml`
- [ ] All compliance checks + the full test suite from `06`
- [ ] `test_no_action_ever_bypasses_gate` via the `GateToken`
- [ ] Ledger writer wired into every stage
- [ ] Cancellation rules

**B:**
- [ ] `run_baseline`, `run_agent`, `run_oracle`
- [ ] `metrics.py`
- [ ] First three-arm comparison numbers

**C:**
- [ ] Funding-window model, all five terms
- [ ] Fit `gap_term` on the train split
- [ ] Weight grid search
- [ ] Real Razorpay Payment Link creation in test mode

**D:**
- [ ] Portfolio and cycle timeline screens against the live API
- [ ] Ledger table

### Checkpoint at hour 22 — the only one that matters

**One failed debit goes end to end: ingest → classify → predict → gate → schedule
→ execute → recover → ledger.** With numbers on screen.

If this is not working at hour 22, stop building features and start cutting. Go
to the cut list below.

---

## Hour 22–34 — Depth and honesty

**A:** adversarial cases A1–A12 wired as injectable scenarios; escalation queue
**B:** independent auditor; multi-seed runs; report generator; per-segment
breakdown; calibration plot
**C:** classifier co-occurrence check (issuer corroboration); WhatsApp live path
if templates approved; LLM rationale writer with deterministic fallback
**D:** run comparison screen; the month strip overlay animation; Q&A drawer

---

## Hour 34–42 — Freeze and prove

- [ ] **Feature freeze at hour 34.** Enforce it. Every hackathon loses on the
      feature someone added at hour 44.
- [ ] Full run: `make clean && make corpus && make eval && make report`
- [ ] Five-seed run, mean ± spread
- [ ] Verify the regulatory constants — the VERIFY block in `06`
- [ ] Fill every `source` field
- [ ] `/sim/inject` tested live for case A2, the staged refusal
- [ ] Deck built from generated report numbers, never typed by hand
- [ ] Demo rehearsed end to end **three times**, timed

---

## Hour 42–48 — Buffer

Reserved for the thing that breaks. If nothing breaks: rehearse again, tighten
copy, record a backup video of the full demo. **Record the video regardless** —
it is your insurance against a dead venue network.

---

## Cut order — sacrifice from the bottom up

When you run out of time, cut in this order. Anything above the line is the
submission.

```
  KEEP — cutting these means you have no submission
  ────────────────────────────────────────────────
   1. Synthetic corpus with real timing signal (V1-V3 passing)
   2. Classifier + taxonomy
   3. Compliance gate + its test suite
   4. Funding-window model (customer + population terms minimum)
   5. Baseline vs agent comparison
   6. Append-only ledger with rationales
   7. Month strip + run comparison screen
   8. One staged refusal, live
  ────────────────────────────────────────────────
   9. Oracle arm                    ← cut here first
  10. Independent auditor
  11. Multi-seed runs
  12. Payment link fallback (real API → sim only)
  13. Q&A drawer
  14. Live WhatsApp (→ sim rendering)
  15. Calibration plot
  16. Issuer co-occurrence check
  17. Per-segment breakdown
  18. LLM rationale writer (→ deterministic templates)
  19. Cycle timeline screen (→ ledger filtered by cycle)
```

Items 9 and 10 hurt to cut because they are differentiators. Cut them anyway
before touching 1–8. A working core with an honest baseline beats a broken system
with an oracle arm.

---

## Other team shapes

**Team of 2, 48 hours:** cut everything below line item 12. One person takes
B+C (sim, model, eval), the other takes A+D (core, gate, UI). Drop the oracle,
the auditor, multi-seed, live WhatsApp, and the Q&A drawer from the plan
entirely rather than hoping. Target 150 failed cycles instead of 250.

**Team of 4, 24 hours:** drop to items 1–8 only, plus the ledger. Reduce the
corpus to 60 days and 150 customers. Skip the real Razorpay integration in
favour of the simulator and say so — the track cares about the recovery logic,
not your OAuth flow.

**Solo:** do not attempt this scope. Cut to `BALANCE_SHORTFALL` and
`MANDATE_DEFECT` only, two policy rules, six compliance checks, one screen, and
the baseline comparison. That is still a strong Track 03 submission because the
baseline table is the thing that wins, not the feature count.
