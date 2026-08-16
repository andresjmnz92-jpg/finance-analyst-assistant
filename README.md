# Finance Analyst Assistant

Ask a question in plain English. It queries the ledger, reads the policy, checks the budget, does
the arithmetic, and shows exactly what it did.

```
python -m src.ui.ask "Which cost centers came in worst against budget in Q3?"
```

## Install and run

Python 3.12, **standard library only**. Nothing to install.

```bash
git clone https://github.com/andresjmnz92-jpg/finance-analyst-assistant
cd finance-analyst-assistant

python -m src.load                 # data/          -> data.db
python -m src.load evals/fixtures  # evals/fixtures -> fixtures.db
```

The database name comes from the folder, and the folder's path is stored inside the database, so
two datasets cannot overwrite each other. Both `.db` files are gitignored and rebuilt from the CSVs.

### Credentials — yours, not mine

Create a `.env` in the repository root:

```bash
MODEL_API_KEY=your-key
MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/   # optional
MODEL_NAME=gemini-3.6-flash                                              # optional
```

Nothing is committed: `.gitignore` has excluded `.env` since the first commit and no key has ever
been in this history. Any provider that speaks the OpenAI-compatible protocol works — Gemini, Groq,
OpenAI, OpenRouter, a local Ollama — with the caveats in [`NOTES.md`](NOTES.md), because
"OpenAI-compatible" turned out not to be one protocol.

**`--model` and `--base-url` override the environment**, so switching provider needs no file edited.

## Using it

```bash
# a question: the model routes, the code runs, the model writes one paragraph
python -m src.ui.ask "Who are our ten largest vendors by spend?"

# a plan by name: NO model at all, and every figure is still produced
python -m src.ui.ask --plan cost_per_fte --param root=6100

# the small dataset, and save the trace
python -m src.ui.ask "Did we pay anyone twice?" --db fixtures.db --save
```

The eight plans: `opex_by_cost_centre`, `spend_comparison`, `consolidated_spend`,
`largest_vendors`, `budget_variance`, `policy_breaches`, `cost_per_fte`, `duplicate_payments`.

## What a run looks like

It prints the work before the conclusion — every tool call with its arguments, the SQL behind each
figure, every caveat beside the step that raised it, what the model cost, and then the answer.

```
  step 2   convert_currency
           -> total: 10,003,879.96
             ->! NOT CONVERTED - no rate on file for 1 month/currency combination(s),
                 covering 147 rows: 147 ledger rows worth 1,231,309.12 EUR in 2024-09.

  ->! Every year with Q3 data was totalled, not just the one reported: Q3 2023 =
      10,580,182.40 COMPLETE. Only Q3 2023 can be totalled completely from this file.

  model:   2 call(s), 9,251 tokens
  status:  PARTIAL
```

Sample runs are committed under [`traces/`](traces/).

## How to run the evals

```bash
python -m evals.eight               # the eight plans, both datasets, no model anywhere
python -m evals.no_borrowed_facts   # no tool quotes a fact from a dataset it was not given
python -m evals.guards              # every fixed defect still fires, against mutated data
```

`evals.eight` stores no expected answer — the rule that bans hardcoded figures turned out to bind
statuses too, since six of the eight plans compute theirs from whether an FX rate was missing.
Instead it judges coherence: a status must agree with the evidence the same run published, a
refusal must name its reason, and every `must_declare` entry in `plans.py` must have its evidence
in the trace, found through a named emitter. What it deliberately cannot judge is the written
paragraph — that is still graded by reading it.

`CASOS` pins the root account codes of these two datasets, because the runner runs with no model
anywhere and the account a phrase like "operating expenses" resolves to is the model's decision in
the full pipeline. Against a chart numbered differently the plans refuse cleanly and the runner
reports those refusals without failing them — the exemption is keyed to the reasons the code emits
before its tools run, never to REFUSED in general, so `cost_per_fte` refusing on the schema still
has to name both of its sources.

## Why there are two datasets

The brief says the tools will be run against a second dataset with the same columns and different
numbers. That rules out an eval suite asserting absolute figures: it would pass here and fail there.

- **Meridian proves the judgement.** Did it refuse when it should, declare the convention it chose,
  name what it could not convert, avoid the confident wrong answer.
- **Tessera proves the arithmetic.** Eighteen hand-built rows, a flat 2.0 EUR rate, and every
  expected figure written down **before any tool existed**, in
  [`evals/fixtures/EXPECTED.md`](evals/fixtures/EXPECTED.md).

Tessera reproduces every ambiguity in Meridian in miniature: a missing FX rate, an account that
changes parent mid-year, a budget line duplicated with no version column, a vendor spelled several
ways, a catch-all vendor, payroll rows with no vendor, a three-level hierarchy, and repeated
amounts that are **not** duplicates. It also carries one case the tools get **wrong on purpose** —
a vendor abbreviated `AERO FRT.` that no name rule resolves. A fixture where everything passes is
not measuring anything.

## What the loader tells you

Facts about whatever dataset it just read, not errors:

```
data.db  (2,452 KB)   from .../data
  gl_transactions       10,916 rows
data characteristics (not errors):
  accounts with more than one validity window : 1
  budget keys appearing twice                 : 228
  FX grid 24 months x 3 currencies = 72, actual rows 71 -> 1 missing
```

It also warns about columns it does not recognise rather than dropping them silently — a
`budget_version` column in a future dataset would resolve the duplicate-budget ambiguity on its
own, and nobody should discover that by accident.

## Status

| | |
| --- | --- |
| ✅ The eight plans | Every figure checked against `EXPECTED.md`, on both datasets |
| ✅ The router | 8 of 8 questions to the right plan, with the right account code each time |
| ✅ The writer, the trace and the CLI | One model call to route, one to write; figures and caveats printed by code |
| ✅ Three eval commands | `eight`, `no_borrowed_facts` and `guards` |
| ✅ A runner over the eight questions | `python -m evals.eight`: 16 runs, statuses judged by coherence with their own evidence, all 26 `must_declare` entries backed by a named emitter |
| ⬜ The expected behaviour for Meridian's eight | Written, but not yet in this repository nor in English |
| ⬜ Traces for all eight | Two committed so far |

## Known limitations

- Amounts are SQLite `REAL`. At these magnitudes the rounding error is sub-cent; integer minor
  units would be stricter and would complicate every query. Declared, not overlooked.
- The nightly-rate rule in the T&E policy is **not** checked. It is checkable from the free-text
  memo — 100% of Meridian's hotel memos carry nights and a city, and doing it finds 7 breaches —
  but a memo format is a property of one file, while the approval rule answers the question from
  columns that exist. Measured, then cut on purpose.
- `duplicate_payments` prints vendor codes where it should print names.
- The fixture has one internal document instead of four, no cost centre rename and no credit notes.
  Those are exercised against Meridian only.
- Meridian's files are committed under `data/`, following the layout the brief suggests.

## Layout

```
src/tools/      the eight tools
src/agent/      plans, executor, router, writer, trace, model call
src/ui/         the CLI
evals/          the checks that run, and the fixture with its expected answers
traces/         sample runs, committed
data/           Meridian's five CSVs and four documents
```
