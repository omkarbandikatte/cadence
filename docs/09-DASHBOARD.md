# 09 — Dashboard Spec

Single merchant. Four screens. Built for one job: let someone who has never seen
this product understand, in under three minutes, that money was recovered and
that nothing improper happened.

---

## Design direction

Most fintech dashboards default to a dark shell with a neon accent, or a white
card grid with a blue primary. Both read as templated and neither says anything
about this subject.

Ground it instead in the actual material world of Indian recurring payments: the
**bank mandate form and the passbook**. Pale safety-paper stock, boxed character
cells, violet rubber-stamp ink, dot-matrix statement printing. That vernacular is
specific, it is instantly legible to an Indian payments audience, and it carries
the right connotation — this is a system of record, not a growth dashboard.

### Tokens

```css
--paper:      #EEF2EA;  /* safety-paper green, the page */
--paper-2:    #F7F9F5;  /* raised surfaces */
--rule:       #C9D2C4;  /* hairlines, form-box borders */
--ink:        #1B2432;  /* primary text, near-black indigo */
--ink-muted:  #5C6875;
--stamp:      #5B3FA8;  /* violet stamp — the single accent */
--recovered:  #1F6B4A;  /* deep ledger green */
--at-risk:    #A6641C;  /* burnt amber, never red-alert red */
--blocked:    #6B7280;  /* grey — a block is normal, not an error */
```

Deliberately **no red**. A blocked action is correct behaviour; colouring it red
teaches the viewer to read your best feature as a failure. Blocks are grey and
neutral. Only genuine faults get amber.

### Type

- **Display:** a squarish technical grotesque with tight apertures — the register
  of a printed form heading, not an editorial serif. Set in small caps for
  section eyebrows with wide tracking, mimicking form field labels.
- **Body:** a neutral humanist sans at a comfortable 15px/1.55.
- **Data:** a tabular monospace for every rupee figure, date, ID and count.
  Non-negotiable: numbers must align vertically down a column. This is a ledger.

IDs render in a boxed-cell treatment — thin rules between character groups, like
the boxes on a NACH form: `mnd│01H│K4Q│2XP`.

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
