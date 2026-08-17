# Architecture

> **This document started as the specification, not the write-up.** The eight expected behaviours
> were written before any tool existed, and the tools below are what fell out of them. Where a
> claim here was later measured, the measurement replaced the claim.

## The decision this exercise is about

The brief says the orchestration decision is the centre of the exercise, and also that autonomy is
a cost. Those pull in opposite directions. Here is where I landed.

**Writing the eight expected behaviours first surfaced something uncomfortable: none of the eight
needs a model to decide which tool to call.** Even Q5, the one that genuinely chains two steps, has
a path that can be written down in advance — *find the worst-deviating centre, then break that
centre down.* The second query consumes the first **result**, not a first **decision**.

So the model does exactly two things, and neither is a number:

```
  the question  ──▶  ROUTER    picks a plan and fills its parameters      (model)
                     ↓
                     PLAN      a written sequence of tool calls           (code)
                     ↓
                     TOOLS     SQL, arithmetic, FX, document text         (code)
                     ↓
                     WRITER    one paragraph over figures it did not compute  (model)
```

*"Something decides which tools to call"* is satisfied, and the something is a router. Picking that
over a free-running loop is the least autonomy that answers the question — the
[Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents)
recommendation is to reach for an agent only when the task is too ambiguous to route with code, and
eight known question shapes are not that.

**Every plan also runs with no model at all** — `python -m src.ui.ask --plan largest_vendors`. That
is what "real computation, testable without the model" means here, and it is how the figures in
this repository were checked against a hand-written contract.

### The rule for what lives in code and what lives in the prompt

> **If the model disobeys and it does damage — code.**
> **If it disobeys and it only looks bad — prompt.**

That did not come from here. It came from a production WhatsApp sales bot, after one photo of a
payment receipt marked three orders as paid. It was not fixed by adding *"do not mark three"* to a
prompt; it was fixed with a 24-hour filter and an idempotency guard, and it never recurred.

Applied here, it removed most of the prompt. The writer's instructions went from seven rules to
one, because two of them were patching a **data** problem rather than disobedience:

| Rule | Why it was removed |
| --- | --- |
| *"do not claim more than the caveats support"* | It overclaimed because it could not **see** the caveats. Showing them fixed it. |
| *"answer, do not describe the method"* | It described the method because the caveats it had just been handed are ten lines of method. The rule was patching this system's own input. |

Run over three plans with three rules and with one, the paragraphs came out equivalent — and the
three-rule version repeated the caveats anyway, which is what one of its own rules forbade. What
survives is the one rule whose breach does damage: **never calculate**. Behind it is a check in
code, not trust.

**And most of what must reach the reader never goes through the model at all.** The figures are
printed from the findings by code; the caveats are printed verbatim from the tool that measured
them. It cannot forget what it was never asked to carry, and a warning nobody paraphrased cannot be
softened.

## Tools

Eight, each one small and boring. Every one exists because at least one of the eight questions
needs it.

| Tool | What it does | Needed by |
| --- | --- | --- |
| `query_ledger` | filter the GL by period, account, centre, entity, vendor; group and sum | 1–7 |
| `resolve_accounts` | expand the hierarchy to leaf accounts, **respecting `valid_from`/`valid_to`** | 1, 2, 6, 7 |
| `list_account_names` | the chart as a menu, so the model picks a code instead of recalling one | 1, 2, 6, 7 |
| `convert_currency` | apply FX and **return what it could not convert**, plus the rate range | 1, 2, 3, 4, 5, 6 |
| `query_budget` | budget by centre/account/month, **surfacing duplicate keys** | 5 |
| `normalize_vendors` | propose groupings of name variants; flag catch-alls | 4, 5, 8 |
| `find_duplicate_payments` | candidates by business attributes, with evidence | 8 |
| `read_document` | one internal document, whole | 6, 7 |

## Where the line falls, per question

| | Questions | What the model does |
| --- | --- | --- |
| Route only | 3, 4, 5, 8 | Names the plan. Nothing else. For 4, the vendor groupings are proposed by `normalize_vendors` and **accepted by the plan, not by the model** |
| Route and name an account | 1, 2, 6, 7 | Picks a code from `list_account_names`; `resolve_accounts` refuses a code that is not in force, so it cannot invent one |
| Route, name an account, supply a rule | 6 | The approval threshold. The plan then looks for that number in the documents and says whether the rule is the policy's or the caller's |

**The model never does arithmetic.** In all eight, every figure comes from a tool.

## What the code refuses to let the model do

| It tries | What happens |
| --- | --- |
| A plan that does not exist | Rejected; the answer names the eight it knows |
| A parameter the plan does not take | Dropped, and the drop is reported in the trace |
| An account code that is not real | `resolve_accounts` returns no leaves and the plan refuses |
| A year with no data | Refused, naming the years that do have it |
| A figure that no tool produced | Flagged above the answer, next to the measured figures |

