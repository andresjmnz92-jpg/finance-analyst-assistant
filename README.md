# Finance Analyst Assistant

An assistant for Meridian Instruments' FP&A team: ask a question in plain English, and it queries
the ledger, reads the policy, checks the budget and shows exactly what it did.

**Status: in progress.** What exists today is listed below, honestly. Nothing here is a promise.

## What works right now

| | |
| --- | --- |
| ✅ Data loading | Five CSVs into SQLite, no cleaning, no dependencies |
| ✅ A second dataset with known answers | `evals/fixtures/` — 18 rows whose every figure was worked out by hand first |
| ✅ [`ARCHITECTURE.md`](ARCHITECTURE.md) | The tool design and where the model is and is not in the loop |
| ✅ The seven tools | Built and checked against both datasets; see [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| ✅ [`NOTES.md`](NOTES.md) | What went wrong, how it was noticed, what was cut |
| ✅ One check that runs | `python -m evals.no_borrowed_facts` |
| ⬜ Router, CLI and trace | The orchestration layer is written but not yet wired |
| ⬜ The eval runner over all eight questions | |

## Install and run

Python 3.12, standard library only. Nothing to install for the data layer.

```bash
git clone https://github.com/andresjmnz92-jpg/finance-analyst-assistant
cd finance-analyst-assistant

python -m src.load                 # data/          -> data.db
python -m src.load evals/fixtures  # evals/fixtures -> fixtures.db
```

The database name is derived from the folder, so the two datasets cannot overwrite each other. Both
`.db` files are gitignored and rebuilt from the CSVs every run.

### Credentials

None are needed yet, and none are committed. When the model layer lands it will read an API key from
the environment, and whoever runs this supplies their own. There is no `.env` in this repository and
`.gitignore` has excluded one since the first commit.

## Why there are two datasets

The brief says the tools will be run against a second dataset with the same columns and different
numbers. That rules out an eval suite that asserts absolute figures — it would pass here and fail
there.

So the eight questions are checked two ways:

- **Meridian proves the judgement.** Did it refuse when it should, declare the convention it chose,
  cite a source, avoid the confident wrong answer. Those checks survive any dataset.
- **Tessera proves the arithmetic.** Eighteen hand-built rows, a flat 2.0 EUR rate, and every
  expected figure written down **before any tool existed** in
  [`evals/fixtures/EXPECTED.md`](evals/fixtures/EXPECTED.md).

Tessera reproduces every ambiguity in Meridian in miniature: one missing FX rate, one account that
changes parent mid-year, one budget line duplicated with no version column, one vendor spelled two
ways, a catch-all vendor, payroll rows with no vendor, a three-level account hierarchy, and four
repeated amounts that are **not** duplicates.

## What the loader tells you

It prints the characteristics of whatever dataset it just read — not errors, facts:

```
data.db  (2,452 KB)   from .../data
  gl_transactions       10,916 rows
  ...
data characteristics (not errors):
  accounts with more than one validity window : 1
  budget keys appearing twice                 : 228
  FX grid 24 months x 3 currencies = 72, actual rows 71 -> 1 missing
```

It also warns about columns it does not recognise, rather than dropping them silently. That matters
here: a `budget_version` column in a future dataset would resolve the duplicate-budget ambiguity on
its own, and nobody should find that out by accident.

## Known limitations

- Amounts are stored as SQLite `REAL`. For these magnitudes the rounding error is sub-cent; integer
  minor units would be stricter and would complicate every query. Declared, not overlooked.
- The fixture has one internal document instead of four, no cost centre rename and no credit notes.
  Those are exercised against Meridian only.
- Meridian's own files are committed under `data/`, following the layout suggested in the brief.

## Layout

```
src/            loader today, tools and agent next
evals/fixtures/ the second dataset and its expected answers
data/           Meridian's five CSVs and four documents
traces/         sample runs, once there are runs
```
