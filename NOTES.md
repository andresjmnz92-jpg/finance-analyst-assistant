# Notes

*Written as the work happened, not reconstructed afterwards.*

## How I used AI, and what I kept for myself

I used Claude Code throughout — for the tools, the SQL, and most of the prose in this repository.
What I did not delegate was the analysis. **Before any code existed I wrote out the expected
behaviour for all eight questions by hand**, including the ones that should refuse, and every tool
in `ARCHITECTURE.md` fell out of that document rather than being designed up front.

That order mattered more than any prompt. Deciding what the answer should be, before knowing what
the code would return, is the only reason several wrong answers were caught at all.

Four decisions here are mine and were argued for against a different suggestion:

- **Attack the exercise backwards.** Write the eight expected answers first, derive the tools from
  them. It is why there is no `run_anything` tool — there was nowhere for one to come from.
- **Do not look at the data until the problem is understood.** You end this brief with *"we'll ask
  you to walk through what you built"*. A repository I cannot explain loses the conversation that
  decides.
- **Build a second dataset whose answers I already know.** More on that below.
- **Show both vendor rankings rather than one.** You ask for an interface that "must show the work,
  not just the conclusion", and in that question the decision *is* the answer.

## Something that worked well

**The fixture in `evals/fixtures/`.** Eighteen rows, a flat 2.0 EUR rate, every figure worked out on
paper before a tool existed, and every ambiguity in your data reproduced in miniature.

It paid for itself twice.

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

**An adversarial review of the whole repository found 20 defects, and not one of them fires against
your data.** They fire against data shaped differently — which is exactly what you say you will do.

- Two payments of the same magnitude in different currencies reported as one payment made twice,
  because the match key omitted currency and every Meridian entity is single-currency.
- Two companies sharing a cost centre code reported as conflicting budget versions, because the
  partition omitted entity.
- A conversion to any currency other than USD returning a USD figure with the wrong label.

Worst of all: several tools stated **Meridian's own measurements as fact** inside the notes that
travel into the final answer. All true here. All fabricated against any other dataset. The code
refused to guess about data it could not see, and then quoted figures from a file that was not
loaded.

Three smaller ones, each invisible until something specific was measured:

| What was wrong | How it surfaced |
| --- | --- |
| `convert_currency` reported *"1 row worth 1,231,309 EUR could not be converted"*. The amount was right; the count was 147 | Calling the same tool two ways and comparing |
| A vendor rule grouped three of Nordwind's four spellings; fixed; a second rule grouped three of four again, because `B.V.` became `B V` | A group total not matching the sum of its parts, then counting members |
| The first live model call returned HTTP 200 and an empty string | `finish_reason: length`. Reasoning tokens count against `max_tokens` and appear in neither `prompt_tokens` nor `completion_tokens` — my ceiling saw 9 where the provider counted 106 |

**And at the end, the answers themselves were graded by someone other than me. Two of five failed** —
not on a figure, but because content the code had already computed sat in the findings as a raw key
and never reached a sentence. The vendor ranking existed only inside the model's paragraph, and 46%
of spend having no vendor at all was a number nobody said out loud. Both are now printed by code.

## The thing I had to correct repeatedly, and what stopped it

**Asserting things I had not measured.** Not once — I can count them, because they are all in this
history:

```
"about ten hours"          the measured figure was 5.9
two weekday names          Thursday and Friday; they were Friday and Saturday
"the fourth largest"       Nordwind is the largest. That docstring had recorded the figure
                           produced by the bug it describes, and outlived the fix
"216 of 228 pairs differ"  228 of 228 differ - and the same docstring said so correctly two
                           sentences earlier
"the eval runner asserts"  there is no eval runner
```

Every one reads well and was never checked. Prompting did not fix it, because it is not
disobedience — it is the shape of writing.

**What fixed it was making the rule structural.**

- `evals/no_borrowed_facts.py` runs every tool against the fixture and **fails if a note mentions
  anything only Meridian has**. A tool may describe what it measured; it may not remember.
