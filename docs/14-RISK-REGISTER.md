# 14 — Risk Register

Ordered by how badly each one kills the submission. Each has a **detection
signal** — the thing you check to know it is happening — because the failure mode
of a hackathon is not the unknown risk, it is the known risk nobody looked at
until hour 40.

---

## R1 — The corpus has no timing signal (**fatal**)

If failures are effectively independent draws, the funding-window model adds
nothing, the baseline matches the agent, and the entire thesis collapses. This is
the most likely way the project dies.

**Detect:** V1–V3 in `07`. Oracle ceiling outside 0.75–0.85; flat day-of-month
success curve; baseline scoring near the oracle.
**Mitigate:** Gate the whole build on V1–V3 passing by hour 10. Do not let anyone
build downstream until they do.
**Fallback:** Sharpen the post-credit spend spike until the optimal window is
2–4 days wide. If that fails, reduce credit sizes relative to debit amounts.

---

## R2 — Leakage inflates the result (**fatal, and embarrassing**)

`core/` reads `funding_calendar`, `segment`, or `is_outage`, or the train/test
split is by event rather than by customer. Result looks excellent, is worthless,
and a sharp judge finds it in one question.

**Detect:** V4 grep test in CI. Also: any recovery rate above the oracle ceiling
is definitionally leakage.
**Mitigate:** V4 in CI from hour 2. Split by customer, asserted in a test.
**Fallback:** If found late, re-run held-out only and report the corrected number.
Correcting your own number out loud costs less than being caught.

---

## R3 — WhatsApp templates not approved in time (**visible, embarrassing**)

Meta review is not instant, and a dead send in the middle of the demo undoes the
credibility the rest of the build earned.

**Detect:** Template status not `APPROVED` by hour 30.
**Mitigate:** Submit all four in hour one. You have run this gauntlet before —
use the head start.
**Fallback:** `SimMessaging` renders the exact approved-format body into the UI.
Narrate it: "live sending is gated on Meta review; this is the approved template
rendering." Prepared, this reads as competence. Unprepared, it reads as broken.

---

## R4 — A wrong regulatory constant, stated on stage (**credibility-fatal**)

Quoting a presentation cap or notice period that a Razorpay judge knows is wrong,
*on a compliance feature*, is worse than not shipping the feature.

**Detect:** Any constant in `policy.yaml` still marked `source: UNVERIFIED` at
hour 40.
**Mitigate:** Verify against current NPCI and RBI circulars during the hour 34–42
window. Fill every `source`.
**Fallback:** Leave it marked `UNVERIFIED` in config **and in the UI**, and say
so in the demo. Marked-unverified is rigour. Confidently-wrong is not.

---

## R5 — The gate gets bypassed somewhere (**thesis-fatal**)

One code path that presents or messages without the gate makes "every action is
gated" false, and the independent auditor will find it — which is good, but only
if you built the auditor.

**Detect:** The `GateToken` type check; the auditor's violation count.
**Mitigate:** Build the `GateToken` pattern in M3, before any adapter exists.
Five minutes, makes the claim structurally true.

---

## R6 — Scope creep past the freeze (**common, self-inflicted**)

Voice recovery. Multi-merchant. A real ML model. Every one is tempting at hour 30
and every one has ended a hackathon.

**Detect:** Anyone opening a new file after hour 34.
**Mitigate:** Freeze at 34, enforced by one named person. The cut list in `11` is
the authority when the argument starts.

---

## R7 — Uplift is real but too small to defend

The agent wins by three points and the confidence interval crosses zero.

**Detect:** Bootstrap CI in the multi-seed run.
**Mitigate:** Run five seeds early — hour 24, not hour 40 — so you still have
time to respond.
**Fallback:** Report it honestly with the interval, and pivot the emphasis to the
cost metrics: presentments per recovery and wasted presentments on terminal
cases. Those gaps come from classification rather than timing and are much larger
and more robust. A team that says "our timing uplift is underpowered at this
sample size, here is what is solid" reads as more competent than one quoting
three decimals on one run.

---

## R8 — The demo runs long

Five minutes evaporates. You reach the numbers at 4:50.

**Detect:** Rehearsal timings. If run one is over five minutes, the script is too
long, not your delivery.
**Mitigate:** Three timed rehearsals. Nothing computes live except the injected
case.
**Fallback:** Cut the escalation section. Never cut the month strip, the numbers,
or the refusal.

---

## R9 — Postgres or the environment dies on stage

**Mitigate:** Everything local, no cloud dependency in the demo path. Pre-seeded
DB snapshot. Backup video recorded by hour 42 regardless of how well things are
going.

---

## R10 — Judges have seen a better version of this internally

Razorpay works on recovery. Someone in the room may know more about it than you.

**Mitigate:** Do not claim novelty on the concept — claim it on the execution.
The defensible claims are: the funding-window model reading per-customer salary
rhythm, the gate as a type-level invariant, and the independent auditor. Lead
with what you measured, not with what you invented.
**Reframe:** "You almost certainly think about this already. What we wanted to
show is what it looks like when the retry decision is explainable per rupee and
the compliance boundary is structural rather than procedural."

---

## The two-line version

Everything above reduces to: **the corpus must have real signal, and the numbers
must survive a hostile question.** Guard V1–V4 with your life and run five seeds
early. Everything else is recoverable.
