"""query_ledger - filter and group the general ledger. Every question ends here.

TWO DECISIONS THAT ARE NOT DETAILS

Which date. Every row carries posting_date AND accrual_date, and no document in
the pack says which one defines a period. They disagree: posting_date runs to
2025-01-14 while accrual_date stops at 2024-12-31, and all 60 rows posted in 2025
accrue in 2024 - they are the year-end close. A 2024 report by posting date loses
those 60. The default here is accrual_date, because accrual is what FP&A reports
on, and the choice is returned in the answer so it can be challenged.

No conversion. This tool returns amounts in the currency they were booked in,
grouped by currency, and never sums across currencies. Converting is
convert_currency's job, and keeping them apart is what stops a missing rate from
disappearing inside a subtotal.
"""

CAMPOS_FECHA = ("accrual_date", "posting_date")

# Solo estas columnas pueden agrupar o filtrar. No es paranoia de inyeccion - los
# valores van parametrizados igual - es que una lista cerrada convierte un nombre
# de columna mal escrito en un error inmediato en vez de en una consulta vacia.
DIMENSIONES = ("entity", "cost_centre", "account_code", "vendor_id", "currency")

DATE_BASIS = (
    "Period assigned by {campo}. The pack does not say which date defines a period, "
    "and the two disagree: posting_date extends into 2025-01 while accrual_date "
    "stops at 2024-12-31."
)


def query_ledger(con, date_from=None, date_to=None, accounts=None, group_by=(),
                 date_field="accrual_date", **filtros):
    """Sum the ledger between two dates, grouped by whatever dimensions you pass.

    accounts: an explicit list of leaf codes, normally from resolve_accounts.
    group_by / filtros: only names in DIMENSIONES.

    Returns one row per group PER CURRENCY, always. Feed them to convert_currency
    to get a single figure - and to be told what could not be converted.
    """
    if date_field not in CAMPOS_FECHA:
        raise ValueError(f"date_field must be one of {CAMPOS_FECHA}")
    for d in tuple(group_by) + tuple(filtros):
        if d not in DIMENSIONES:
            raise ValueError(f"unknown dimension '{d}'; allowed: {DIMENSIONES}")

    donde, params = [], []
    if date_from:
        donde.append(f"{date_field} >= ?"); params.append(date_from)
    if date_to:
        donde.append(f"{date_field} <= ?"); params.append(date_to)
    if accounts is not None:
        if not accounts:
            # Lista vacia: la respuesta honesta es cero filas, no todas las filas.
            donde.append("1 = 0")
        else:
            donde.append(f"account_code IN ({','.join('?' * len(accounts))})")
            params += list(accounts)
    for col, val in filtros.items():
        valores = val if isinstance(val, (list, tuple, set)) else [val]
        donde.append(f"{col} IN ({','.join('?' * len(valores))})")
        params += list(valores)

    # currency y el mes SIEMPRE salen: son lo que convert_currency necesita para
    # buscar la tasa, y sin el mes no se puede saber cual falta.
    grupos = list(dict.fromkeys(tuple(group_by) + ("currency",)))
    seleccion = grupos + [f"substr({date_field},1,7) AS period_month"]
    sql = (f"SELECT {', '.join(seleccion)}, ROUND(SUM(amount),2) AS amount, COUNT(*) AS rows "
           f"FROM gl_transactions "
           + (f"WHERE {' AND '.join(donde)} " if donde else "")
           + f"GROUP BY {', '.join(grupos + ['period_month'])} "
           f"ORDER BY {', '.join(grupos + ['period_month'])}")

    cols = grupos + ["period_month", "amount", "rows"]
    filas = [dict(zip(cols, r)) for r in con.execute(sql, params)]

    notas = [DATE_BASIS.format(campo=date_field)]
    monedas = {f["currency"] for f in filas}
    if len(monedas) > 1:
        notas.append(f"Rows span {len(monedas)} currencies ({', '.join(sorted(monedas))}) "
                     f"and are NOT summed here. Pass them through convert_currency.")
    if not filas:
        notas.append("No rows matched. Check the period and the account list before "
                     "reporting this as a zero.")

    return {
        "result": {"rows": filas, "row_count": sum(f["rows"] for f in filas),
                   "date_field": date_field},
        "notes": notas,
        "sql": [(sql, tuple(params))],
    }
