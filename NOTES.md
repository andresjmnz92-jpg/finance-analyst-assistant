# Notes

*Written as the work happened, not reconstructed afterwards.*

## How I used AI, and what I kept for myself

I used Claude Code throughout — for the tools, the SQL, and most of the prose in this repository.
What I did not delegate was the analysis. Before any code existed I wrote out the expected behaviour
for all eight questions by hand, including the two that should refuse, and every tool in
`ARCHITECTURE.md` fell out of that document rather than being designed up front.

That order mattered more than any prompt. Deciding what the answer should be, before knowing what
the code would return, is the only reason several wrong answers were caught at all.

Three decisions in this repository are mine and were argued for against a different suggestion:

- **Attack the exercise backwards.** Write the eight expected answers first, derive the tools from
  them. It is why there is no `run_anything` tool — there was nowhere for one to come from.
- **Do not look at the data until the problem is understood.** You end this brief with *"we'll ask
  you to walk through what you built"*. A repository I cannot explain loses the conversation that
  decides.
- **Build a second dataset whose answers I already know.** More on that below; it is the single
  most useful thing in here.

## Something that worked well

**The fixture in `evals/fixtures/`.** Eighteen rows, a flat 2.0 EUR rate, every figure worked out on
paper before a tool existed, and every ambiguity in your data reproduced in miniature — one missing
FX rate, one account that changes parent mid-year, one budget line duplicated with no version
column, one vendor spelled several ways, repeated amounts that are *not* duplicates.

It paid for itself immediately: checking my hand-written answers against SQL found **six arithmetic
errors of mine**, all of them rows I had missed while adding up. The data was not touched; my sums
were corrected. And because the same loader reads both datasets with no special case, running the
questions over both is itself the evidence that nothing is hardcoded to yours.

It also carries one case the tools get **wrong on purpose** — a vendor abbreviated `AERO FRT.` that
no name rule resolves. A fixture where everything passes is not measuring anything.

## Where the AI got it wrong, and how I noticed

Four times, and none of them raised an error.

**1. Silent miscount.** `convert_currency` reported *"1 row worth 1,231,309 EUR could not be
converted"*. The amount was right; the count was 147. Grouped rows each stand for many
transactions. Found by calling the same tool two ways — grouped and row-by-row — and comparing.

**2. The same bug twice, in one afternoon.** A vendor-name rule grouped three of Nordwind's four
spellings because stripping `LOG` from `NORDWIND LOG.` left `NORDWIND`. Fixed. A second rule then
grouped three of four again, because punctuation was removed before company suffixes, turning
`B.V.` into `B V`. Neither raised anything. The first was caught because a group total did not
match the sum of its parts; the second by counting members in the output.

**3. Empty answers that looked fine.** The first live model call returned HTTP 200 and an empty
string. Gemini reasons before answering; those tokens count against `max_tokens` and appear in
neither `prompt_tokens` nor `completion_tokens`. Measured: one word of output needs over a hundred
of them. My token ceiling was seeing 9 where the provider counted 106 — blind to 92% of the spend.

**4. The one that mattered most, and it was structural.** An adversarial review of the whole
repository found **20 defects**. Not one of them fires against your data: they fire against data
shaped differently. Two payments of the same magnitude in different currencies reported as one
payment made twice, because the match key omitted currency and every Meridian entity is
single-currency. Two companies sharing a cost centre code reported as conflicting budget versions,
because the partition omitted entity. A conversion to any currency other than USD returning a USD
figure with the wrong label.

Worst of all: several tools stated **Meridian's own measurements as fact** inside the notes that
travel into the final answer — which date ranges disagree, how many duplicates were planted. All
true here. All fabricated claims against any other dataset. The code refused to guess about data it
could not see, and then quoted figures from a file that was not loaded.

## The thing I had to correct repeatedly, and what stopped it

**Asserting things I had not measured.** It is the same failure in all four cases above, and it kept
coming back in different clothes.

Prompting did not fix it. What fixed it was making the rule structural:

- `evals/no_borrowed_facts.py` runs every tool against the fixture and **fails if any note mentions
  something only Meridian has**. A tool may describe what it measured; it may not remember.
- The date note now queries both columns and reports what it finds. Against the fixture:
  *"identical here, so the choice does not change this answer."* Against Meridian: *"they differ,
  and 114 rows fall in a different year depending on which is used."*
