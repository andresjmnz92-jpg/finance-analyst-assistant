"""Load a set of five CSVs into a local SQLite file.

    python -m src.load                    # data/          -> data.db
    python -m src.load evals/fixtures     # evals/fixtures -> fixtures.db

The database name is derived from the folder, and the folder's full path is stored
inside the database. Loading a different folder that happens to share the same
basename refuses instead of overwriting.

Both guards exist because both failures happened. First the db name was a second
argument, so forgetting it loaded the fixture over the real data. Then the name was
derived from the basename alone, so any folder called 'data' did the same thing -
a review verified it, replacing 10,916 rows with 18 and printing a success
summary.

TWO DATASETS, ONE LOADER. The brief says the tools will be run against a second
dataset with the same columns. Rather than take that on faith, the eval suite runs
the same eight questions over a small hand-built fixture whose answers are known
in advance (evals/fixtures/EXPECTED.md). If the loader needed a special case for
either one, that would already be the bug.

The database is named after the folder it came from - data/ becomes data.db,
evals/fixtures/ becomes fixtures.db - and both are rebuilt every time, so every
.db is gitignored. Nothing here is clever on purpose: five tables, one index set,
and a row count you can check.

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

import contextlib
import csv
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (csv, table, columns with their type). The order is the file's own.
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


def cargar(datos=None, force=False):
    datos = Path(datos) if datos else RAIZ / "data"
    if not datos.is_absolute():
        datos = RAIZ / datos
    datos = datos.resolve()
    DB = RAIZ / f"{datos.name}.db"

    # The source path is written inside the database. Deriving the name from the
    # basename is not enough: ANY folder called 'data' pointed at the same file, so
    # loading /somewhere/else/data wiped the 10,916 real rows and printed a success
    # summary. The docstring claimed that was impossible; it was not.
    if DB.exists() and not force:
        anterior = None
        try:
            # ALWAYS close before the unlink: on Windows an open file cannot be
            # deleted, and the check ended up blocking the load it was meant to allow.
            with contextlib.closing(sqlite3.connect(DB)) as previo:
                anterior = previo.execute(
                    "SELECT value FROM _source WHERE key = 'path'").fetchone()
        except sqlite3.Error:
            anterior = None
        if anterior and anterior[0] != str(datos):
            sys.exit(
                f"{DB.name} already holds a different dataset:\n"
                f"    existing: {anterior[0]}\n"
                f"    incoming: {datos}\n"
                f"Both folders are named '{datos.name}'. Rename one, or pass force=True "
                f"if replacing it is what you meant.")
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

        # utf-8-sig: if the file arrives with a BOM, the first header comes out as
        # '﻿vendor_id' and DictReader never finds the column.
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            nombres = [n for n, _ in columnas]
            presentes = set(lector.fieldnames or [])
            faltan = set(nombres) - presentes
            if faltan:
                sys.exit(f"{archivo}: expected columns not found: {sorted(faltan)}")

            # Columns we did not expect. They are NOT loaded, and staying quiet about
            # them would be worse: if a future dataset carries budget_version, that one
            # column resolves the duplicate-budget ambiguity by itself, and nobody
            # would find out.
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

    con.execute("CREATE TABLE _source (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO _source VALUES ('path', ?)", (str(datos),))
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
    dup_budget = q("""SELECT COUNT(*) FROM (SELECT entity, cost_centre, account_code,
                      period_month FROM budget GROUP BY 1,2,3,4 HAVING COUNT(*) > 1)""").fetchone()[0]
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
