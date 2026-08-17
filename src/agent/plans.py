"""The plans. One per question shape, written down in advance.

THIS FILE IS THE ORCHESTRATION DECISION

The brief says two things that pull against each other:

    "Autonomy is a cost, not a feature. Use the least that answers the question."
    "Something decides which tools to call, in what order, and when the question
     is answered. That decision is the centre of this exercise."

Note the wording: SOMETHING decides, not A MODEL decides. Writing the eight
expected behaviours before any code made it clear that none of the eight needs a
model to choose the calls. Even Q5, which genuinely chains two queries, has a
sequence that can be written down: find the worst-deviating centre, then break
that centre down. The second query consumes the first RESULT - it does not
require a first DECISION.

So a plan is a named sequence of tool calls, and the model's job is to read the
question and pick one. What the model does not do is invent the path at runtime.

WHERE THE MODEL STILL EARNS ITS PLACE
  - reading an English question and choosing the plan and its parameters
  - reading a policy document and turning it into checkable rules (Q6)
  - writing the answer, carrying every caveat the tools returned

WHAT IS BEING MEASURED, NOT ASSERTED
For Q4, Q5 and Q6 a model-driven variant is built as well and both are run. If the
model version does better, that is the version that ships and the number says why.
"""

# Each plan declares which tools it uses, in what order, and which ambiguities
# whoever runs it has to resolve or state. The ambiguity list is not documentation:
# it is the contract an answer is judged against.

PLANS = {
    "opex_by_cost_centre": {
        "question": "What did we spend on operating expenses in Q2, by cost center?",
        "tools": ["resolve_accounts", "query_ledger", "convert_currency"],
        "must_declare": ["which year", "which date field defines the period",
                         "which account the phrase resolved to"],
        # Measured before deciding it: against Meridian, 'travel' matches one account,
        # 'operating expense' matches two (6000 and 6830, one inside the other) and
        # 'headcount' matches NONE - no account is called that, they are called
        # Personnel and Salaries & Wages. No string rule bridges that distance, so the
        # model picks from the list list_account_names returns and the code ties it
        # down: resolve_accounts resolves nothing that is not in force there.
        # What getting it wrong costs: with root 6830 this same plan answers
        # 91,015.92 where the answer is 12,780,721.78.
        "model_decides": ["which account code the phrase 'operating expenses' means"],
    },
    "spend_comparison": {
        "question": "How did travel spend in 2024 compare to 2023?",
        "tools": ["resolve_accounts", "query_ledger", "convert_currency"],
        # Two resolutions, one either side of 6230 changing parent. Not a detail of the
        # plan: resolving once for the whole year counts marketing spend as travel, or
        # loses travel spend, depending on which date is picked.
        "must_declare": ["account validity windows", "which date field defines the period",
                         "which account the phrase resolved to"],
        "model_decides": ["which account code the phrase 'travel' means"],
    },
    "consolidated_spend": {
        "question": "What was total consolidated spend in Q3, in USD?",
        "tools": ["query_ledger", "convert_currency"],
        "must_declare": ["which year", "the FX basis", "what could not be converted",
                         "which years can be totalled completely"],
        "model_decides": [],
    },
    "largest_vendors": {
        "question": "Who are our ten largest vendors by spend?",
        "tools": ["normalize_vendors", "query_ledger", "convert_currency"],
        # "the period" was missing and the question does not state one: undeclared, a
        # ranking of the whole ledger reads as if it were the current year. So was
        # "spend with no vendor": in Meridian that is 46% of spend - payroll - so a top
        # ten orders half the money while sounding like it ordered all of it.
        "must_declare": ["the vendor grouping applied", "catch-all vendors", "the FX basis",
                         "the period covered", "spend with no vendor"],
        "model_decides": ["whether to accept each proposed vendor grouping"],
    },
    "budget_variance": {
        "question": "Which cost centers came in worst against budget in Q3, and what "
                    "does the driver look like?",
        "tools": ["query_ledger", "convert_currency", "query_budget",
                  "query_ledger", "normalize_vendors"],
        "must_declare": ["worst by value or by percent", "two budget sets",
                         "unconverted rows by centre", "which sign flips because of them",
                         "centres with only one side of the comparison"],
        "model_decides": [],           # la variante con modelo elige el segundo desglose
    },
    "policy_breaches": {
        "question": "Which transactions look like they breached our T&E policy?",
        "tools": ["read_document", "resolve_accounts", "query_ledger", "convert_currency"],
        "must_declare": ["which policy rules are checkable with these columns",
                         "which are not"],
        "model_decides": ["turning the policy text into rules"],
    },
    "cost_per_fte": {
        "question": "What's our headcount cost per FTE?",
        "tools": ["resolve_accounts", "query_ledger", "read_document"],
        "must_declare": ["that the denominator is absent", "the source that says so"],
        "model_decides": [],
        "expected_refusal": True,
    },
    "duplicate_payments": {
        "question": "Did we pay anyone twice?",
        "tools": ["normalize_vendors", "find_duplicate_payments"],
        "must_declare": ["the matching criterion", "that these are candidates",
                         "recurring charges look identical"],
        "model_decides": [],
    },
}


def plan_names():
    return list(PLANS)


def describe(name):
    """One line per plan, for the model to choose from. Kept short on purpose: a
    long description invites the model to reason about the plan instead of picking
    it."""
    p = PLANS[name]
    return f"{name}: {p['question']}"
