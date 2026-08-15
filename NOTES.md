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

About ten hours so far. Four on analysis before any code, which felt like not working and was the
only part that could not be recovered later. Two on the tools. Two more on the review and its
fallout. The rest on the fixture, twice — I rebuilt it once after finding six errors in my own
arithmetic and again after noticing your account hierarchy is three levels deep where mine was two.

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
