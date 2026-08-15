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

# Cada plan declara: que herramientas usa, en que orden, y que ambiguedades tiene
# que resolver o declarar quien lo ejecute. La lista de ambiguedades no es
# documentacion: el runner comprueba que la respuesta las menciona.

PLANS = {
    "opex_by_cost_centre": {
        "question": "What did we spend on operating expenses in Q2, by cost center?",
        "tools": ["resolve_accounts", "query_ledger", "convert_currency"],
        "must_declare": ["which year", "which date field defines the period"],
        "model_decides": [],
    },
    "spend_comparison": {
        "question": "How did travel spend in 2024 compare to 2023?",
        "tools": ["resolve_accounts", "query_ledger", "convert_currency"],
        # Dos resoluciones, una a cada lado del cambio de padre de la 6230. No es un
        # detalle del plan: resolver una sola vez para todo el ano cuenta el gasto de
        # marketing como viajes, o pierde el de viajes, segun la fecha que se elija.
        "must_declare": ["account validity windows", "which date field"],
        "model_decides": [],
    },
    "consolidated_spend": {
        "question": "What was total consolidated spend in Q3, in USD?",
        "tools": ["query_ledger", "convert_currency"],
        "must_declare": ["which year", "the FX basis", "what could not be converted"],
        "model_decides": [],
    },
    "largest_vendors": {
        "question": "Who are our ten largest vendors by spend?",
        "tools": ["normalize_vendors", "query_ledger", "convert_currency"],
        "must_declare": ["the vendor grouping applied", "catch-all vendors", "the FX basis"],
        "model_decides": [],           # la variante con modelo agrupa los nombres
    },
    "budget_variance": {
        "question": "Which cost centers came in worst against budget in Q3, and what "
                    "does the driver look like?",
        "tools": ["query_ledger", "convert_currency", "query_budget", "query_ledger"],
        "must_declare": ["worst by value or by percent", "two budget sets",
                         "unconverted rows by centre"],
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
