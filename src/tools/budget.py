"""query_budget - what was planned, and the fact that there may be two plans.

THE PROBLEM THIS TOOL REFUSES TO HIDE

In Meridian one cost centre carries its budget twice. OPS-AMER has 456 rows where
its shape says 228 - nineteen accounts across twelve months - and all 228 keys
repeat with DIFFERENT amounts. Not one is an identical copy, so it is not a paste
error: there are two sets of figures for the same twelve months.

There is no version column. Nothing in the pack says which is current. Three
documented explanations were tested and all three fail:

    the 4% H2 cut in the board memo   -> set B is +14.1% in H1 and +14.6% in H2
    the plan restated onto OPS-AMER   -> 228 of 228 pairs differ in amount
    a uniform rescale                 -> pair ratios run from 0.755 to 1.709

So the tool returns BOTH sets and says it cannot choose. A caller that wants one
number has to state a rule; a caller that reports one number without stating it is
producing the plausible wrong answer this exercise is about.

The only thing separating the two sets is the order they appear in the file, which
is a property of the CSV and not of the business. That is stated too.

Two more facts a caller must carry: the budget is in USD while the ledger is in
local currency, and it covers 2024 only.
"""

DETECTION = (
    "Duplicate keys are found by grouping on entity + cost_centre + account_code + "
    "period_month, never by row count. A row count is a property of one file; a "
    "repeated key is a property of the data."
)


def query_budget(con, period_from=None, period_to=None, cost_centres=None, accounts=None):
    """Budget rows for a period, with duplicate keys surfaced rather than merged.

    Returns one entry per (centre, account, month, version). `version` is 1 for the
    first occurrence in file order and 2 for the second - a label, not a claim
    about which is current.
    """
    donde, params = [], []
    if period_from:
        donde.append("period_month >= ?"); params.append(period_from)
    if period_to:
        donde.append("period_month <= ?"); params.append(period_to)
    for col, val in (("cost_centre", cost_centres), ("account_code", accounts)):
        if val is not None:
            if not val:
                donde.append("1 = 0")
            else:
                donde.append(f"{col} IN ({','.join('?' * len(val))})"); params += list(val)

    # entity va en la particion. Sin ella, dos sociedades que comparten codigo de
    # centro - normal en un grupo - salen como "dos versiones del presupuesto en
    # conflicto", que es la alarma principal de esta herramienta disparandose sobre
    # dos lineas correctas y sin relacion.
    sql = ("SELECT entity, cost_centre, account_code, period_month, budget_amount, currency, "
           "ROW_NUMBER() OVER (PARTITION BY entity, cost_centre, account_code, period_month "
           "ORDER BY rowid) AS version "
           "FROM budget "
           + (f"WHERE {' AND '.join(donde)} " if donde else "")
           + "ORDER BY cost_centre, account_code, period_month, version")

    cols = ["entity", "cost_centre", "account_code", "period_month", "amount", "currency", "version"]
    filas = [dict(zip(cols, r)) for r in con.execute(sql, params)]

    versiones = sorted({f["version"] for f in filas})
    afectados = sorted({f["cost_centre"] for f in filas if f["version"] > 1})

    # Los totales por version se calculan SOLO sobre las claves que tienen dos, y el
    # resto va aparte. Sumando todo, "set 1" incluiria los ocho centros sanos y
    # "set 2" solo el duplicado: dos cifras correctas puestas de forma que se leen
    # como un recorte del 90% que nunca existio.
    duplicadas = {(f["entity"], f["cost_centre"], f["account_code"], f["period_month"])
                  for f in filas if f["version"] > 1}
    totales = {v: round(sum(f["amount"] for f in filas if f["version"] == v
                            and (f["entity"], f["cost_centre"], f["account_code"], f["period_month"])
                            in duplicadas), 2)
               for v in versiones} if duplicadas else {}
    sin_ambiguedad = round(sum(f["amount"] for f in filas
                               if (f["entity"], f["cost_centre"], f["account_code"], f["period_month"])
                               not in duplicadas), 2)

    notas = ["Budget is stated in USD while the ledger is in local currency, and it "
             "covers 2024 only. Comparing actual to plan needs a rate, and it will "
             "not be the rate used to build the plan.",
             DETECTION]

    if len(versiones) > 1:
        notas.append(
            f"TWO BUDGET SETS for {', '.join(afectados)}. Same centre, account and month, "
            f"different amounts, and no version column: they are told apart ONLY by their "
            f"order in the file. Across the duplicated keys ONLY: "
            + ", ".join(f"set {v} = {t:,.2f}" for v, t in totales.items())
            + f". Every other key in this period totals {sin_ambiguedad:,.2f} and is not in "
              f"question. Nothing in the data says which set is current, so any single "
              f"figure derived from one of them must state which rule was applied.")

    if not filas:
        notas.append("No budget rows matched. The budget covers 2024 only - a request for "
                     "2023 returns nothing, and that is not the same as a zero budget.")

    return {
        "result": {"rows": filas, "versions": versiones,
                   "totals_by_version_duplicated_keys_only": totales,
                   "total_unambiguous": sin_ambiguedad,
                   "centres_with_two_sets": afectados},
        "notes": notas,
        "sql": [(sql, tuple(params))],
    }
