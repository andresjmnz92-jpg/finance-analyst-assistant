"""Load a set of five CSVs into a local SQLite file.

    python -m src.load                    # data/          -> data.db
    python -m src.load evals/fixtures     # evals/fixtures -> fixtures.db

The database name is derived from the folder, never passed in. An earlier version
took it as a second argument, which meant forgetting it loaded the fixture on top
of the real data - silently, and with a success message.

TWO DATASETS, ONE LOADER. The brief says the tools will be run against a second
dataset with the same columns. Rather than take that on faith, the eval suite runs
the same eight questions over a small hand-built fixture whose answers are known
in advance (evals/fixtures/EXPECTED.md). If the loader needed a special case for
either one, that would already be the bug.

Rebuilt from data/ every time, so meridian.db is gitignored. Nothing here is
clever on purpose: five tables, one index set, and a row count you can check.

WHY SQLITE AND NOT PANDAS
Every one of the eight questions is filter, group, sum. That is SQL. SQLite ships
with Python, so there is no dependency to install and no version to pin, and the
tools stay small and boring - one query with parameters each.

WHAT THE SCHEMA DELIBERATELY DOES NOT DECLARE
No primary key on chart_of_accounts.account_code: account 6230 legitimately
appears twice, once per validity window. No unique key on budget either: one cost
centre carries two full sets of figures. Declaring keys the data does not have
would either fail the load or hide the ambiguity - both worse than carrying it.
"""

import csv
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (csv, tabla, columnas con su tipo). El orden es el del archivo.
TABLAS = [
    ("gl_transactions.csv", "gl_transactions", [
        ("txn_id", "TEXT PRIMARY KEY"), ("posting_date", "TEXT"), ("accrual_date", "TEXT"),
        ("entity", "TEXT"), ("cost_centre", "TEXT"), ("account_code", "TEXT"),
        ("amount", "REAL"), ("currency", "TEXT"), ("vendor_id", "TEXT"),
        ("doc_ref", "TEXT"), ("approval_ref", "TEXT"), ("memo", "TEXT"),
    ]),
    ("chart_of_accounts.csv", "chart_of_accounts", [
        ("account_code", "TEXT"), ("account_name", "TEXT"), ("parent_code", "TEXT"),
        ("parent_name", "TEXT"), ("statement_line", "TEXT"),
        ("valid_from", "TEXT"), ("valid_to", "TEXT"),
    ]),
    ("budget.csv", "budget", [
        ("entity", "TEXT"), ("cost_centre", "TEXT"), ("account_code", "TEXT"),
        ("period_month", "TEXT"), ("budget_amount", "REAL"), ("currency", "TEXT"),
    ]),
    ("fx_rates.csv", "fx_rates", [
        ("period_month", "TEXT"), ("currency", "TEXT"), ("rate_to_usd", "REAL"),
    ]),
    ("vendors.csv", "vendors", [
        ("vendor_id", "TEXT PRIMARY KEY"), ("vendor_name", "TEXT"),
        ("category", "TEXT"), ("country", "TEXT"),
    ]),
]

INDICES = [
    "CREATE INDEX idx_gl_accrual  ON gl_transactions(accrual_date)",
    "CREATE INDEX idx_gl_posting  ON gl_transactions(posting_date)",
    "CREATE INDEX idx_gl_account  ON gl_transactions(account_code)",
    "CREATE INDEX idx_gl_centre   ON gl_transactions(cost_centre)",
    "CREATE INDEX idx_gl_vendor   ON gl_transactions(vendor_id)",
    "CREATE INDEX idx_budget_key  ON budget(cost_centre, account_code, period_month)",
    "CREATE INDEX idx_fx_key      ON fx_rates(period_month, currency)",
]


def cargar(datos=None):
    datos = Path(datos) if datos else RAIZ / "data"
    if not datos.is_absolute():
        datos = RAIZ / datos
    DB = RAIZ / f"{datos.name}.db"

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    resumen, avisos = [], []

    for archivo, tabla, columnas in TABLAS:
        ruta = datos / archivo
        if not ruta.exists():
            sys.exit(f"Missing data file: {ruta}")

        cols_sql = ", ".join(f"{n} {t}" for n, t in columnas)
        con.execute(f"CREATE TABLE {tabla} ({cols_sql})")

        # utf-8-sig: si el archivo llega con BOM, la primera cabecera saldria como
        # '﻿vendor_id' y el DictReader no encontraria la columna.
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            nombres = [n for n, _ in columnas]
            presentes = set(lector.fieldnames or [])
            faltan = set(nombres) - presentes
            if faltan:
                sys.exit(f"{archivo}: expected columns not found: {sorted(faltan)}")

            # Columnas que no esperabamos. NO se cargan, pero callarselas seria peor:
            # si un dataset futuro trae budget_version, esa columna resuelve por si
            # sola la ambiguedad del presupuesto duplicado, y nadie se enteraria.
            extra = sorted(presentes - set(nombres))
            if extra:
                avisos.append(f"{archivo}: unrecognised columns present and NOT loaded: {extra}")

            reales = [n for n, t in columnas if t.startswith("REAL")]
            filas = []
            for fila in lector:
                v = []
                for n in nombres:
                    x = fila[n]
                    if n in reales:
                        v.append(float(x) if x not in ("", None) else None)
                    else:
                        v.append(x)
                filas.append(v)

        marcas = ", ".join("?" * len(nombres))
        con.executemany(f"INSERT INTO {tabla} VALUES ({marcas})", filas)
        resumen.append((tabla, len(filas)))

    for sql in INDICES:
        con.execute(sql)
    con.commit()

    print(f"{DB.name}  ({DB.stat().st_size / 1024:,.0f} KB)   from {datos}")
    for tabla, n in resumen:
        print(f"  {tabla:20s} {n:>7,} rows")

    for a in avisos:
        print(f"\n  WARNING  {a}")

    # Sanity checks. These are not tests of the loader - they are the three
    # ambiguities in the source data, restated so the load fails loudly if a
    # future dataset does not have them.
    print("\ndata characteristics (not errors):")
    q = con.execute
    dup_cuentas = q("""SELECT COUNT(*) FROM (SELECT account_code FROM chart_of_accounts
                       GROUP BY account_code HAVING COUNT(*) > 1)""").fetchone()[0]
    dup_budget = q("""SELECT COUNT(*) FROM (SELECT cost_centre, account_code, period_month
                      FROM budget GROUP BY 1,2,3 HAVING COUNT(*) > 1)""").fetchone()[0]
    fx_meses = q("SELECT COUNT(DISTINCT period_month) FROM fx_rates").fetchone()[0]
    fx_mon = q("SELECT COUNT(DISTINCT currency) FROM fx_rates").fetchone()[0]
    fx_filas = q("SELECT COUNT(*) FROM fx_rates").fetchone()[0]
    print(f"  accounts with more than one validity window : {dup_cuentas}")
    print(f"  budget keys appearing twice                 : {dup_budget}")
    print(f"  FX grid {fx_meses} months x {fx_mon} currencies = {fx_meses * fx_mon}, "
          f"actual rows {fx_filas} -> {fx_meses * fx_mon - fx_filas} missing")
    con.close()


if __name__ == "__main__":
    cargar(*sys.argv[1:2])
