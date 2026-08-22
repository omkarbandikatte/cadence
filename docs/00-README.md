# Cadence — document index

**Recurring debit failure recovery for UPI Autopay and e-NACH mandates.**
Razorpay Buildathon, Track 03 — AI Revenue Recovery.

> When a subscription debit fails, decide when the money will actually be there,
> whether it is legal to present again, and which channel and instrument to use —
> then execute inside hard regulatory bounds.

---

## The one-paragraph pitch

Industry-standard retry logic for failed recurring debits is a calendar: T+1, T+3,
T+5, give up. That schedule is indifferent to the single most predictive variable
in Indian recurring payments — *when the customer's account actually has balance*.
Insufficient funds is a timing problem being handled as a terminal one. Cadence
classifies why a debit failed, predicts the funding window from that customer's own
successful-debit history, checks every proposed action against mandate and
regulatory constraints, nudges before presenting, and falls back to a one-time
Payment Link when presentations are exhausted — converting a dead recurring charge
into collected revenue using primitives Razorpay already ships.

## Read in this order

**To understand the project**
1. `01-PRD.md` — scope, users, success criteria, out-of-scope
2. `02-ARCHITECTURE.md` — the six-stage loop and the simulation clock

**To build it**
3. `03-DATA-MODEL.md` — schema and enums
4. `04-FAILURE-TAXONOMY.md` — failure code to root cause
5. `05-DECISION-ENGINE.md` — funding-window model and policy table
6. `06-COMPLIANCE-GATE.md` — the hard rules
7. `07-SYNTHETIC-DATA.md` — the corpus generator
8. `08-API-CONTRACT.md` — endpoints
9. `09-DASHBOARD.md` — UI spec

**To win with it**
10. `10-EVALUATION.md` — baseline comparison and metrics
11. `11-BUILD-PLAN.md` — milestones and cut order
12. `12-AGENT-PROMPTS.md` — copy-paste prompts for the coding agent
13. `13-DEMO-SCRIPT.md` — the five-minute runbook
14. `14-RISK-REGISTER.md` — what kills this project and how to see it coming

`CLAUDE.md` goes at the repo root, not in `docs/`.

## The three artifacts that win the room

1. **The baseline table.** Same corpus, same simulator, fixed-interval retry vs
   Cadence. Recovery rate, rupees, attempts per recovery, messages per recovery,
   compliance violations. Almost nobody runs a baseline; without one, every
   recovery-rate claim is unfalsifiable.
2. **The staged refusal.** Live, feed the agent a revoked mandate. It classifies,
   hits the gate, declines to present, writes the refusal to the ledger with a
   reason. Deliberate restraint reads as production maturity.
3. **The ledger.** One scrollable table where every rupee, every message and every
   blocked action has a timestamped row and a plain-English rationale.
