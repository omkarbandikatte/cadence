# 09 — Dashboard Spec

Single merchant. A marketing landing page plus four dashboard screens. Built
for one job: let someone who has never seen this product understand, in under
three minutes, that money was recovered and that nothing improper happened.

---

## Design direction

A dark violet system: near-black surfaces, a lavender-violet accent, white
type. It reads as a modern product rather than a themed artifact, while
keeping the same restraint the ledger metaphor always called for — one accent
color, no decoration for its own sake, numbers that align.

### Tokens

```css
--paper:      #1C1C1C;  /* page background, near-black */
--paper-2:    #2C303D;  /* raised surfaces — cards, nav */
--paper-3:    #23262F;  /* nested surfaces inside cards */
--rule:       #383D4D;  /* hairlines, borders */
--ink:        #FFFFFF;  /* primary text */
--ink-muted:  #9BA0AE;
--stamp:      #A089E6;  /* violet accent — the single accent color */
--stamp-deep: #271A58;  /* deep violet, used in gradients and the logo mark */
--recovered:  #34D399;  /* success green */
--at-risk:    #E0A458;  /* amber, never red-alert red */
--blocked:    #7C8291;  /* grey — a block is normal, not an error */
```

Deliberately **no red**. A blocked action is correct behaviour; colouring it red
teaches the viewer to read your best feature as a failure. Blocks are grey and
neutral. Only genuine faults get amber. This rule survives the visual
refresh — it is a compliance-communication choice, not a color scheme choice.

### Type

- **Display & body:** Geist Sans (`next/font/local`, variable weight) — a
  squarish geometric grotesk, close in spirit to Aeonik. Section eyebrows are
  set in the monospace face, uppercase, tracked wide, like a form field label.
- **Data:** Geist Mono for every rupee figure, date, ID and count.
  Non-negotiable: numbers must align vertically down a column. This is still
  a ledger, just a dark one.

IDs keep the boxed-cell treatment — thin rules around each id, like the boxes
on a NACH form: `cyc_9F2K…`.

### Landing page

A marketing entry point lives at `/`; the dashboard lives at `/app/*`. The
landing page states the product in one headline, shows a live-shaped preview
of the portfolio board (Failed → In recovery → Recovered), explains the
six-stage loop, restates the two compliance guarantees in plain language, and
reports the actual baseline/agent/oracle numbers from a real evaluation run —
not fabricated testimonials or customer logos, since none exist yet.

### The signature element — the Month Strip

One horizontal band of 31 cells, day 1 to 31.

- Cell fill height encodes that customer's historical probability of a
  successful debit on that day-of-month.
- Baseline attempts plot as small hollow markers.
- Cadence's attempt plots as a filled violet stamp mark.
- The failure date is a hairline vertical rule.

On a `SALARIED_MONTH_START` customer this instantly shows three hollow markers
clustered in the dead zone at 28/29/31, and one violet stamp landing on the
peak at day 2. **That single graphic is the entire thesis of the project.** Put
it at the top of the comparison screen at full width, and repeat it small on
every cycle timeline.

Everything else stays quiet. This is the one place to spend boldness.

### Motion

One orchestrated moment only: on the run-comparison screen, the month strip
animates the baseline attempts landing first, then Cadence's single stamp. About
1.2 seconds, once, on load. Respect `prefers-reduced-motion`. No other animation
anywhere — scattered effects here would read as AI-generated filler.

---

## Screen 1 — Portfolio

The merchant's home. Answers "what is happening to my money."

```
┌──────────────────────────────────────────────────────────────┐
│ CADENCE            recurring debit recovery    [Pause all]   │
├──────────────────────────────────────────────────────────────┤
│  AT RISK          IN RECOVERY      RECOVERED     NEEDS YOU   │
│  ₹1,12,400        63 cycles        ₹41,800       7 cycles    │
│  247 cycles                        37.2%                     │
├──────────────────────────────────────────────────────────────┤
│  WHY DEBITS ARE FAILING                                      │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ balance shortfall              136          │
│  ▓▓▓▓▓ mandate defect                            27          │
│  ▓▓▓▓ instrument defect                          24          │
│  ▓▓▓ issuer degraded                             19          │
│  ▓▓ technical                                    12          │
│  ▓ risk block / unknown                          11          │
├──────────────────────────────────────────────────────────────┤
│  NEXT 48 HOURS                                               │
│  14 presentments · 22 reminders · 6 links expiring           │
└──────────────────────────────────────────────────────────────┘
```

