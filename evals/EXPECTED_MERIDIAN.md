# Meridian — the expected behaviour for the eight

**This file holds no expected figures, and that is the point.** Its companion,
[`fixtures/EXPECTED.md`](fixtures/EXPECTED.md), holds every figure for the Tessera fixture,
worked out by hand before any tool existed. The division is deliberate and it is the one the brief
forces:

> *"We'll also run your tools against a second dataset with the same columns and different numbers,
> so don't hardcode anything to this one."*

An eval asserting *"the answer is 10,003,879.96"* passes here and fails there, and failing on your
data with a green suite of mine reads worse than having no suite. So **Tessera proves the maths and
Meridian proves the judgement**: did it refuse when it should, did it declare the convention it
chose, did it name what it could not convert, did it avoid the confident wrong answer.

The numbers that do appear below describe **the shape of the trap**, never the answer to the
question. They are properties of this file that a reviewer can check.

**Where this is enforced:** each *must state* line below is an entry in `must_declare` in
[`../src/agent/plans.py`](../src/agent/plans.py), and [`eight.py`](eight.py) fails if the trace
does not carry its evidence, found through a named emitter. Twenty-six entries, all backed. What
no command judges is the written paragraph — that is still graded by reading it.

---

## 1. Operating expenses in Q2, by cost centre

**Must state** — which year (the ledger holds Q2 in both 2023 and 2024, and neither is *the*
answer); which date field defines the period; which account the phrase "operating expenses"
resolved to.

**Must do** — sum **leaf accounts only**. The chart mixes 24 leaves with 9 aggregation nodes;
summing everything counts the same spend up to three times.

**Must not** — pick a year in silence. Use `statement_line` as a classifier: all 34 of its records
read `Operating Expenses`. **Treat `OPS-NA` and `OPS-AMER` as one centre without saying so, or as
two unrelated ones.** The board memo records the rename effective 2024-07-01.

**The trap that hides here:** rows with no FX rate belong to a cost centre too. Totalling only the
convertible ones and sorting the result publishes an order that is not a ranking. The plan bounds
each affected centre and says so.

---

## 2. Travel spend, 2024 against 2023

**Must state** — whether it compares in local or consolidated currency, and with which rate;
both totals and the difference, in value and in percent.

**Must do** — resolve "travel" through the account hierarchy, **respecting the validity window**.
Account `6230` is Travel & Entertainment to 2024-06-30 and Marketing from 2024-07-01: same code,
different meaning. Joining the chart without that filter duplicates every `6230` transaction.

**Must not** — put the second half of 2024's marketing spend inside "travel". Subtract a complete
year from an incomplete one and publish the difference to the cent: one side is missing rows with
no rate, and in a subtraction that gap is amplified. Answer at all when the two years given are the
same year, or when a year has no rows — a year with no data reading as a 100% fall is the failure
this refuses.

**Note for `ARCHITECTURE.md`:** this question is the written example of *"if a path can be written
down in advance, write it down"*. An agent here is surplus, and saying so is worth more than
building one.

---

## 3. Total consolidated spend in Q3, in USD — no honest single answer, **for 2024**

**The fact that breaks it:** exactly one of the 72 combinations in `fx_rates.csv` is absent, and it
is **`2024-09 / EUR`**. Q3 is July, August, September. **147 rows in euros accrue in 2024-09**, and
there is no way to convert them without inventing a rate.

**And the question does not say which year**, which is the trap inside the trap:

| | rows | with no rate | |
| --- | --- | --- | --- |
| **Q3 2023** | 1,369 | **0** | answerable in full |
| **Q3 2024** | 1,348 | **147** | no honest single total |

So the expected behaviour has two beats: **declare or ask the year first**, then apply the rest. A
system that refuses without having settled the year is failing for the wrong reason.

**Must state** — the missing rate, with the count and amount left out; the conversion convention.
The rate table is monthly and **does not say whether it is spot, average or closing**. The only
sentence about rates anywhere in the pack lives in the wrong document — the travel policy's
*"the local equivalent at the month-end rate applies"* is a rule for testing travel caps, not a
consolidation policy.

**Must not** — inner-join against the rates. It **deletes the 147 rows in silence** and returns a
total that looks correct. This is the textbook plausible wrong answer. Fill the gap with August's
rate, or the quarter average, without saying so. Publish an unqualified total.

---

## 4. The ten largest vendors by spend

**Must do** — consolidate the variants of one vendor. `Nordwind` appears **4 times** and
`Delft Precision` twice: **43 records for 39 real vendors**, and `vendors.csv` has four columns and
none of them is a tax id. **The grouping is a declared criterion, not a fact of the data.**

The evidence that supports it: the four Nordwind records **coexist** across 2023 and 2024 — not a
change of legal name, where one would end where the next begins — and bill against the same three
accounts, the same category and the same country. Four separate registrations of one supplier.

**How much it changes the answer:** split in four, Nordwind does not reach the top ten at all;
consolidated it ranks near the top. **Without this step the answer is wrong and sounds perfect.**

