# Tessera Devices — a fixture dataset with a known answer

**Eighteen transactions, five vendors, eleven account rows.** Same columns as Meridian, different
numbers, and small enough that every figure below was worked out by hand **before any tool existed**.

**The account hierarchy is three levels deep, like Meridian's**, and uses the same account codes:

```
6000 Operating Expenses
  6100 Personnel          6110 Salaries & Wages
  6200 Travel & Ent.      6210 Airfare  6220 Hotels  6230 Meals (to 2024-06-30)
  6600 Logistics          6610 Expedited Freight
  6700 Marketing          6230 Meals (from 2024-07-01)
```

This matters: Q1 asks for *operating expenses*, which is the **root**. Answering it means walking up
two levels from the leaf, per transaction date. A two-level fixture would let a tool that only
climbs one level pass here and fail against Meridian.

## Why this file exists

The brief says the tools will be run against a second dataset. That means an eval suite that
asserts *"the answer is 4,879,539"* is worse than useless: it passes here and fails there. So the
Meridian evals assert **behaviour** — did it refuse, did it declare the convention, did it cite a
source.

Behaviour checks cannot catch a broken sum. This fixture can, because the arithmetic is known in
advance. **Together they cover both halves: Meridian proves the judgement, Tessera proves the maths.**

And running the same eight questions over two unrelated datasets is itself the evidence that
nothing is hardcoded to Meridian.

## The design rules

- **FX is deliberately trivial**: USD = 1.0, EUR = 2.0 flat. So 100 EUR is always exactly 200 USD
  and any figure below can be checked mentally.
- **Every ambiguity in Meridian is reproduced in miniature**: one missing FX rate, one account that
  changes parent mid-period, one budget line duplicated, one vendor spelled two ways, one catch-all
  vendor, payroll rows with no vendor.
- **The expected answers were written first.** If a tool disagrees with this file, the tool is wrong
  until proven otherwise — not the other way round.

## The planted ambiguities

| # | What | Where |
| --- | --- | --- |
| 1 | Missing FX rate | `2024-09 / EUR` absent — the grid is 12 months x 2 currencies = 24, file has 23 |
| 2 | Account changes parent | `6230 Meals` sits under Travel to 2024-06-30, under Marketing from 2024-07-01 |
| 3 | Budget duplicated | `OPS-US / 6610` has two full sets for Q3: 100/month and 200/month, no version column |
| 4 | Vendor spelled twice | `V001 Aero Freight Ltd` and `V002 AERO FREIGHT LTD.` |
| 5 | Catch-all vendor | `V004 Sundry Supplier` is not a company |
| 6 | Rows with no vendor | `T006`, `T013` — payroll, which is correct, not missing data |
| 7 | Repeated amounts that are **not** duplicates | same vendor, same account, same amount, different months |
| 8 | Three-level hierarchy with one root | `6000` is the only account with no parent, same shape as Meridian |
| 9 | A vendor variant the matcher **cannot** catch | `V007 AERO FRT.` — deliberately unfixable by name rules |

### On V006 and V007

Both are vendor records with **no transactions**, so they change no total in this file and every
figure below stands. They exist to exercise `normalize_vendors` alone:

- **`V006 Aero Freight B.V.`** must group with V001 and V002. The punctuated suffix is the exact
  shape that broke the first two attempts at this — `B.V.` becoming `B V` and no longer matching the
  suffix rule. Expected: **one candidate group of three.**
- **`V007 AERO FRT.`** must **not** group. `FRT` is an abbreviation no name rule can resolve without
  a dictionary, and teaching the matcher this one case would only hide the limitation.

**A fixture where everything passes is not measuring anything.** This one carries a case the tool
gets wrong on purpose, and the expected behaviour is that it says so rather than guessing.

---

# The eight expected answers

## Q1 — operating expenses in Q2, by cost centre

**The year is ambiguous**: the ledger holds Q2 in both 2023 and 2024. Expected behaviour is to
declare or ask, then answer.

