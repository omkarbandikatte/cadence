# 13 — Demo Script

Five minutes. Rehearse it three times, timed. The single most common way a good
hackathon build loses is a demo that spends four minutes on setup and thirty
seconds on the result.

---

## Before you start

- Corpus generated, all three arms run, report built. **Nothing computes live
  except the injected case.**
- Backup video recorded and on a local drive.
- Dashboard open on the run comparison screen, not the login page.
- Phone hotspot ready.

---

## 0:00–0:35 — The problem, in numbers not adjectives

> A merchant runs subscriptions on UPI Autopay and e-NACH. Some debits fail. What
> happens today is a calendar: retry on day one, day three, day five, then give
> up.
>
> That calendar is indifferent to the one thing that actually determines whether
> the money is there — when the customer gets paid. Insufficient balance is a
> timing problem, and the industry handles it as a terminal one.
>
> So we built an agent that answers three questions instead of one: why did this
> fail, when will the money be there, and am I allowed to try again.

No slide of statistics about the Indian subscription market. Judges have read the
brief. Start where your work starts.

---

## 0:35–1:40 — The signature graphic

Run comparison screen. Let the month strip animate once.

> This is one customer. The bars are how likely a debit is to clear on each day
> of the month — read off their own history. This customer is salaried, paid at
> month start.
>
> The debit failed on the 27th. [point] Here is what fixed-interval retry does:
> three attempts, on the 28th, the 30th, the 1st. All three land in the dead
> zone. All three fail. That's three regulated presentments burnt and the
> subscription is dead.
>
> [point at the violet mark] Here is what Cadence does. One attempt, on the 2nd.
> It clears.

Pause. That graphic is the whole pitch and it needs a beat of silence.

---

## 1:40–2:40 — The numbers, with the ceiling

Same screen, scroll to the table.

> Two hundred and forty-seven failed debits. Same synthetic book, same simulator,
> same seed for all three arms.
>
> Fixed-interval retry recovers ₹24,900. Cadence recovers ₹41,800.
>
> The third column is a perfect-information oracle that reads the customers'
> actual bank balances — the ceiling nobody can beat. We show it because it tells
> you how much of the available signal we actually captured, which is 44% of the
> headroom.
>
> And the row I care about most: presentments per recovery. Baseline burns 8.1.
> We use 2.2. Presentations are a capped, regulated resource — this isn't just
> more revenue, it's more revenue at a third of the regulatory cost.
>
> Across five seeds, the uplift holds at [X] plus or minus [Y].

The oracle column and the five-seed line are what separate this from a team
quoting one lucky run. Do not skip them for time.

---

## 2:40–3:40 — The staged refusal, live

Switch to the cycle timeline for a live-running mandate. Hit the inject shortcut
for case A2.

> This mandate has a presentment scheduled for Thursday. Watch — I'm going to
> revoke it right now, the way a customer would from their UPI app.
>
> [inject] The agent re-checks the gate at execution time, not at scheduling
> time. [point at the grey row] It refuses to present. It writes the refusal to
> the ledger with the reason. And it sends a re-authorisation link instead,
> because the customer probably still wants the service — they just cancelled
> the mandate.
>
> Notice this row isn't red. A block isn't an error. It's the system working.

Then, immediately:

> Every action goes through one gate. Not by convention — the adapters take a
> token that only the gate can mint, so bypassing it is a type error. And the
> zero in the violations column isn't the gate grading its own homework: a
> separate auditor re-derives legality from the ledger without sharing any code
> with the enforcement path.

That is the sixty seconds a payments judge remembers.

---

## 3:40–4:20 — Escalation and stopping

Portfolio screen, "Needs you" queue.

> Seven cycles are sitting here waiting for a human. Four are risk blocks — the
> bank declined for suspected fraud. We don't dun those customers. Messaging
> someone mid-fraud-investigation is not a revenue opportunity, so it goes to a
> person.
>
> Three are mandate cap mismatches, where the charge exceeds what the customer
> authorised. That needs a new mandate, not a retry.
>
> And four customers are churn-flagged after two consecutive failed cycles.
> Automation stops there. We're not trying to maximise recovery rate — we're
> maximising recovered rupees per unit of customer contact and per regulated
> presentment.

That last sentence is the thesis. Land it clearly.

---

## 4:20–5:00 — Honest limits, then close

Do this. Volunteering limits is the highest-return thirty seconds in the whole
demo.

> Three things I'd want you to know. This runs on synthetic data — we built the
> generator so a smarter policy genuinely wins, and we validated that against an
> oracle ceiling, but it is still our world. The regulatory constants are in
> config with a source field; [the verified ones] are checked against current
> circulars, [any unverified ones] are marked unverified in the UI. And the model
> is an interpretable hazard model, not a deep net — with a handful of successes
> per customer, anything larger is memorisation.
>
> The reason this is buildable on Razorpay: it's a scheduling layer over
> primitives you already ship. Webhooks, Subscriptions, Payment Links, pre-debit
> notifications. No core infrastructure changes. Thank you.

---

## Q&A — the eight questions you will get

**"Is this just one lucky seed?"**
Five seeds, mean ± spread, bootstrap CI on the delta. Report screen, section 8.

**"How do we know the baseline isn't a straw man?"**
It does what real fixed-interval retry does, including dunning and cap
compliance. It lacks exactly four things: classification, timing, the gate, and
link fallback. Named, in the report.

**"Would a simple 'retry on the 2nd' heuristic do this?"**
No — and we tested it. The `SALARIED_MONTH_END` cohort is 20% of the book and
that heuristic fails all of it. Per-segment breakdown, report section 3.

**"Won't the LLM do something unpredictable with someone's money?"**
The LLM never chooses an action. It writes rationale strings, drafts messages
from an approved template allowlist, and answers read-only questions. The
decision path is a table and a hazard model, both deterministic.

**"What about the customer experience — isn't this just better dunning?"**
Contact caps are enforced per customer, not per mandate. Quiet hours enforced.
Opt-out is absolute. We report messages per recovery, and it's lower than
baseline. Fewer, better-timed messages.

**"What happens when your classifier is wrong?"**
Asymmetric costs, reported separately rather than averaged into an F1. Unknown
codes are treated as terminal — we don't retry what we don't understand.

**"How does this handle real Razorpay failure codes?"**
The taxonomy is a config file, not code. Adding codes is a YAML edit. The
description-substring fallback and the unknown-terminal default mean an unmapped
code degrades safely rather than guessing.

**"What would you build next?"**
Learn the funding curve online from live outcomes rather than fitting once.
Extend the co-occurrence check into a real issuer-health service, since that
signal is useful to every merchant on the platform, not just for recovery.

---

## Failure drills — rehearse these too

| Breaks | Do this |
|---|---|
| Venue wifi dies | Everything runs locally. Say so and continue. |
| Postgres won't start | Pre-seeded SQLite snapshot with the finished run. |
| Inject endpoint fails on stage | Pre-recorded 20-second clip of A2, cued. |
| Laptop dies | Backup video on a phone, deck as a PDF on a second device. |
| You run over time | Cut the escalation section (3:40–4:20). Never cut the numbers or the refusal. |
