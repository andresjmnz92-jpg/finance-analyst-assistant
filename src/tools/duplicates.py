"""find_duplicate_payments - candidates with their evidence. Never a verdict.

WHAT DOES NOT WORK, MEASURED

Meridian contains seven planted duplicate payments. The obvious approach - same
vendor and amount within a few days - finds four of them. Three sit exactly 30
days apart, because they imitate a monthly billing cycle, and widening the window
to catch those starts confusing them with next month's subscription.

The fix was not a better window. It was dropping the date from the criterion
entirely:

    entity + cost centre + account + vendor + amount, ignoring dates
        -> 9 candidate groups in Meridian, containing all 7 planted ones
    ...and within the same month  -> 4 groups, misses 3
    ...and on the same day        -> 4 groups, misses 3

Nine candidates for seven real ones. Two false positives is the honest cost of not
missing three.

WHAT WOULD WORK AND MUST NOT BE USED

All seven planted duplicates carry a doc_ref sequence at or above 600000 while the
10,909 genuine rows run 000001 to 010916. It is a perfect signature - and it is an
artefact of how this file was generated. The brief says these tools will be run
against a second dataset, so keying on it would score perfectly here and find
nothing there, without raising anything. It is not used, and saying why is part of
the answer.

WHY CANDIDATES AND NOT ANSWERS

A monthly rent, a recurring licence and a genuine double payment are identical in
this data. In the fixture, four of the five groups found are legitimate repeat
purchases and only one is a real duplicate - and no rule available here can tell
them apart. A tool that reports one confident duplicate has silently thrown away
the ones it could not judge. Credit notes make it worse: 31 rows in Meridian are
exact reversals of real invoices, so a naive detector flags them as duplicates.
"""

# Se agrupa por lo que define un pago, no por cuando se registro. `currency` no es
# opcional: sin ella, 5.000 EUR y 5.000 USD al mismo proveedor salen como un pago
# hecho dos veces. En Meridian cada entidad usa una sola moneda y no se nota nunca;
# en otro dataset con una entidad multimoneda es un duplicado inventado.
CLAVE = ("entity", "cost_centre", "account_code", "currency", "amount", "vendor_id")


def find_duplicate_payments(con, vendor_groups=None, date_from=None, date_to=None):
    """Groups of rows that could be the same payment made twice.

    vendor_groups: optional output of normalize_vendors. Applying it widens the net,
    because the same company spelled two ways hides a duplicate from a vendor_id
    match. It is not applied by default - that is a judgement the caller makes.
    """
    donde, params = ["vendor_id <> ''"], []
    if date_from:
        donde.append("accrual_date >= ?"); params.append(date_from)
    if date_to:
        donde.append("accrual_date <= ?"); params.append(date_to)

    sql = (f"SELECT txn_id, {', '.join(CLAVE)}, accrual_date, doc_ref, memo "
           f"FROM gl_transactions WHERE {' AND '.join(donde)} ORDER BY txn_id")
    cols = ["txn_id", *CLAVE, "accrual_date", "doc_ref", "memo"]
    filas = [dict(zip(cols, r)) for r in con.execute(sql, params)]

    # El mapa de proveedor a grupo: sin el, "Nordwind Logistics" y "NORDWIND LOG."
    # son dos proveedores y el duplicado entre ambos no se ve.
    alias = {}
    if vendor_groups:
        for g in vendor_groups:
            for m in g["members"]:
                alias[m["vendor_id"]] = g["key"]

    grupos = {}
    for f in filas:
        k = tuple(alias.get(f[c], f[c]) if c == "vendor_id" else f[c] for c in CLAVE)
        grupos.setdefault(k, []).append(f)

    candidatos = []
    for k, miembros in grupos.items():
        if len(miembros) < 2:
            continue
        fechas = sorted(m["accrual_date"] for m in miembros)
        separacion = [(__import__("datetime").date.fromisoformat(b)
                       - __import__("datetime").date.fromisoformat(a)).days
                      for a, b in zip(fechas, fechas[1:])]
        candidatos.append({
            **dict(zip(CLAVE, k)), "vendor": k[CLAVE.index("vendor_id")],
            "rows": [{c: m[c] for c in ("txn_id", "accrual_date", "doc_ref", "memo")}
                     for m in miembros],
            "extra_rows": len(miembros) - 1,
            "days_between": separacion,
            "looks_periodic": all(25 <= d <= 35 for d in separacion) if separacion else False,
        })
    candidatos.sort(key=lambda c: (-c["extra_rows"], -abs(c["amount"] or 0)))

    extras = sum(c["extra_rows"] for c in candidatos)
    periodicos = sum(1 for c in candidatos if c["looks_periodic"])
    notas = [
        "Grouped on entity + cost centre + account + currency + amount + vendor, IGNORING "
        "dates. A date window is the obvious approach and it misses duplicates spaced a "
        "full billing cycle apart, so the gap is reported as evidence instead of used as "
        "a filter.",
        "doc_ref is deliberately NOT used as a criterion, even where document numbering "
        "would separate genuine duplicates cleanly. Numbering patterns are properties of "
        "how a file was produced, not of the business, and would not carry to another "
        "dataset.",
        "These are CANDIDATES. A monthly rent, a recurring licence and a genuine double "
        "payment can be indistinguishable, and a credit note reverses a real invoice "
        "exactly. Deciding is the analyst's job, not this tool's.",
    ]
    if periodicos:
        notas.append(f"{periodicos} group(s) are spaced 25-35 days apart, which is what a "
                     f"monthly charge looks like. Flagged, not excluded - a duplicate can "
                     f"land a month later too.")
    if vendor_groups:
        notas.append(f"Vendor variants were merged using {len(vendor_groups)} proposed "
                     f"group(s) before matching. Without that, the same company spelled two "
                     f"ways hides a duplicate.")
    else:
        notas.append("Vendor variants were NOT merged. If the same company appears under more "
                     "than one vendor_id, duplicates between the spellings are invisible here.")

    return {
        "result": {"candidate_groups": candidatos, "group_count": len(candidatos),
                   "extra_rows": extras},
        "notes": notas,
        "sql": [(sql, tuple(params))],
    }