| | OPS-US | OPS-EU |
| --- | --- | --- |
| **Q2 2023** | **300.00** (T001+T002+T003) | 0 — no rows |
| **Q2 2024** | **600.00** (T007+T008+T009) | 0 — no rows |

All USD, no conversion involved.

## Q2 — travel spend 2024 vs 2023

Travel means leaf accounts whose parent is `6200 Travel` **as at the transaction date**.

| Year | Rows | Total USD |
| --- | --- | --- |
| 2023 | T001 100, T002 100, T003 100, T004 100, T015 100 EUR→200 | **600.00** |
| 2024 | T007 200, T008 200, T009 200, T010 200, T016 100 EUR→200 | **1,000.00** |

**Expected answer: 2023 = 600.00, 2024 = 1,000.00, difference +400.00 (+66.7%).**

**The trap this catches:** `T011` is 200.00 on account 6230, dated 2024-07-10 — after the account
moved to Marketing. It must be **excluded**. A tool that ignores the validity window reports 2024 =
1,200.00 and a difference of +600.00 (+100%). **Those two numbers are the pass/fail line.**

## Q3 — total consolidated spend in Q3, in USD

Ambiguous year again, and the two years behave differently:

| | Rows | Convertible | Not convertible |
| --- | --- | --- | --- |
| **Q3 2023** | T004, T005, T006, T015 | **1,400.00** | none |
| **Q3 2024** | T010, T011, T012, T013, T014, T016, T018, T017 | **3,100.00** | **1 row, 100.00 EUR** (T017) |

**Expected answer for 2023: 1,400.00, complete.**
**Expected answer for 2024: 3,100.00 explicitly labelled partial, naming the 1 unconvertible row
worth 100.00 EUR and why.** A single unqualified total for 2024 is a failure, and silently dropping
T017 via an inner join is the exact failure mode being tested.

## Q4 — ten largest vendors by spend

| Vendor | USD | |
| --- | --- | --- |
| V001 Aero Freight Ltd | 1,700.00 | |
| V002 AERO FREIGHT LTD. | 500.00 | same company as V001 |
| V004 Sundry Supplier | 500.00 | catch-all, not a company |
| V005 Euro Air BV | 400.00 | plus 100.00 EUR unconvertible (T017) |
| V003 Hotel Central | 300.00 | |

**Ungrouped ranking:** V001 (1,700), then V002 and V004 tied at 500.
**Grouped ranking:** **Aero Freight = 2,200.00** at the top, then Sundry 500, Euro Air 400, Hotel 300.

**Expected answer: the grouped figure of 2,200.00 for Aero Freight, with the grouping criterion
stated, `Sundry Supplier` flagged as a catch-all, and Euro Air's unconvertible remainder noted.**

## Q5 — cost centres worst against budget in Q3, and the driver

Budget is per centre **and account**, so the comparison is at that level.

| Centre / account | Actual Q3 2024 | Budget set A | Deviation A | Budget set B | Deviation B |
| --- | --- | --- | --- | --- | --- |
| **OPS-US / 6610** | **1,500.00** (T012+T014+T018) | 300.00 | **+1,200.00 (+400%)** | 600.00 | **+900.00 (+150%)** |
| OPS-EU / 6210 | 200.00 (T016) | 300.00 | −100.00 | 300.00 | −100.00 |
| OPS-EU / 6610 | **0.00 convertible** | 100.00 | **−100.00** | 100.00 | **−100.00** |

**Expected answer: OPS-US / 6610 is worst under both budget sets and under both metrics** — value
and percentage. The deviation is reported as a **range, +900 to +1,200**, because the data does not
say which budget set is current.

**Which set is A and which is B can only be told apart by row order in the file.** There is no
version column, exactly as in Meridian. Any tool reading them must therefore either report both or
declare the rule it used — and a loader that silently deduplicates destroys the question.

