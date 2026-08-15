"""resolve_accounts - expand a rollup into the leaf accounts underneath it.

WHY THIS IS NOT A ONE-LINE LOOKUP

Meridian's chart of accounts is three levels deep and carries validity windows:

    6210 Airfare  ->  6200 Travel & Entertainment  ->  6000 Operating Expenses
    6230 Meals    ->  6200 Travel & Entertainment       until 2024-06-30
    6230 Meals    ->  6700 Marketing                    from  2024-07-01

Three consequences, and each one is a wrong answer waiting to happen:

1. Asking for "operating expenses" means climbing two levels, not one. Anything
   that only reads parent_code once misses every leaf.

2. The same account code means different things on different dates. Joining the
   ledger to this table without a date filter matches BOTH rows for 6230 and
   double-counts every meals transaction ever booked.

3. The table mixes leaves with rollup nodes - 24 leaves and 9 nodes in Meridian.
   Summing every row that comes back triples the total, because the parents
   contain their children.

There is no column marking which rows are leaves. A leaf is defined here as an
account that is nobody's parent, which is a derived fact, not a stated one.
"""


def resolve_accounts(con, root, as_of):
    """Leaf accounts under `root`, as the hierarchy stood on `as_of` (YYYY-MM-DD).

    Rollup nodes are excluded from `leaves` and listed separately, so a caller can
    see the shape it walked without being able to sum them by accident.
    """
    sql = """
    WITH RECURSIVE tree(code) AS (
        SELECT account_code FROM chart_of_accounts
         WHERE account_code = ? AND ? BETWEEN valid_from AND valid_to
      UNION
        SELECT c.account_code FROM chart_of_accounts c JOIN tree t ON c.parent_code = t.code
         WHERE ? BETWEEN c.valid_from AND c.valid_to
    )
    SELECT DISTINCT code FROM tree
    """
    bajo = {r[0] for r in con.execute(sql, (root, as_of, as_of))} - {root}

    padres = {r[0] for r in con.execute(
        "SELECT DISTINCT parent_code FROM chart_of_accounts WHERE parent_code <> ''")}
    hojas = sorted(c for c in bajo if c not in padres)
    nodos = sorted(c for c in bajo if c in padres)

    notas = []
    if not bajo:
        notas.append(f"'{root}' resolved to nothing on {as_of}. Either it is not an "
                     f"account code, or it was not in force on that date.")

    # Una cuenta con mas de una ventana significa que esta respuesta CAMBIA con la
    # fecha. Quien pregunte por un periodo entero no puede usar una sola resolucion.
    movidas = con.execute("""
        SELECT account_code, COUNT(*) FROM chart_of_accounts
         GROUP BY account_code HAVING COUNT(*) > 1""").fetchall()
    afectadas = [c for c, _ in movidas if c in bajo or c in {root}]
    if movidas:
        detalle = ", ".join(c for c, _ in movidas)
        aviso = (f"{len(movidas)} account(s) have more than one validity window: {detalle}. "
                 f"This answer is correct for {as_of} only.")
        if afectadas:
            aviso += (f" {', '.join(afectadas)} is inside this rollup, so a query spanning a "
                      f"period must resolve per transaction date, not once for the period.")
        notas.append(aviso)

    return {
        "result": {"root": root, "as_of": as_of, "leaves": hojas, "rollup_nodes": nodos},
        "notes": notas,
        "sql": [(sql, (root, as_of, as_of))],
    }
