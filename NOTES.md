# Notes

*Written as the work happened, not reconstructed afterwards.*

> **You asked for one page and this is longer.** Rather than delete the evidence, the working-out
> behind five of these answers moved to [`JOURNAL.md`](JOURNAL.md), whole and unedited. What is
> here is the answer; what is there is the proof, if you want it.

## How I used AI, and what I kept for myself

I used Claude Code throughout — for the tools, the SQL, and most of the prose in this repository.
What I did not delegate was the analysis. **Before any code existed I wrote out the expected
behaviour for all eight questions by hand**, including the ones that should refuse, and every tool
in `ARCHITECTURE.md` fell out of that document rather than being designed up front. That order
mattered more than any prompt: deciding what the answer should be, before knowing what the code
would return, is the only reason several wrong answers were caught at all.

Three decisions set the shape before anything was built: **attack it backwards** — write the eight
expected answers first and derive the tools from them, which is why there is no `run_anything` tool;
**do not open the data until the problem is understood**, because you end this brief with *"we'll ask
you to walk through what you built"*; and **build a second dataset whose answers I already know**.

Then, repeatedly, I overruled the model's design and the measurement said I was right to. Seven of
those changed the code; the three that mattered most:

- *Let the model translate the question into accounts, not a string rule.* **"headcount" matches zero
  accounts** in this chart — they are called Personnel and Salaries & Wages — and picking the wrong
  rollup is not an error, it is a plausible figure: root 6830 answers **91,015.92** where the answer
  is **12,780,721.78**.
- *Showing the work sounds like two tables, not one.* Nordwind is the largest vendor grouped and
  **does not reach the top ten split**, at number 15. The ranking is a decision, so both are printed.
- *You are being too strict.* The figure guard was **deleting correct answers** over a truncated
  number, a correct sign and the numerals in a bulleted list. It annotates now.

The pattern is the same every time: the model's instinct was defensible and the measurement decided
it. That is the working relationship, not a prompt. The other four are in the journal.

## Which model, and why it barely matters

**Gemini 3.6 Flash on Google AI Studio's free tier**, which you name as fine, then `gpt-5-mini` when
the free tier stopped: **20 requests per day**, and one sweep of the eight questions is fifteen —
two calls each except the refusal, which costs one.
Worth knowing before planning an eval run around it.

**"OpenAI-compatible" is not one protocol.** I wrote here that a provider swap was two environment
variables, then swapped and got two HTTP 400s: `max_tokens` rejected in favour of
`max_completion_tokens`, and `temperature` rejected for not supporting 0.0. The first is a rename.
The second removes a design decision — temperature 0 is why the same question routes the same way
twice — and that model does not offer it. `ask()` adapts to both and **records the adjustment on the
answer**, because a run that could not be deterministic must not look like one that was.

A stronger model cannot improve a single figure here, because the arithmetic never touches it. The
honest comparison is **which caveats each one dropped**, not which totals differ.

## Something that worked well

**The fixture in `evals/fixtures/`.** Eighteen rows, a flat 2.0 EUR rate, every figure worked out on
paper before a tool existed, and every ambiguity in your data reproduced in miniature. It paid for
itself twice.

**On day one it found six arithmetic errors of mine** — rows I had missed while adding up by hand.
The data was not touched; my sums were corrected.

**On day two it caught a lie in code ten minutes old.** The policy-breach question returned six
candidates where the fixture says five. The extra one was a meal dated nine days after that account
moved from Travel to Marketing: the plan had collected the leaf accounts from every validity window
and then queried the whole period with the union — while the sentence that same plan prints claimed
scope was resolved window by window. The condition is now built per window.

It also carries one case the tools get **wrong on purpose**: a vendor abbreviated `AERO FRT.` that
no name rule resolves. A fixture where everything passes is not measuring anything.

## Where the AI got it wrong, and how I noticed

**Four reviews, and my own verification found nothing in any of them.** That is the finding, and it
repeats: every defect below was caught by someone who had not written the code.

- **20 defects, and not one fires against your data.** They fire against data shaped differently,
  which is what you say you will do. Worst of them, several tools stated **Meridian's own
  measurements as fact** inside notes that travel into the answer — all true here, all fabricated
  anywhere else. `evals/no_borrowed_facts.py` exists because of that one.
- **6 more that afternoon.** Four have a guard in `evals/guards.py`; two do not — and I had written
  *"each case is reproduced here"* in that docstring while shipping four. I found it by counting,
  which is the whole point of this section.
- **The answers graded by someone other than me: two of five failed.** Not on a figure — content the
  code had already computed sat in the findings as a raw key and never reached a sentence. The
  vendor ranking lived only inside the model's paragraph, and 46% of spend having no vendor at all
  was a number nobody said out loud. Both are printed by code now.
- **The fourth review found three wrong figures in your data**, and none of them raises an error —
  all three print cleanly. A cost centre renamed mid-2024 that nothing mapped, so the worst
  overspender was dropped from Q1 and Q2 entirely while the code inheriting its budget published
  **−100%, "spent nothing"**, having spent 716,962.62. The by-centre answer ordered wrong at every
  rate on file, because unconverted rows went into an aggregate and were never attributed to a
  centre — in the one question that asks *by cost centre*. And a year compared against itself
  counted twice.

That last review was four agents reading at once, **none of them shown the others' findings**. Blind
and parallel buys one thing sequential does not: when two report the same defect independently, the
agreement means something. The method, and the design of mine that a fresh agent killed before it
was written, are in [`JOURNAL.md`](JOURNAL.md).

One technical trap, kept because a design decision rests on it: the first live model call returned
HTTP 200 and an empty string. Reasoning tokens count against `max_tokens` and appear in neither
`prompt_tokens` nor `completion_tokens` — my ceiling saw 9 where the provider counted 106. The
ceiling counts `total_tokens` because of it.