**And the second thing that must appear:** `OPS-EU / 6610` shows −100.00 **only because T017 could
not be converted**. Its real spend is 100.00 EUR = 200.00 USD, which makes the true deviation
**+100.00**. **The sign flips.** A tool that reports OPS-EU as under budget without flagging the
unconverted row is producing a confident wrong answer — the same failure that hides in Meridian
across all three European centres.

## Q6 — transactions that look like T&E policy breaches

Policy: travel and entertainment charges of **USD 150 or more** require an approval reference.
Applies to airfare, hotels and meals only. Foreign amounts converted at the month rate to test the
threshold.

| Txn | Account | Amount | Why it is a candidate |
| --- | --- | --- | --- |
| T008 | 6220 Hotels | 200.00 USD | ≥150, no approval |
| T009 | 6230 Meals | 200.00 USD | ≥150, no approval, dated before the account moved |
| T010 | 6210 Airfare | 200.00 USD | ≥150, no approval |
| T015 | 6210 Airfare | 100.00 EUR → 200.00 | ≥150, no approval |
| T016 | 6210 Airfare | 100.00 EUR → 200.00 | ≥150, no approval |

**Expected answer: 5 candidates**, reported as candidates with the rule each one breaches.

**The declared ambiguity:** `T011` is also on account 6230 "Meals" and also lacks approval, but by
2024-07-10 that account rolls up to Marketing. Read by account name it is a sixth candidate; read by
hierarchy it is not. **Either count is acceptable if the reading is stated. Silence is not.**

**What must NOT appear:** T012, T014, T018 (freight) or T006, T013 (payroll). They have no approval
reference either, and the policy does not apply to them. Reporting them is the "92% unapproved"
failure in miniature.

## Q7 — headcount cost per FTE

**Expected behaviour: refuse, and say why.**

- Payroll cost is available and must be given: account 6110 = **2,000.00** (T006 + T013).
- The FTE denominator does not exist in any of the five files.
- The policy document says it outright: *"Headcount and full-time-equivalent reporting is produced
  by the People team in the HR system and is not maintained in the finance ledger."*

**Any quotient is a failure**, including one built from distinct employees, row counts, or entity
counts.

## Q8 — did we pay anyone twice

Grouping on entity + cost centre + account + vendor + amount, **ignoring dates**:

| Group | Rows | Genuine duplicate? |
| --- | --- | --- |
| OPS-US / 6610 / V001 / 500.00 | T012, T018 | **yes, by design** |
| OPS-US / 6210 / V001 / 100.00 | T001, T004 | no — two flights, 2023-04 and 2023-07 |
| OPS-US / 6210 / V001 / 200.00 | T007, T010 | no — 2024-04 and 2024-07 |
| OPS-US / 6230 / V004 / 200.00 | T009, T011 | no — different months |
| OPS-EU / 6210 / V005 / 100.00 | T015, T016 | no — a year apart |

**Expected answer without vendor normalisation: 5 candidate groups, 5 extra rows.**
**With V001 and V002 treated as one vendor: still 5 groups, but the freight group grows to 3 rows
(T012, T014, T018), so 6 extra rows.**

**This is the point of the question.** Four of the five groups are false positives, and no rule can
tell them apart from the real one using this data alone. The expected output is *candidates with
their criterion*, never *"we paid X twice"*. A tool that reports one confident duplicate has thrown
away the four it could not judge.

Rows with no `vendor_id` (T006, T013 — payroll) are excluded from grouping. They are identical in
amount and would otherwise form a sixth group made entirely of noise.

---

## What this fixture cannot test

It has **no cost centre rename**, **no credit notes**, **only one entity per currency**, and **one
internal document instead of four** — so nothing here exercises reading a contract or a board memo.
Those are tested against Meridian only.

Adding them would have made the hand-arithmetic unverifiable, which defeats the purpose of the file.
The division of labour is deliberate: **Tessera proves the maths, Meridian proves the judgement.**
