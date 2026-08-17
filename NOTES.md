# Notes

*Written as the work happened, not reconstructed afterwards.*

## How I used AI, and what I kept for myself

I used Claude Code throughout — for the tools, the SQL, and most of the prose in this repository.
What I did not delegate was the analysis. **Before any code existed I wrote out the expected
behaviour for all eight questions by hand**, including the ones that should refuse, and every tool
in `ARCHITECTURE.md` fell out of that document rather than being designed up front.

That order mattered more than any prompt. Deciding what the answer should be, before knowing what
the code would return, is the only reason several wrong answers were caught at all.

Three decisions set the shape before anything was built: **attack it backwards** — write the eight
expected answers first and derive the tools from them, which is why there is no `run_anything` tool;
**do not open the data until the problem is understood**, because you end this brief with *"we'll ask
you to walk through what you built"*; and **build a second dataset whose answers I already know**.

Then, repeatedly, I overruled the model's design and the measurement said I was right to. These are
the ones that changed the code:

| I pushed back with | What it was worth, measured |
| --- | --- |
| *Let the model translate the question into accounts, not a string rule* | **"headcount" matches zero accounts** in this chart — they are called Personnel and Salaries & Wages. A text rule goes mute on question 7. And picking the wrong rollup is not an error, it is a plausible figure: root 6830 answers **91,015.92** where the answer is **12,780,721.78** |
| *Then why not just hardcode the code?* | Forced the line I now work by: **shape is assumed, values are not**. The five tables and `rate_to_usd` are shape; an account code is a value, and your brief says the values change |
| *Showing the work sounds like two tables, not one* | Your own criterion, and it holds: Nordwind is the largest vendor grouped and **does not reach the top ten split**, at number 15. The ranking is a decision, so both are printed |
| *You are being too strict* | The figure guard was **deleting correct answers** over a truncated number, a correct sign and the numerals in a bulleted list. A guard that is wrong is worse than no guard: it now annotates instead of removing |
| *Is that a data problem or an obedience problem?* | Deleted two of the writer's three rules. Both were patching data, and the paragraphs came out equivalent without them |
| *Test it on a paid model too, not just the free one* | Found that **"OpenAI-compatible" is not one protocol** — and that a claim already published in this file was false |
| *What if we narrowed it first instead of reading every memo?* | The bound is provable and **saves 13%**, measured, so it was not built. The intersection that matters is one line, not a stage |

The pattern is the same every time: the model's instinct was defensible and the measurement decided
it. That is the working relationship, not a prompt.

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
| The first live model call returned HTTP 200 and an empty string | `finish_reason: length`. Reasoning tokens count against `max_tokens` and appear in neither `prompt_tokens` nor `completion_tokens` — my ceiling saw 9 where the provider counted 106 |

Those twenty were one review; a second one that afternoon — three agents rather than me, because
my own verification had found none of the twenty — turned up six different ones, each re-measured
here before it was accepted. **Four of those six have a guard in `evals/guards.py`; two do not.**
I wrote "each case is reproduced here" in that file's docstring while shipping four, which is the
same class of claim this whole section is about, and I only found it by counting.

**And at the end, the answers themselves were graded by someone other than me. Two of five failed** —
not on a figure, but because content the code had already computed sat in the findings as a raw key
and never reached a sentence. The vendor ranking existed only inside the model's paragraph, and 46%
of spend having no vendor at all was a number nobody said out loud. Both are now printed by code.

### The review that found the wrong numbers: four readers who could not see each other

The reviews above were sequential, and each one inherited what the last had concluded. The final
one was not. **Four agents read the repository at the same time, none of them shown the others'
findings**, each given a different lens: one reading it as your reviewer would, one auditing the
diffs, one hunting for figures that are wrong while looking right, one checking every claim the
documents and docstrings make about the code.

Blind and parallel buys one thing sequential does not: **when two of them report the same defect
independently, the agreement means something.** Five defects were found twice that way, including a
README row asserting every figure was checked against a file that holds figures for one of the two
datasets — and contradicting itself six lines below.

But the expensive findings came from the one nobody else duplicated, the reader comparing figures
against the data:

