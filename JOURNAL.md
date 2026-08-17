# Journal

The brief asks for one page each of ARCHITECTURE.md and NOTES.md. Those two are the
answer; this file is the working-out, and nothing here is needed to understand either
of them. It exists because the material below is true and measured, and deleting a
measurement to hit a page count is the wrong kind of tidy.

Read it if you want the evidence behind a claim. Skip it and you lose nothing.

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