- Every tool returns `notes` as part of its result rather than logging them. A log is not read; an
  exception can be caught and dropped; a field in the answer has to be handled.

That is a rule I already use in a production WhatsApp sales bot, after one photo of a payment
receipt marked three orders as paid: **if the model disobeys and it does damage, it goes in code; if
it disobeys and it only looks bad, it goes in the prompt.** Precise numbers, duplicates and anything
that reaches an invoice are code. Tone is prompt.

## Which model, and why it barely matters

I used **Gemini 3.6 Flash on Google AI Studio's free tier**, which you name as expected and fine. I
have no budget for this, and a hiring exercise is not where a bill should appear.

**The provider is three environment variables — and "OpenAI-compatible" is not one protocol.** I
wrote here that a swap was two variables and no code change, then swapped to `gpt-5-mini` to check
it and got two HTTP 400s:

```
max_tokens    rejected: "use max_completion_tokens instead"
temperature   rejected: "does not support 0.0 with this model"
```

The first is a rename. The second removes a design decision: temperature 0 is why the same question
routes the same way twice, and that model does not offer it. `ask()` now adapts to both and
**records the adjustment on the answer**, because a run that could not be deterministic must not
look like one that was.

So the claim survives with an asterisk. Same code path, same three variables:

```bash
MODEL_BASE_URL=...    MODEL_NAME=...    MODEL_API_KEY=...
```

You will run it with your own credentials and nothing needs changing for that. It also means the
whole system works with no model at all: every tool is callable and testable without one, and a plan
can be run by name. The model is the thinnest layer in here, deliberately — measurably so, since
five of the eight questions are answered end to end with a single model call each, and that call
writes prose only.

**Would a stronger model do better? Probably, in one specific place — and I would measure it rather
than assume it.** The model's job here is to read an English question, pick a plan, and write the
answer carrying the caveats. A more capable model might handle a vaguer question, or notice an
ambiguity the plan does not list. It cannot improve a single number: the arithmetic never touches
it. So the honest experiment is to run the same eight questions on two models and compare **which
caveats each one dropped**, not which totals differ — the totals cannot differ.

That is the same test I already applied to autonomy, and to a retrieval layer I did not build. Free
was not a compromise here; it was the correct default until a measurement says otherwise.

## What I cut

- **No web interface.** The brief allows either; a UI would eat hours you are not evaluating.
- **No retrieval over the documents.** Four files, 5.4 KB. They are read whole. Chunking them would
  add an embedding model, a vector store and a similarity threshold so that the paragraph answering
  the question can rank fourth and never arrive. That failure is not hypothetical: a line-based
  search for the sentence that decides the FTE question returned nothing, because the sentence spans
  a line break.
- **No dependencies at all.** Clone it, run it with Python 3.12. An OpenAI-compatible chat call is
  JSON over HTTPS, and every package I do not add is one thing you do not install before seeing it
  work.
- **No autonomy where the path is known.** See `ARCHITECTURE.md` — and it is measured, not assumed.

## Roughly how long

**7.2 hours of active work**, and that figure is measured rather than estimated — I read the
timestamps of the working session and discarded every gap over twenty minutes.

| | window | active |
| --- | --- | --- |
| Fri 14 Aug, evening | 16:42–21:34 | **2.3 h** |
| Sat 15 Aug | 09:27–17:10 | **4.9 h** |

Roughly two of those hours went on analysis before a line of code existed — writing the eight
expected answers, opening the CSVs, finding the traps. It felt like not working and it is the only
part that could not have been recovered later.

I had written "about ten hours" here first, from memory. Measuring it showed I was nearly four
hours over, and the same measurement caught two weekday names I had also written from memory and
also got wrong. Leaving either in a document you asked me to be honest in would have been a small
lie in the one place it is easy to check.

## What I would do with two more days

1. **Make the review permanent.** Its findings are fixed, but only one became a test. Every edge
   case it found should be a check that runs with a single command — otherwise the next change
   quietly reintroduces them.
2. **Real cost accounting.** The ceiling reports $0.00 because nothing supplies prices. On a free
   tier that is true and still wrong: a reported zero reads as measured.
3. **Read documents in any format.** Today only `.md` is seen, so a `.txt` policy would make the
   assistant refuse for lack of a document sitting in the folder.
4. **A third dataset I did not build.** Both of mine are ones I understand. The interesting failures
   are in the one I do not.