- `evals/guards.py` reproduces each fixed defect against a mutated copy of the fixture — a zero
  budget, an unrated currency, a year with no data. **Each was verified in the failing direction**:
  the bug was put back and the guard caught it. A check that only ever passes proves nothing.
- **The figures and the caveats are printed by code**, from the tool that measured them. The model
  writes one paragraph and cannot forget what it was never asked to carry.
- And the narrow rule I now work by: **do not write an hour, a date or a figure you did not just
  read.**

This is the same rule I already use in a production WhatsApp sales bot, after one photo of a payment
receipt marked three orders as paid: **if the model disobeys and it does damage, it goes in code; if
it only looks bad, it goes in the prompt.**

Applied to the writer, it deleted most of the prompt. Seven rules became one, because two of them
were patching a **data** problem: it overclaimed because it could not *see* the caveats, and it
drifted into methodology because the caveats it had just been handed are ten lines of methodology.
Run over three plans with three rules and with one, the paragraphs came out equivalent — and the
three-rule version repeated the caveats anyway, which one of its own rules forbade.

## Which model, and why it barely matters

I used **Gemini 3.6 Flash on Google AI Studio's free tier**, which you name as fine, and moved to
`gpt-5-mini` when the free tier stopped: **20 requests per day**, and one sweep of the eight
questions is sixteen. Worth knowing before planning an eval run around it.

**"OpenAI-compatible" is not one protocol.** I wrote here that a provider swap was two environment
variables, then swapped and got two HTTP 400s:

```
max_tokens    rejected: "use max_completion_tokens instead"
temperature   rejected: "does not support 0.0 with this model"
```

The first is a rename. The second removes a design decision — temperature 0 is why the same question
routes the same way twice — and that model does not offer it. `ask()` adapts to both and **records
the adjustment on the answer**, because a run that could not be deterministic must not look like one
that was.

**Would a stronger model do better? Probably, in one place, and I would measure it rather than assume
it.** Its job is to read a question, pick a plan and write a paragraph; it cannot improve a single
number, because the arithmetic never touches it. The honest experiment compares **which caveats each
model dropped**, not which totals differ — the totals cannot differ.

## What I cut

- **No web interface.** The brief allows either; a UI would eat hours you are not evaluating.
- **No retrieval over the documents.** Four files, under 6 KB, read whole. Chunking would add an
  embedding model, a store and a threshold so the paragraph that answers the question can rank fourth
  and never arrive. Not hypothetical: a line-based search for the sentence deciding the FTE question
  returned nothing, because it spans a line break.
- **No database beyond the local file**, which is also your rule. No performance argument either —
  grouping all 10,916 rows takes 4 ms.
- **No dependencies at all.** Clone it, run it with Python 3.12.
- **The nightly-rate policy rule, after measuring it.** It is checkable from the free-text memo, 100%
  of Meridian's hotel memos parse, and it finds 7 breaches — but a memo format is a property of one
  file, and the approval rule answers the question from columns that exist.

## Roughly how long

**9.7 hours of active work**, measured rather than estimated: I read the timestamps of the working
session and discarded every gap over twenty minutes.

| | window | active |
| --- | --- | --- |
| Fri 14 Aug, evening | 16:42–21:34 | **2.3 h** |
| Sat 15 Aug | 09:27–19:37 | **7.4 h** |

Roughly two of those hours went on analysis before a line of code existed — writing the eight
expected answers, opening the CSVs, finding the traps. It felt like not working and it is the only
part that could not have been recovered later.

## What I would do with two more days

1. **A runner over the eight questions.** The arithmetic is checked mechanically against a contract
   written before the code; the prose is not checked at all. Each plan already declares what its
   answer must surface — that list should have a named emitter, so a requirement nobody satisfies
   fails loudly instead of quietly.
2. **Real cost accounting.** The ceiling reports $0.00 because nothing supplies prices. On a free
   tier that is true and still wrong: a reported zero reads as measured.
3. **Read documents in any format.** Only `.md` is seen today, so a `.txt` policy would make the
   assistant refuse for lack of a document sitting in the folder.
4. **A third dataset I did not build.** Both of mine are ones I understand. The interesting failures
   are in the one I do not.