The last one **annotates rather than deletes**, and that was a correction. The first version threw
the paragraph away after two retries — and it was wrong three times, over a truncated figure
(`4099409` for 4,099,409.58), a correct sign (*"a decrease of 204,257.95"* where the measured value
is negative) and the numerals in a bulleted list. A guard that is wrong is worse than no guard: it
deleted correct answers over formatting and spent two model calls doing it. Detection over prose is
a heuristic, so it adds rather than removes.

## Where I deliberately did not use an agent

**No vector store, no retrieval, no embeddings.** Four internal documents, under 6 KB, read whole.
Chunking them would add an embedding model, a store and a threshold so the paragraph that answers
the question can rank fourth and never arrive. That failure is not hypothetical: a line-based
search for the sentence deciding Q7 returned nothing, because the sentence spans a line break.

**No database beyond the local file**, which the brief also rules out. There is no performance
argument either: grouping all 10,916 rows takes 4 ms and scanning every memo takes 2 ms.

**No free-running tool loop.** The path is written down because it could be.

**`convert_currency` does not fill gaps.** Returning *"these 147 rows could not be converted"* is
the function, not a failure mode — the missing rate does not only break Q3, it silently flips the
sign of the budget variance for **43 centre/account pairs**, all three European cost centres.

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
the structural maximum; 200,000 cannot happen because the largest of the eight runs is 9,757. The
mechanism is sound: set `max_calls=2` and the third call is refused rather than truncated. **An
agent with a free-running loop would need these; this one has them because the brief asks, and the
honest thing is to say they have never fired** — a reported zero reads as measured, and an unfired
ceiling reads as an enforced one.

The evidence is the eight traces under [`traces/`](traces/): **36,359 tokens for all eight**, from
**1,239** to **9,757**. The smallest is `cost_per_fte`, which refuses after routing and never
reaches the writer, so a refusal costs one call instead of two. The count is `total_tokens` and not
prompt + completion, because reasoning tokens are billed inside the total and appear in neither of
the other two — summing those undercounted the real spend by 90%.

## Where I disagree with one of yours

> *"A plausible wrong answer costs more than a refusal."*

**True of an answer. Not true of the guard that judges one, and this repository has the measurement
rather than the opinion.**

The principle rests on an asymmetry: withholding is cheap, being confidently wrong is expensive. It
holds when the thing deciding is a measurement. It **inverts** when the thing deciding is a
heuristic over free text — because then the guard is wrong too, and when it is wrong it withdraws a
*correct* answer. That is the same loss the principle is trying to avoid, plus the cost of arriving
at it.

The figure guard is exactly that case. Its first version obeyed the principle literally: any figure
it could not match got the paragraph rejected and rewritten, twice, before falling back to bare
figures. **It fired three times and was wrong all three** — a truncated numeral, a correct sign, and
the ordinals of a bulleted list, all detailed above. Three correct answers deleted over formatting,
at two model calls each. Nothing it caught was ever a fabrication.

So the rule here is narrower than yours: **a guard that cannot measure annotates; only a guard that
can measure refuses.** `cost_per_fte` refuses outright, because "no column in this schema holds an
FTE count" is a fact about the data. The figure guard annotates, because "this string does not
appear in my list of measured numbers" is a fact about a regular expression.

The cost of being wrong in my direction is a visible line reading *"not verified"* above a correct
paragraph. The cost of being wrong in the other direction was a deleted correct answer, and we paid
it three times before changing it.

## What is measured and what is asserted

| Claim | Evidence |
| --- | --- |
| The figures are right **on Tessera** | Every plan checked field by field against `evals/fixtures/EXPECTED.md`, written by hand before the code. **By hand, not by a command:** no check in `evals/` reads that file. Meridian has no such file, by design — it is judged by behaviour instead, one row down |
| Nothing is hardcoded to Meridian | The same loader and the same plans run over both datasets; `python -m evals.no_borrowed_facts` fails if a tool's note mentions anything only Meridian has |
| The guards still fire | `python -m evals.guards` reproduces each fixed defect on a mutated copy of the fixture, and each was verified in the failing direction |
| The router picks correctly | Measured by hand during development, two live sweeps of the eight questions; not automated here, because routing needs a model and the eval suites run without one |
| The answers declare what they must | **Automated in `evals/eight.py`.** First graded by an independent reviewer — two of five failed and the three causes were fixed. Now every `must_declare` entry has a named emitter, and the runner fails if its evidence is missing from the trace |

The honest remainder of that row: the trace is checked mechanically, the paragraph is not — prose
is still graded by reading it.