- **A cost centre was renamed mid-2024** — your own board memo says so — and nothing mapped the two
  codes. In Q1 and Q2 the centre with the largest overspend in the quarter was **dropped from the
  answer entirely** for having no budget line, while the code that inherited its budget was
  published at **−100%, "spent nothing"**, having spent 716,962.62.
- **The by-centre answer was ordered wrong at every rate on file**, because rows with no FX rate
  were totalled into an aggregate and never attributed to a centre — in the one question that asks
  *by cost centre*.
- **A year compared against itself was counted twice**, and a year with no rows read as a 100% fall
  instead of a refusal.

None of the three raise an error. All three print cleanly.

**And then the fix for the first one was killed before it was written.** I designed it as "read the
memo, map the codes", handed the design to a fresh agent to attack rather than to implement, and it
came back with the design measured rather than argued with: the suites run `budget_variance` on Q3,
Q3 has no orphaned centres, so the whole branch would have shipped untested — the exact thing
`guards.py` exists to forbid. It also fabricated a case where a centre that closed and a centre that
opened produce the same signature as a rename, which is why nothing here maps the codes. The plan
now prints both sides and lets the analyst do the mapping, which is what the memo asks the analyst
to do.

The lesson I did not have before: **executing coldly and reviewing coldly are two different valves.**
A fresh agent executes a bad design perfectly. Attacking the design costs one more agent and is the
one I nearly skipped.

## The thing I had to correct repeatedly, and what stopped it

**Stating a measurement it had not taken.** Every one of these was written into this repository as
fact, and every one is about the data or about the system — not about prose:

```
"the fourth largest"        Nordwind is the LARGEST. That docstring had recorded the figure
                            produced by the bug it describes, and outlived the fix
"216 of 228 pairs differ"   228 of 228 differ, and the same docstring said so correctly two
                            sentences earlier
"resolved window by window" the plan printed that sentence while querying the whole period
                            with the union of every window - caught by the fixture, five
                            candidates against six
"the eval runner asserts"   there was no eval runner when that was written (one exists
                            now: evals/eight.py)
several tools' notes        Meridian's own row counts and date ranges, stated as fact, in
                            text that travels into the answer against any dataset
"five of the six rules"     a fixed string enumerating Meridian's policy, emitted as a
                            decision against ANY dataset - already false against the
                            fixture, whose policy has four sections and none of those
                            rules. Found while anchoring the runner's emitters; it had
                            escaped no_borrowed_facts, which reads tool notes, and this
                            was a plan decision. The sentence is now built from the
                            headings of the documents the run actually read
```

Every one reads well and none was checked. Prompting did not fix it, because it is not disobedience
— a sentence that sounds measured costs nothing to write.

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

A stronger model cannot improve a single figure here, because the arithmetic never touches it. The
honest comparison is **which caveats each one dropped**, not which totals differ.

## What I cut

- **No web interface.** The brief allows either; a UI would eat hours you are not evaluating.
- **No retrieval over the documents.** Four files, under 6 KB, read whole. Chunking would add an
  embedding model, a store and a threshold so the paragraph that answers the question ranks fourth
  and never arrives — and that is not hypothetical: a line-based search for the sentence deciding
  the FTE question returned nothing, because it spans a line break.
- **No database beyond the local file**, which is also your rule. No performance argument either:
  grouping all 10,916 rows takes 4 ms. **No dependencies at all** — clone it, run it with 3.12.
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

1. **Judging the paragraph, not just the trace.** The runner over the eight has since been built
   (`evals/eight.py`): statuses judged by coherence with their own published evidence, every
   `must_declare` entry backed by a named emitter — and building it caught one more fixed-string
   claim, listed above. What still nobody checks by command is the written paragraph itself:
   whether the prose carries what the trace proved.
2. **Real cost accounting.** The ceiling reports $0.00 because nothing supplies prices. On a free
   tier that is true and still wrong: a reported zero reads as measured.
3. **Read documents in any format.** Only `.md` is seen today, so a `.txt` policy would make the
   assistant refuse for lack of a document sitting in the folder.
4. **A third dataset I did not build.** Both of mine are ones I understand. The interesting failures
   are in the one I do not.
