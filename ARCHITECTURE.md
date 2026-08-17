# Architecture

> **This document started as the specification, not the write-up.** The eight expected behaviours
> were written before any tool existed, and the tools below fell out of them. Where a claim here was
> later measured, the measurement replaced the claim.

> **You asked for one page and this is closer to two.** The cut I made was a different one:
> everything that does not answer one of your four questions moved to [`JOURNAL.md`](JOURNAL.md) —
> the ceilings, the measured-versus-asserted table, the evidence behind the claims. What is left
> here answers something you asked for, and the section headings are the table of contents.

## Where control flow is deterministic, and where the model decides

- The brief calls the orchestration decision the centre of the exercise and also calls autonomy a cost. Those pull in opposite directions; here is where I landed.
- **Writing the eight expected behaviours first surfaced something uncomfortable: not one of them needs a model to decide which tool to call.**
- Even Q5, which genuinely chains two steps, has a path writable in advance — *find the worst-deviating centre, then break that centre down.* The second query consumes the first **result**, not a first **decision**.
- So the model does exactly two things, and neither is a number:

```
  the question  ──▶  ROUTER    picks a plan and fills its parameters      (model)
                     ↓
                     PLAN      a written sequence of tool calls           (code)
                     ↓
                     TOOLS     SQL, arithmetic, FX, document text         (code)
                     ↓
                     WRITER    one paragraph over figures it did not compute  (model)
```

- *"Something decides which tools to call"* is satisfied, and the something is a router — the least autonomy that answers the question.
- [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) says to reach for an agent only when the task is too ambiguous to route with code. Eight known question shapes are not that.
- **Every plan also runs with no model at all** — `python -m src.ui.ask --plan largest_vendors` — which is how the figures here were checked against a hand-written contract.

### Why the line is there

> **If the model disobeys and it does damage — code. If it disobeys and it only looks bad — prompt.**

- That rule did not come from here. It came from a WhatsApp sales bot **I built and still run in production**, where one photo of a payment receipt marked three orders as paid.
- It was not fixed by adding *"do not mark three"* to a prompt. It was fixed with a 24-hour filter and an idempotency guard, and **it never recurred**.
- Applied here it deleted most of the prompt: the writer went from seven rules to one, because two were patching a **data** problem rather than disobedience.

| Rule deleted | Why |
| --- | --- |
| *"do not claim more than the caveats support"* | It overclaimed because it could not **see** the caveats. Showing them fixed it |
| *"answer, do not describe the method"* | The caveats it had just been handed are ten lines of method. The rule was patching this system's own input |

- Run over three plans with three rules and with one, the paragraphs came out equivalent — and the three-rule version repeated the caveats anyway, which one of its own rules forbade.
- What survives is the one rule whose breach does damage: **never calculate**. Behind it is a check in code, not trust.
- **Most of what must reach the reader never goes through the model at all:** figures are printed from the findings by code, caveats verbatim from the tool that measured them. It cannot forget what it was never asked to carry, and a warning nobody paraphrased cannot be softened.

## The tools, and why those

Eight, each small and boring. Every one exists because at least one of the eight questions needs it.

| Tool | What it does | Needed by |
| --- | --- | --- |
| `query_ledger` | filter the GL by period, account, centre, entity, vendor; group and sum | 1–7 |
| `resolve_accounts` | expand the hierarchy to leaf accounts, **respecting `valid_from`/`valid_to`** | 1, 2, 6, 7 |
| `list_account_names` | the chart as a menu, so the model picks a code instead of recalling one | 1, 2, 6, 7 |
| `convert_currency` | apply FX and **return what it could not convert**, plus the rate range | 1–6 |
| `query_budget` | budget by centre/account/month, **surfacing duplicate keys** | 5 |
| `normalize_vendors` | propose groupings of name variants; flag catch-alls | 4, 5, 8 |
| `find_duplicate_payments` | candidates by business attributes, with evidence | 8 |
| `read_document` | one internal document, whole | 6, 7 |

## Where the line falls, per question

| | Questions | What the model does |
| --- | --- | --- |
| Route only | 3, 4, 5, 8 | Names the plan. Nothing else. For 4 the vendor groupings are proposed by `normalize_vendors` and **accepted by the plan, not by the model** |
| Route and name an account | 1, 2, 6, 7 | Picks a code from `list_account_names`; `resolve_accounts` refuses a code not in force, so it cannot invent one |
| Route, name an account, supply a rule | 6 | The approval threshold. The plan looks for that number in the documents and says whether the rule is the policy's or the caller's |

**The model never does arithmetic.** In all eight, every figure comes from a tool.

| It tries | What the code does |
| --- | --- |
| A plan that does not exist | Rejected; the answer names the eight it knows |
| A parameter the plan does not take | Dropped, and the drop is reported in the trace |
| An account code that is not real | `resolve_accounts` returns no leaves and the plan refuses |
| A year with no data | Refused, naming the years that do have it |
| A figure no tool produced | Flagged above the answer, next to the measured figures |

- That last one **annotates rather than deletes**, and it was a correction. The first version threw the paragraph away after two retries.
- **It fired three times and was wrong all three:** a truncated numeral (`4099409` for 4,099,409.58), a correct sign (*"a decrease of 204,257.95"* where the measured value is negative), and the numerals of a bulleted list.
- A guard that is wrong is worse than no guard — it deleted correct answers over formatting, at two model calls each. Detection over prose is a heuristic, so it adds rather than removes.

## Where I deliberately did not use an agent

- **No vector store, no retrieval, no embeddings.** Four internal documents, under 6 KB, read whole.
- Chunking would add an embedding model, a store and a threshold, so the paragraph that answers the question can rank fourth and never arrive — not hypothetical: a line-based search for the sentence deciding Q7 returned nothing, because the sentence spans a line break.
- **No database beyond the local file**, which the brief also rules out. No performance argument either: `query_ledger` grouping all 10,916 rows returns in 13 ms and scanning every memo takes 1 ms — measured, and an earlier "4 ms" here was not reproducible.
- **No free-running tool loop.** The path is written down because it could be.
- **`convert_currency` does not fill gaps.** *"These 147 rows could not be converted"* is the function, not a failure mode — the missing rate does not only break Q3, it silently flips the sign of the budget variance for **43 centre/account pairs**, all three European cost centres.

## Where I disagree with one of yours

> *"A plausible wrong answer costs more than a refusal."*

True of an answer. **Not true of the guard that judges one** — and this repository has the
measurement rather than the opinion.

The principle rests on an asymmetry: withholding is cheap, being confidently wrong is expensive.
That holds when the thing deciding is a measurement. It **inverts** when the thing deciding is a
heuristic over free text, because then the guard is wrong too, and when it is wrong it withdraws a
*correct* answer — the same loss the principle avoids, plus the cost of getting there.

The figure guard is that case. Its first version obeyed the principle literally: any figure it could
not match got the paragraph rejected and rewritten twice. It fired three times, was wrong all three,
and nothing it caught was ever a fabrication.

So the rule here is narrower than yours: **a guard that cannot measure annotates; only a guard that
can measure refuses.** `cost_per_fte` refuses outright, because *"no column in this schema holds an
FTE count"* is a fact about the data. The figure guard annotates, because *"this string is not in my
list of measured numbers"* is a fact about a regular expression.

Being wrong in my direction costs a visible *"not verified"* line above a correct paragraph. Being
wrong in the other direction cost three deleted correct answers, and we paid it before changing it.