"Needs you" is the escalation queue — risk blocks, unknown causes, mandate cap
mismatches. A dashboard that hands work back to a human is more credible than one
that claims to handle everything.

---

## Screen 2 — Cycle timeline

The screen you spend the most demo time on. One failed cycle, everything that
happened, in order.

Header: customer, amount, mandate rail, cycle window, current state, presentments
used of cap as filled boxes (`■ ■ □` = 2 of 3).

Then the **month strip** for this customer, small.

Then **diagnosis**, as a form block:
```
  ROOT CAUSE      balance shortfall
  CONFIDENCE      0.95      matched rule BAL_001
  BASIS           customer history · 4 prior successes
  WHY THIS DAY    customer term    0.61  ▓▓▓▓▓▓
                  gap term         0.19  ▓▓
                  population       0.14  ▓
                  issuer           0.00
                  proximity        −0.06 ▒
```

Then the timeline. Each row: timestamp, event, one-line rationale, amount if any.
Blocked rows render in grey with the block code as a small boxed tag — visually
present, not hidden, not alarming.

Then the next scheduled action with a **Cancel** control. Being able to cancel a
pending charge from the UI, live, is worth demonstrating.

---

## Screen 3 — Run comparison

The screen that wins it.

Full-width month strip at the top with the baseline/Cadence overlay and the
one-time animation. Below it, the table:

```
                          BASELINE     CADENCE      ORACLE
  Recovery rate              31.0%       52.0%       79.0%
  Recovered                ₹24,900     ₹41,800     ₹63,500
  Presentments used            624         288         214
  Per successful recovery      8.1         2.2         1.0
  Messages sent                247         319           0
  Per successful recovery      3.2         2.4         0.0
  Wasted on terminal cases     171           0           0
  Compliance violations          9           0           0
```

Below the table, one plain sentence rendered from the numbers:

> Cadence captured 44% of the headroom the baseline left on the table, using 54%
> fewer regulated presentments.

Include the oracle column. It shows you know your own ceiling and pre-empts the
"how do we know this is good" question before it is asked.

The baseline's non-zero violation count is legitimate and important: a naive
fixed-interval retry genuinely does present against revoked mandates and
genuinely does breach contact caps. That is not a straw man, it is the actual
behaviour of the thing being replaced. Label the column clearly as
"fixed-interval retry, no gate" so nobody thinks you handicapped it.

---

## Screen 4 — Ledger

A dense, filterable, monospaced table. Sticky header. Filters as form-style
chips: run, event type, cause, cycle, customer, blocked-only.

Columns: `#`, time, event, mandate, customer, amount, rationale, block code.

Two controls that matter:
- **Blocked only** toggle — one click to show the whole refusal history.
- **Export CSV** — an auditor's instinct is to want the file. Giving them one
  before they ask is a small, strong signal.

Empty state: "No ledger rows yet. Run a simulation to populate." Empty states
give direction, they do not apologise.

---

## Q&A drawer

Persistent slide-over on every screen. Ask in plain English, get an answer with
clickable ledger citations and the executed query shown in a collapsible block.

Seed it with three example questions so a judge can click rather than think:
- "Why did we not retry mandate mnd_0142?"
- "How much did we recover from customers on HDFC?"
- "Show every action we blocked in quiet hours."

---

## Quality floor

Responsive down to 390px — someone will open this on a phone. Visible keyboard
focus rings in `--stamp`. All numbers tabular-aligned. Loading skeletons that
match final layout so nothing jumps. Reduced motion respected. No spinner over
two seconds without a text status.