## The thing I had to correct repeatedly, and what stopped it

**Stating a measurement it had not taken.** Six of them were written into this repository as fact,
and every one is about the data or about the system — not about prose. Two examples:

```
"the fourth largest"        Nordwind is the LARGEST. That docstring had recorded the figure
                            produced by the bug it describes, and outlived the fix
"five of the six rules"     a fixed string enumerating Meridian's policy, emitted as a decision
                            against ANY dataset - already false against the fixture, whose
                            policy has four sections and none of those rules
```

Every one reads well and none was checked. Prompting did not fix it, because it is not disobedience
— a sentence that sounds measured costs nothing to write. **What fixed it was making the rule
structural.**

- `evals/no_borrowed_facts.py` runs every tool against the fixture and **fails if a note mentions
  any of eighteen names, codes and figures that exist only in Meridian**. A blacklist, not a
  detector: it catches the borrowed facts I knew about, not the ones I did not.
- `evals/guards.py` reproduces **four of those six defects** against a mutated copy of the fixture,
  plus a fifth from a later round. **Each was verified in the failing direction**: the bug was put
  back and the guard caught it. A check that only ever passes proves nothing — and two of the six
  still have no guard, which the file's own docstring says out loud.
- **The figures and the caveats are printed by code**, from the tool that measured them. The model
  writes one paragraph and cannot forget what it was never asked to carry.
- And the narrow rule I now work by: **do not write an hour, a date or a figure you did not just
  read.**

This is the same rule I already use in a WhatsApp sales bot I built and still run in production,
after one photo of a payment receipt marked three orders as paid: **if the model disobeys and it
does damage, it goes in code; if it only looks bad, it goes in the prompt.** Applied to the writer,
it deleted most of the prompt — seven rules became one, because two were patching a **data**
problem. The other four cases are in the journal.

## What I cut

- **No web interface.** The brief allows either; a UI would eat hours you are not evaluating.
- **No retrieval over the documents.** Four files, under 6 KB, read whole. Chunking would add an
  embedding model, a store and a threshold so the paragraph that answers the question ranks fourth
  and never arrives — not hypothetical: a line-based search for the sentence deciding the FTE
  question returned nothing, because it spans a line break.
- **No database beyond the local file**, which is also your rule. No performance argument either:
  `query_ledger` grouping all 10,916 rows returns in 13 ms. **No dependencies at all** — clone it,
  run it with 3.12.
- **The nightly-rate policy rule, after measuring it.** It is checkable from the free-text memo, 100%
  of Meridian's hotel memos parse, and it finds 7 breaches — but a memo format is a property of one
  file, and the approval rule answers the question from columns that exist.
- **Translating the local variables.** Everything you read is in English — documents, comments,
  docstrings, commit messages — and so is every identifier that crosses from one module to another;
  those six were renamed once it was clear a reviewer meets them in a traceback. Inside the
  functions, the working variables are still in Spanish, because that is the language I thought the
  problem in. **It stopped there because nothing in `evals/` checks that a figure is correct**, so a
  sweep across twelve files buys consistency and risks moving a number with nothing to catch it. The
  full reasoning is in the journal.

## Roughly how long

**About 14 hours**, against the 10–12 the brief suggests. Timestamps of the working session, every
gap over twenty minutes discarded.

| | window | active |
| --- | --- | --- |
| Fri 14 Aug, evening | 16:42–21:34 | **2.3 h** |
| Sat 15 Aug | 09:27–20:27 | **7.4 h** |
| Sun 16 Aug | 13:24–23:21, in two sittings | **~4.5 h** |

Plus **~1.4 h** on a fourth day, 10:04–12:06, which built nothing: it went on cutting these two
documents to the length you asked for and checking their figures again.

**Neither of the last two days built anything.** They went on the review and the fixes it produced:
three wrong figures in your data, claims in these documents that were not true — including four of
my own found after I thought this was finished — and a design of mine that a fresh agent killed
before it was written. I am over your range and I would rather say so than round down the one
number in this repository nobody can check.

This is the softest figure here and it is worth saying why. The repository's own commit timestamps
give a **floor** of 4.2 h for Saturday and 3.6 h for Sunday under the same twenty-minute rule — but
a commit records when work was saved, not how long it took, and Friday produced 2.3 hours and
**zero commits** because it was spent writing the eight expected answers before any code existed.

Roughly two of the first day's hours went on analysis before a line of code existed — writing the
eight expected answers, opening the CSVs, finding the traps. It felt like not working and it is the
only part that could not have been recovered later.

## What I would do with two more days

1. **A check that fails when a figure moves.** This is the gap under most of the others. `eight.py`
   judges coherence and `guards.py` reproduces fixed defects, but nothing asserts an amount, and
   `EXPECTED.md` — the file holding Tessera's hand-computed answers — is read by no code at all.
   Measured, not assumed: a reviewer inflated every cost-centre total by 1% and all three suites
   stayed green; another moved a quarter-end date by one day, took 31,267 USD off the consolidated
   total, and they stayed green again.
2. **Judging the paragraph, not just the trace.** `evals/eight.py` judges statuses by coherence with
   their own published evidence and backs every `must_declare` entry with a named emitter. What
   nobody checks by command is the written paragraph itself: whether the prose carries what the
   trace proved.
3. **Real cost accounting.** The ceiling reports $0.00 because nothing supplies prices. On a free
   tier that is true and still wrong: a reported zero reads as measured.
4. **Read documents in any format.** Only `.md` is seen today, so a `.txt` policy would make the
   assistant refuse for lack of a document sitting in the folder.
5. **A third dataset I did not build.** Both of mine are ones I understand. The interesting failures
   are in the one I do not.