**Must state** — the grouping criterion; the four catch-all "vendors" that are not companies
(`Sundry Supplier`, `Various Card Settlement`, `Meridian Lodging Program`, `Aeroline Travel Desk`),
and whether they are in or out; that **864 rows carry no `vendor_id`**, which is not missing data —
they are exclusively the payroll accounts 6110 and 6120.

**Must not** — group on raw `vendor_name`. Sum across currencies. Present a catch-all as a supplier.

**The tool proposes groups; it never merges silently.** Writing this file, a text normaliser
(stripping `BV`, `GmbH`, `LOG`, dots) grouped **3 of 4**: `NORDWIND LOG.` lost its `LOG`, became
`NORDWIND`, and stopped matching. **It raised no error.** It was caught because the group summed to
3.09M where the four variants sum to 4.09M. A silent grouper that fails produces exactly the
plausible wrong answer the brief penalises.

---

## 5. Cost centres worst against budget in Q3, and the driver

**The only one of the eight that needs two genuinely chained steps:** find the worst-deviating
centre, and **only then** go and find what caused it. The second query consumes the first result.

**Must state** — that the budget carries **duplicated keys with no version column**, so the
deviation is a range and not a point; which rows could not be converted, **by centre**, and
**whether that flips a sign**; any centre with spend and no budget line, or a budget line and no
spend, with its amount.

**The sign flip is the whole question.** The three European centres appear **under** budget only
because September is missing entirely. With the absent month included they go over. A report that
does not flag it states that Europe underspent when it probably overspent — 43 centre/account pairs
change sign this way.

**Must not** — drop a centre from the answer for having no budget line. Report a budget line with
no rows as **spend of zero, −100%**. Both were real defects here: the centre with the largest
overspend of the quarter was deleted from the answer while its renamed successor was published at
−100%, having spent hundreds of thousands.

**Not a coincidence:** the one centre with a duplicated budget is the same one the board memo
singles out for freight variance. The trap is set where it hurts.

---

## 6. Transactions that look like T&E policy breaches

The brief's *"look like"* is the instruction: these are candidates, not findings.

**Must do** — read the policy and **separate the checkable rules from the ones these columns cannot
test**. Apply the thresholds **to travel accounts only**.

**Must state** — each candidate with its `txn_id` and the rule it appears to breach; which parts of
the policy are not checkable here.

**Must not** — report *"92% of spend is unapproved"*. `approval_ref` is empty in 92% of rows and
that percentage **is not the finding**: approvals exist in only 3 of the 24 accounts, and they are
the three travel ones. Applying a travel rule to payroll, rent and freight manufactures thousands
of false positives. Say *"breached"* where the data supports *"appears to breach"*.

---

## 7. Headcount cost per FTE — **the clean refusal**

**If the system returns a quotient, it failed.**

The fact is theirs, in the board memo:

> *"Headcount reporting is produced by the People team in the HR system and is **not maintained in
> the finance ledger**."*

Confirmed by sweep: 2,100 budget rows against `headcount|FTE|employee|staff` returns nothing.

**Must do** — give the numerator, which does exist: payroll cost from accounts 6110 and 6120.
**Refuse the quotient** and explain that the denominator requires an FTE count. **Cite the memo.**
The right answer is not *"I could not find it"*, it is *"your own documentation says that figure
does not live here"*.

**Must not** — return any quotient. Substitute distinct employees, payroll row counts or entity
counts for FTE.

**Why it is a trap:** FTE is a **unit of measure, not a category of person** — two half-timers are
one FTE. With ten full-timers at $5,000 and four half-timers at $2,500, dividing by FTE gives
$5,000, by headcount $4,285, by full-timers only $6,000. All three are defensible and only one
answers the question. A model picks one and sounds certain.

---

## 8. Did we pay anyone twice

**Must do** — group by **business attributes**: same entity, centre, account, vendor and amount,
**with the vendor normalised**, or the duplicated Nordwind payments escape.

**And drop the date entirely.** Measured on this file:

| Grouping | Candidates | Contains all seven real ones? |
| --- | --- | --- |
| entity + centre + account + vendor + amount, **no date** | **9** | **yes** |
| …and the same month | 4 | no, loses 3 |
| …and the same day | 4 | no, loses 3 |

Three of the seven sit **exactly 30 days apart**, replicating a monthly billing cycle. **A monthly
subscription looks identical to a duplicate payment**, so widening the window does not rescue them —
it confuses them with next month's invoice.

**Must state** — candidates with their criterion, never *"we paid X twice"*; that recurring spend is
an unresolvable false positive class, or how it is distinguished; the **31 credit notes** (`doc_ref`
prefixed `CM-`), which are exact reversals of real invoices and which a naive detector flags.

**Must not** — **detect on `doc_ref`.** The seven planted duplicates carry sequence numbers ≥ 600000
where the 10,909 legitimate rows run below that. It is a perfect signature **and an artefact of this
file**. Leaning on it is cheating, and it fails against your second dataset without raising anything.

---

## What this file cannot judge

The written paragraph. `eight.py` checks that the trace carries the evidence for every entry above;
whether the prose then says it is graded by reading. That gap is named in `README.md` and in
`NOTES.md` rather than papered over, and it is the first thing two more days would go on.
