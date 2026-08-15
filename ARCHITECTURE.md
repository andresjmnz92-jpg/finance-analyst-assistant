# Architecture

> **Status: written before any code.** This document started as the specification, not as a
> write-up. The eight expected behaviours were written first; the tools below are what fell out of
> them. Sections marked *(pending)* will be filled in as the measurements come in.

## The decision this exercise is about

Your brief says the orchestration decision is the centre of the exercise, and also that autonomy is
a cost. Those pull in opposite directions, so here is where I landed and why.

**I wrote the eight expected behaviours before writing any tool.** Doing that surfaced something
uncomfortable: **none of the eight questions requires a model to decide which tool to call.** Even
Q5 — the one that genuinely needs two chained steps — has a plan that can be written down in
advance: *find the worst-deviating cost centre, then break that centre down by account and vendor.*
The second query depends on the first **result**, not on a first **decision**.

So the design is a deterministic router: the model reads the question and picks a named plan; the
plan decides the calls. *"Something decides which tools to call"* is satisfied — the something is a
router, and picking it over a free-running loop is the least autonomy that answers the question.

This is the workflow-versus-agent distinction: a workflow orchestrates the model with code you
control, an agent lets the model decide. The recommendation in
[Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) is to
reach for an agent only when the task is too ambiguous to route with code. Eight known question
shapes are not that.

### The rule I apply for what lives in code and what lives in the prompt

> **If the model disobeys and it does damage — code.**
> **If it disobeys and it only looks bad — prompt.**

I did not arrive at that here. It came out of a production WhatsApp sales bot I run, after one photo
of a payment receipt marked three orders as paid. That was not fixed by adding *"do not mark three"*
to the prompt; it was fixed with a 24-hour filter and an idempotency guard, and it never recurred.

It maps directly onto this exercise. Every plan carries a `must_declare` list — the year assumed,
the FX basis, the rows that could not be converted, that duplicates are candidates. Those are not
prompt instructions asking nicely. **The eval runner asserts they appear in the answer**, because a
total presented without its missing 147 rows is a confident wrong answer, and that is damage.

Prompt keeps what only looks bad if ignored: tone, ordering, how the caveat is phrased.

**I am not asserting the routing decision from principle either. I am measuring it.** For the three
questions where a model might plausibly do better than fixed control flow, both versions get built
and run:

| Question | Why it might need the model | Measured |
| --- | --- | --- |
| Q4 — vendor grouping | string normalisation is brittle; a model may match variants better | *(pending)* |
| Q5 — budget variance driver | the second query depends on the first result | *(pending)* |
| Q6 — T&E policy breaches | the policy has to be read and turned into checkable rules | *(pending)* |

Questions 1, 2, 3, 7 and 8 are deterministic by inspection and are not measured both ways; spending
the time to confirm the obvious would cost hours this exercise does not have. That is a declared
cut, not an oversight.

## Tools

Seven, each one small and boring. Every one of them exists because at least one of the eight
questions needs it — none was invented up front.

| Tool | What it does | Needed by |
| --- | --- | --- |
| `query_ledger` | filter the GL by period, account, cost centre, entity, vendor; group and sum | all |
| `resolve_accounts` | expand the account hierarchy to leaf accounts, **respecting `valid_from` / `valid_to`** | 1, 2, 5, 6, 7 |
| `convert_currency` | apply FX rates and **explicitly return what it could not convert** | 3, 4, 5 |
| `query_budget` | budget by centre/account/month, **flagging duplicate keys** | 5 |
| `normalize_vendors` | propose groupings of name variants; flag catch-all accounts | 4, 8 |
| `find_duplicate_payments` | candidates by business attributes, with evidence | 8 |
| `read_document` | return the text of one of the four internal documents | 3, 5, 6, 7 |

## Where I deliberately did not use an agent

**No vector store, no retrieval, no embeddings.** There are four internal documents totalling under
6 KB. They are read whole. Building retrieval here would be infrastructure in search of a problem.

**No free-running tool loop.** See above — it is measured, not assumed.

**`convert_currency` does not fill gaps.** Returning *"these 147 rows could not be converted"* is the
function, not a failure mode. This matters more than it sounds: the missing FX rate does not only
break Q3, it silently flips the sign of the budget variance for all three European cost centres. A
conversion that fails quietly contaminates every question downstream of it.

## The line between deterministic code and the model

| | Questions | Why |
| --- | --- | --- |
| Fixed path, no model in the loop | 1, 2 | The path is writable in advance |
| Model translates, fixed path executes | 3, 4, 8 | The model parses intent and writes the caveats; arithmetic and detection are code |
| Fixed two-step plan | 5 | The second query consumes the first result, but the sequence is known |
| Model reads and judges | 6, 7 | A document has to be interpreted and a rule declared checkable or not |

**The model never does arithmetic.** In all eight, every number comes from a tool.

## Ceilings

*(pending — step, token and cost limits go here once measured.)*

## Where I disagree

*(pending)*
