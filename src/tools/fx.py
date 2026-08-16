"""convert_currency - turn amounts in local currency into one reporting currency.

THE ONE THING THIS TOOL MUST NEVER DO IS FAIL QUIETLY.

Meridian's fx_rates table is a 24-month by 3-currency grid with exactly one cell
missing: 2024-09 EUR. That single gap sits inside Q3, and it is worth 147 rows and
EUR 1,231,309 - about a third of the euro spend in the quarter. An inner join
against the rate table drops those rows and returns a total that looks right.

Worse, it does not stop at the consolidated total. The same gap makes all three
European cost centres look UNDER budget for Q3. Their real deviation is positive.
A conversion that swallows a gap contaminates every question downstream of it,
which is why what could not be converted is part of the return value and not a
log line.

The rate table also carries no type column - nothing says whether these are spot,
average or closing rates. That is not something this tool can resolve, so it
states the assumption it is operating under and lets the answer carry it.
"""

RATE_BASIS = (
    "fx_rates has one rate per month per currency and no column saying whether it "
    "is spot, average or closing. Applied as a month-average rate against the "
    "transaction's accrual month."
)


def convert_currency(con, rows, to="USD"):
    """Convert rows to `to`, reporting whatever could not be converted.

    rows: an iterable of dicts carrying at least `amount`, `currency` and
    `period_month` (YYYY-MM). Any other key is passed through untouched, so this
    works on single transactions and on grouped totals alike.

    A row may carry `rows` — how many ledger transactions it stands for. Grouped
    input always does. It is honoured when counting what could not be converted,
    because "1 row worth 1,231,309 EUR" reads like one odd payment when it is
    really 147 transactions. Absent, a row counts as one.

    Returns result / notes / sql. `result["unconverted"]` is never omitted: an
    empty list is a positive statement that nothing was dropped.
    """
    # The column is rate_to_usd and it only converts INTO dollars. Accepting another
    # target and applying the same rate returned a USD figure wearing the wrong label -
    # 273 where the answer was 157, with no note anywhere. It refuses rather than
    # miscalculating, because the parameter exists and somebody will use it.
    if to != "USD":
        raise ValueError(
            f"fx_rates only carries rate_to_usd, so USD is the only target this table "
            f"supports. Converting to {to} would need cross rates that are not in the "
            f"pack. Convert to USD and state the basis, or add a rate table that has {to}.")

    tasas, repetidas = {}, {}
    for m, c, r in con.execute("SELECT period_month, currency, rate_to_usd FROM fx_rates"):
        if (m, c) in tasas and tasas[(m, c)] != r:
            # A repeated key with a different value silently rescales EVERYTHING: the
            # dict keeps whichever row SQLite returned last, which is not a decision.
            repetidas.setdefault((m, c), {tasas[(m, c)]}).add(r)
        tasas[(m, c)] = r

    convertidas, sin_tasa, transacciones = [], {}, 0
    for fila in rows:
        moneda, mes = fila["currency"], fila["period_month"]
        tasa = 1.0 if moneda == to else tasas.get((mes, moneda))
        if tasa is None:
            k = (mes, moneda)
            hueco = sin_tasa.setdefault(k, {"period_month": mes, "currency": moneda,
                                            "amount": 0.0, "rows": 0, "groups": 0})
            hueco["amount"] += fila["amount"]
            hueco["rows"] += fila.get("rows", 1)
            hueco["groups"] += 1
            continue
        convertidas.append({**fila, "amount": round(fila["amount"] * tasa, 2),
                            "currency": to, "source_amount": fila["amount"],
                            "source_currency": moneda, "rate": tasa})
        transacciones += fila.get("rows", 1)

    huecos = sorted(sin_tasa.values(), key=lambda h: (h["period_month"], h["currency"]))
    notas = [RATE_BASIS]
    if repetidas:
        detalle = "; ".join(f"{m}/{c}: {sorted(v)}" for (m, c), v in sorted(repetidas.items()))
        notas.append(f"AMBIGUOUS RATES - {len(repetidas)} month/currency key(s) appear more "
                     f"than once with different values: {detalle}. One was applied and the "
                     f"choice is arbitrary; every figure below that touches those months is "
                     f"affected. The rate table needs a version or a type column.")
    if huecos:
        filas = sum(h["rows"] for h in huecos)
        detalle = "; ".join(f"{h['rows']} ledger rows worth {h['amount']:,.2f} "
                            f"{h['currency']} in {h['period_month']}" for h in huecos)
        notas.append(f"NOT CONVERTED - no rate on file for {len(huecos)} month/currency "
                     f"combination(s), covering {filas} rows: {detalle}. Any total below "
                     f"excludes them and is therefore partial.")

    return {
        "result": {
            "rows": convertidas,
            "total": round(sum(f["amount"] for f in convertidas), 2),
            "currency": to,
            "rows_converted": transacciones,
            "groups_converted": len(convertidas),
            "unconverted": huecos,
            # The rate range per currency, measured on this file. It bounds what could
            # not be converted: "100 EUR missing" says nothing, while "between 110 and
            # 120 USD missing" decides whether a deviation changes sign.
            "rate_range": {m: [min(v), max(v)] for m, v in sorted(
                {c: [r for (_, cc), r in tasas.items() if cc == c]
                 for c in {cc for _, cc in tasas}}.items())},
        },
        "notes": notas,
        "sql": [("SELECT period_month, currency, rate_to_usd FROM fx_rates", ())],
    }
