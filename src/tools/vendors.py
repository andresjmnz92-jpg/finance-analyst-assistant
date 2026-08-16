"""normalize_vendors - PROPOSE vendor groupings. It never merges anything.

WHY PROPOSE AND NOT MERGE

Meridian lists Nordwind four times - Nordwind Logistics, NORDWIND LOG.,
Nordwind Logistik B.V., Nordwind Logistics BV - each with its own vendor_id,
because each was created separately by someone who could not find the existing
one. Forty-three rows for thirty-nine real vendors. It changes the answer: split
four ways Nordwind does not reach the top ten at all, its best variant sitting at
number 15; grouped it is the LARGEST vendor in the company at 4,099,409.58.

This line said "the fourth largest" until the ranking was actually run, and the
wrong number was a fossil of the bug described below: with the broken grouping
Nordwind totalled 3.09M, which sits behind Atlas 3.66M, Harbourgate 3.58M and
Kestrel 3.46M - fourth. The docstring had recorded the figure the bug produced,
survived the fix, and would have been read as the true answer.

But vendors.csv has four columns and none of them is a tax identifier. Nothing in
the data PROVES those four are one company. The evidence is strong - all four run
January 2023 to December 2024 in parallel, on the same three accounts, same
category, same country, which rules out a change of legal name where one would
stop as the other starts - but it is evidence, not proof.

So this tool returns candidate groups with the evidence for each, and the caller
decides. That is not caution for its own sake. While writing the expected answers
by hand, a normalisation rule of exactly this kind grouped three of the four:
stripping "LOG" from NORDWIND LOG. left NORDWIND, which no longer matched
NORDWIND LOGISTICS. Nothing raised. It was caught because the group totalled
3.09M when the four variants sum to 4.09M.

A silent merger that is wrong produces a confident wrong answer, which is the
failure this exercise is built around. A proposal that is wrong is visible.

CATCH-ALL VENDORS are flagged separately. Sundry Supplier, Various Card
Settlement, Meridian Lodging Program and Aeroline Travel Desk are not companies;
they distort any "largest vendors" ranking and the caller has to decide whether
they belong in it.
"""

import re

# Company suffixes and punctuation noise. The list is short on purpose: the more
# aggressive it gets, the more unrelated names collapse into one.
SUFIJOS = r"\b(?:B\.?V|N\.?V|GMBH|LTD|LIMITED|LLC|L\.?L\.?C|INC|S\.?A|PLC|CORP|CORPORATION|CO)\b"
GENERICO = re.compile(r"\b(?:SUNDRY|VARIOUS|MISC|MISCELLANEOUS|OTHER|PROGRAM|DESK|SETTLEMENT)\b")


def _clave(nombre):
    """A name reduced to a comparison key. Never shown to anyone."""
    s = nombre.upper()
    # Dotted initials are joined BEFORE the rest of the punctuation is touched. The
    # other way round, "B.V." became "B V" and the suffix pattern - which looks for BV
    # unbroken - stopped recognising it: the key came out NORDWIND LOGISTICS B V and no
    # longer matched NORDWIND LOGISTICS. Second failure of this same family in one day,
    # and neither raised anything.
    s = re.sub(r"\b([A-Z])\.\s*(?=[A-Z]\b|[A-Z]\.)", r"\1", s)
    s = re.sub(r"[.,&/()-]", " ", s)
    s = re.sub(SUFIJOS, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Abbreviations: LOG. for LOGISTICS, LOGISTIK for LOGISTICS. Applied last, over the
    # already-cleaned string, so as not to leave the loose token that broke the first
    # attempt - there, stripping LOG left NORDWIND, which did not match NORDWIND
    # LOGISTICS.
    s = re.sub(r"\bLOGISTI\w*\b", "LOGISTICS", s)
    s = re.sub(r"\bLOG\b", "LOGISTICS", s)
    s = re.sub(r"\bTECH\w*\b", "TECHNICAL", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_vendors(con):
    """Candidate vendor groups, with the evidence for each. Nothing is merged."""
    sql = """
    SELECT v.vendor_id, v.vendor_name, v.category, v.country,
           COUNT(g.txn_id), MIN(g.accrual_date), MAX(g.accrual_date),
           GROUP_CONCAT(DISTINCT g.account_code)
      FROM vendors v LEFT JOIN gl_transactions g ON g.vendor_id = v.vendor_id
     GROUP BY v.vendor_id ORDER BY v.vendor_id
    """
    proveedores = [dict(zip(
        ("vendor_id", "vendor_name", "category", "country", "txns", "first", "last", "accounts"), r))
        for r in con.execute(sql)]

    por_clave = {}
    for p in proveedores:
        por_clave.setdefault(_clave(p["vendor_name"]), []).append(p)

    grupos, cajones = [], []
    for clave, miembros in sorted(por_clave.items()):
        if len(miembros) > 1:
            cuentas = {frozenset((m["accounts"] or "").split(",")) for m in miembros}
            solapan = all(m["first"] and m["last"] for m in miembros) and \
                max(m["first"] for m in miembros) <= min(m["last"] for m in miembros)
            grupos.append({
                "key": clave,
                "members": [{k: m[k] for k in ("vendor_id", "vendor_name", "txns", "first", "last")}
                            for m in miembros],
                "evidence": {
                    "same_category": len({m["category"] for m in miembros}) == 1,
                    "same_country": len({m["country"] for m in miembros}) == 1,
                    "same_accounts": len(cuentas) == 1,
                    "date_ranges_overlap": solapan,
                },
            })
    for p in proveedores:
        if GENERICO.search(p["vendor_name"].upper()):
            cajones.append({k: p[k] for k in ("vendor_id", "vendor_name", "txns")})

    notas = ["Groups are PROPOSED, never applied. vendors.csv carries no tax identifier, "
             "so nothing here proves two rows are one company - the evidence field says "
             "what supports each proposal and the caller decides.",
             "Name matching is fragile by nature and fails in both directions: it can "
             "miss a variant it does not recognise, and it can merge two unrelated "
             "companies whose names reduce to the same key. Neither failure raises "
             "anything, which is why nothing is merged automatically."]
    if grupos:
        n = sum(len(g["members"]) for g in grupos)
        notas.append(f"{len(grupos)} candidate group(s) covering {n} vendor records. Ranking "
                     f"vendors without deciding on these will split at least one company.")
    if cajones:
        notas.append(f"{len(cajones)} vendor record(s) look like catch-alls rather than "
                     f"companies: {', '.join(c['vendor_name'] for c in cajones)}. They distort "
                     f"any largest-vendor ranking; include or exclude them explicitly.")

    return {
        # `vendors` comes out whole because the ledger stores only vendor_id: without
        # this list any ranking prints codes instead of names, and nobody can check a
        # grouping they cannot read.
        "result": {"candidate_groups": grupos, "catch_all_vendors": cajones,
                   "vendor_count": len(proveedores),
                   "vendors": [{k: p[k] for k in ("vendor_id", "vendor_name", "txns")}
                               for p in proveedores]},
        "notes": notas,
        "sql": [(sql, ())],
    }
