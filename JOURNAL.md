# Journal

The brief asks for one page each of ARCHITECTURE.md and NOTES.md. Those two are the
answer; this file is the working-out, and nothing here is needed to understand either
of them. It exists because the material below is true and measured, and deleting a
measurement to hit a page count is the wrong kind of tidy.

Read it if you want the evidence behind a claim. Skip it and you lose nothing.

## How this was approached

Six decisions, in the order they were taken. None is novel on its own; the order is the method.

**1. Write the answers before writing the code.** The eight expected behaviours were written by
hand first — what each answer must state, what it must not claim, and which of them should refuse
outright. That took roughly two hours of the first evening and produced **zero commits**, which is
why the hours table in `NOTES.md` disagrees with this repository's own commit timestamps. Deciding
what the answer should be, before knowing what the code returns, is the only reason several wrong
answers were caught at all.

**2. Derive the tools from those answers, do not design them.** Every tool exists because at least
one expected answer needed it, which is why there is no `run_anything` and no tool that takes free
SQL. Writing the answers first also surfaced the finding the architecture rests on: **not one of the
eight needs a model to decide which tool to call.**

**3. Do not open the data until the problem is understood.** The brief ends with *"we'll ask you to
walk through what you built"*, and a walkthrough of code you wrote against data you never read is a
walkthrough of guesses. The traps in the CSVs — the mid-period cost-centre rename, the missing FX
cell, the duplicate budget keys — were found by reading, before any of them could hide behind a
passing test.

**4. Build a second dataset whose answers you already know.** Eighteen rows, a flat 2.0 EUR rate,
every figure worked out on paper. It found six arithmetic errors of mine on day one, and on day two
it caught a defect in code ten minutes old. A dataset you understand completely is the only thing
that can tell you the code is wrong rather than merely different.

**5. Review cold, in parallel, and blind.** Sequential reviews inherit what the last one concluded.
The final review was four agents reading at the same time, each with a different lens, **none shown
the others' findings** — and when two report the same defect independently, the agreement carries
information that one reviewer's confidence does not. Five defects were found twice that way.

**6. Attack the design before implementing it, not after.** The fix for the renamed cost centre was
designed, then handed to a fresh agent **to refute rather than to build**. It came back with the
design measured instead of argued with: the suites exercise that plan on a quarter with no orphaned
centres, so the whole branch would have shipped untested. That is the lesson I did not have before —
**executing coldly and reviewing coldly are two different valves.** A fresh agent executes a bad
design perfectly.

Underneath all six is the rule that decides where anything lives: **if the model disobeys and it
does damage, it goes in code; if it only looks bad, it goes in the prompt.** That one did not come
from this exercise — it came from a production incident, and it is in `ARCHITECTURE.md`.

## Ceilings

`Budget` carries three and refuses the call that would cross one, rather than truncating: **12
model calls, 200,000 tokens, USD 0.50** per question.

**None of the three can fire in this design, and only one of those is a defect.**

The **money** ceiling is broken: `Model.ask` takes the per-million prices as arguments defaulting to
zero, nothing supplies them, so the running cost is always `0.00` and the comparison against USD
0.50 can never be true. The traces do not record which model produced them either, and a token count
without a model name cannot be turned into money.

The **step** and **token** ceilings are out of reach, which is the architecture working rather than
a defect. There is no tool loop: the model is called twice per question — once to route, once to
write — and once when the plan refuses before the writer. Twelve calls cannot happen because two is
the structural maximum; 200,000 cannot happen because the largest of the eight runs is 9,126. The
mechanism is sound: set `max_calls=2` and the third call is refused rather than truncated. **An
agent with a free-running loop would need these; this one has them because the brief asks, and the
honest thing is to say they have never fired** — a reported zero reads as measured, and an unfired
ceiling reads as an enforced one.

The evidence is the eight traces under [`traces/`](traces/): **35,212 tokens for all eight**, from
**1,040** to **9,126**. The smallest is `cost_per_fte`, which refuses after routing and never
reaches the writer, so a refusal costs one call instead of two. The count is `total_tokens` and not
prompt + completion, because reasoning tokens are billed inside the total and appear in neither of
the other two — summing those undercounted the real spend by 90%.

## What is measured and what is asserted

| Claim | Evidence |
| --- | --- |
| The figures are right **on Tessera** | Every plan checked field by field against `evals/fixtures/EXPECTED.md`, written by hand before the code. **By hand, not by a command:** no check in `evals/` reads that file. Meridian has no such file, by design — it is judged by behaviour instead, one row down |
| Nothing is hardcoded to Meridian | The same loader and the same plans run over both datasets; `python -m evals.no_borrowed_facts` fails if a tool's note mentions any of eighteen names, codes or figures that exist only in Meridian — a blacklist, so it catches the borrowed facts I knew about |
| The guards still fire | `python -m evals.guards` reproduces four of six fixed defects on a mutated copy of the fixture, plus a fifth from a later round, each verified in the failing direction. **Two of the six have no guard** |
| The router picks correctly | Measured by hand during development, two live sweeps of the eight questions; not automated here, because routing needs a model and the eval suites run without one |
| The answers declare what they must | **Automated in `evals/eight.py`.** First graded by an independent reviewer — two of five failed and the three causes were fixed. Now every `must_declare` entry has a named emitter, and the runner fails if its evidence is missing from the trace |

The honest remainder of that row: the trace is checked mechanically, the paragraph is not — prose
is still graded by reading it.

---

# From NOTES.md

*The five blocks below were moved out of `NOTES.md` whole, not rewritten, when that file
was cut down to the page the brief asks for. Each one is the working-out behind an answer
that is still there in short form.*

## The seven times I overruled the model, and what each was worth

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

## The review that found the wrong numbers: four readers who could not see each other


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

## The six measurements it stated without taking

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

## Why the Spanish variables were not swept


  **The reason it stopped there is the reason the rest of this file keeps circling.** Nothing in
  `evals/` checks that a figure is correct — measured, not assumed: a reviewer inflated every
  cost-centre total by 1% and all three suites stayed green. So a sweep across twelve files buys
  consistency and risks moving a number with nothing to catch it. The six that cross modules were
  safe to do because a missed one breaks an import loudly and the output diff over all eight plans
  came back empty, character for character. A hundred local renames have no such floor.

  With two more days it goes with the first item below: build the check that makes a figure change
  fail, then rename freely underneath it.

## The floor under the hours, and why the table is above it

The hours table in `NOTES.md` is the softest figure in this repository, so here is what can be
checked against it. Applying the same twenty-minute rule to this repository's own commit
timestamps gives **4.2 h for Saturday** (43 commits, 13:19 to 20:27) and **3.6 h for Sunday**
(48 commits, 13:24 to 22:02, in two sittings with a two-hour gap). Both are below the table.

That gap is the point rather than an error in it. **Friday produced 2.3 hours of work and zero
commits**, because it was spent writing the eight expected answers and finding the traps in the
CSVs before any code existed. A commit records when work was saved, not how long it took, and the
last two days were mostly reviewing and deciding — which produces few commits and no files.

An earlier version of this section published **2.1 h** as Sunday's floor. That figure was computed
over a window ending at 19:38, and half of Sunday's commits are later than that. Withdrawn rather
than quietly corrected: it is the same defect this file documents elsewhere, committed here.
