"""The executor: it runs a plan and fills in the trace as it goes.

    python -m src.agent.run consolidated_spend

No model is involved here, and that is the point. The brief asks for tools that
are "real computation, testable without the model", so every plan runs by name
first. What the model adds later is reading the question to pick the name, and
writing the prose - not the arithmetic.

WHY A PLAN IS A FUNCTION AND NOT DATA

plans.py declares a plan as a list of tool names. That list cannot be executed:
it says which tools, never with what arguments, and never how one result feeds
the next. Two ways to close that gap:

  a) keep plans as data and write an interpreter for argument templates
     ("accounts": "$1.leaves"). That is inventing a small language, and a bug
     inside an interpreter is invisible from the outside.
  b) write each plan as a function - three calls in plain Python, read top to
     bottom.

(b), for the least code and the most legible path. plans.py keeps the contract -
the question and what the answer must declare - and the function is the path.

THE COST OF (b), AND WHAT PAYS IT
A list of tool names sitting beside a function that calls something else is one
more document that lies, which is the failure this repository keeps finding in
itself. So the declared list is not documentation: _comprobar_ruta compares it
against the tools the trace actually recorded, and raises when they disagree.

WHERE THE DOCUMENTS COME FROM
Not from a path passed in by hand, but from the folder recorded inside the
database by the loader. A tool that reads a policy from one folder while the
numbers come from another produces an answer that cites a file that was never
loaded - which already happened here once, in the tools' notes.
"""

import sqlite3
import sys
import time
from pathlib import Path

from src.agent.plans import PLANS
from src.agent.trace import Trace
from src.tools.accounts import resolve_accounts
from src.tools.fx import convert_currency
from src.tools.ledger import CAMPOS_FECHA, query_ledger

RAIZ = Path(__file__).resolve().parent.parent.parent

# El ultimo dia de cada trimestre. Ninguno cae en febrero, asi que no hace falta
# calendario: 31/30/30/31 es toda la tabla.
FIN_TRIMESTRE = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


class Ejecucion:
    """The pen the plans write with: it calls a tool and records the call.

    Tools are passed `con` explicitly rather than having it injected, because
    read_document takes a folder and no connection at all. Injecting whatever
    each tool happens to need is the kind of cleverness that fails silently.
    """

    def __init__(self, con, datos_dir, trace):
        self.con = con
        self.datos_dir = datos_dir
        self.trace = trace

    def usar(self, herramienta, **args):
        inicio = time.time()
        salida = herramienta(**args)
        self.trace.step(herramienta.__name__, args, salida, time.time() - inicio)
        return salida["result"]


def _anios_con_datos(con, campo, desde_mes, hasta_mes):
    """Which years actually carry rows in that stretch of months. MEASURED.

    The question says "Q3" and never says which one. Answering for the year the
    author happened to have in mind is the confident wrong answer; the honest
    move is to state which years were on offer and which was taken.
    """
    if campo not in CAMPOS_FECHA:
        raise ValueError(f"date_field must be one of {CAMPOS_FECHA}")
    return [r[0] for r in con.execute(
        f"SELECT DISTINCT substr({campo},1,4) FROM gl_transactions "
        f"WHERE substr({campo},6,2) BETWEEN ? AND ? ORDER BY 1", (desde_mes, hasta_mes))]


def _trimestre(eje, year, quarter, date_field):
    """Resolve "Q3" into real dates, and say out loud which year was taken.

    Shared by every plan that takes a quarter, so the sentence declaring the
    choice is written once. Two plans wording the same decision differently is
    how a caveat quietly stops matching what the code did.
    """
    quarter = int(quarter)
    desde_mes, hasta_mes = f"{(quarter - 1) * 3 + 1:02d}", f"{quarter * 3:02d}"
    anios = _anios_con_datos(eje.con, date_field, desde_mes, hasta_mes)
    if year is None and anios:
        year = anios[-1]
        if len(anios) > 1:
            eje.trace.decision(
                f"The question does not say which year. This file holds Q{quarter} rows in "
                f"{', '.join(anios)}; the most recent ({year}) was used, and the same plan "
                f"answers any of them.")
    if not anios:
        eje.trace.decision(f"No rows fall in Q{quarter} of any year in this file.")
        return None, None, None
    return year, f"{year}-{desde_mes}-01", f"{year}-{FIN_TRIMESTRE[quarter]}"


def _ventanas(con, desde, hasta):
    """Cut a period wherever the chart of accounts changes shape.

    An account is not a fixed thing. Meridian's 6230 Meals sits under Travel &
    Entertainment until 2024-06-30 and under Marketing from 2024-07-01, so "the
    leaf accounts under Travel" is a different set on either side of that date.
    Resolving once for a whole year and querying with that one list is wrong in
    both directions: resolve in January and July's meals get counted as travel,
    resolve in December and the first half's meals disappear.

    So the period is split at every boundary, and each piece is resolved and
    queried with the hierarchy that was in force during it. A year with no
    boundary comes back as one window and costs one extra query - nothing.

    Boundaries are taken from the whole chart, not just this root, which can
    split more often than strictly needed. That is deliberate: an extra window
    resolves to the same accounts and changes no figure, while a missed one is a
    wrong number. Cheap in the safe direction.

    `date('9999-12-31','+1 day')` is NULL in SQLite - past the end of its
    calendar - so open-ended windows produce no boundary rather than a spurious
    one. That is checked by the comparison, not assumed.
    """
    cortes = sorted(r[0] for r in con.execute(
        "SELECT DISTINCT valid_from FROM chart_of_accounts "
        " WHERE valid_from > ? AND valid_from <= ? "
        "UNION SELECT DISTINCT date(valid_to,'+1 day') FROM chart_of_accounts "
        " WHERE date(valid_to,'+1 day') > ? AND date(valid_to,'+1 day') <= ?",
        (desde, hasta, desde, hasta)))
    inicios = [desde] + cortes
    ventanas = []
    for i, ini in enumerate(inicios):
        if i + 1 < len(inicios):
            fin = con.execute("SELECT date(?, '-1 day')", (inicios[i + 1],)).fetchone()[0]
        else:
            fin = hasta
        ventanas.append((ini, fin))
    return ventanas


def _sumar_periodo(eje, root, desde, hasta, date_field):
    """Resolve and query a period window by window. Returns the ledger rows."""
    filas, resoluciones = [], []
    for ini, fin in _ventanas(eje.con, desde, hasta):
        cuentas = eje.usar(resolve_accounts, con=eje.con, root=root, as_of=ini)
        if not cuentas["leaves"]:
            return None, resoluciones
        resoluciones.append((ini, fin, cuentas["leaves"]))
        trozo = eje.usar(query_ledger, con=eje.con, date_from=ini, date_to=fin,
                         accounts=cuentas["leaves"], date_field=date_field)
        filas += trozo["rows"]
    return filas, resoluciones


# -- los planes ------------------------------------------------------------------

def opex_by_cost_centre(eje, root, year=None, quarter=2, date_field="accrual_date"):
    """Spend under a rollup for a quarter, split by cost centre.

    `root` has NO default, and that is the design. Writing 6000 here would be the
    one thing the brief names - "don't hardcode anything to this one" - and an
    account code is a value, not a column. The caller supplies it: the model at
    runtime after reading list_account_names, or a test by hand.

    Nothing validates the model's choice here because nothing needs to.
    resolve_accounts already answers with an empty leaf list and says which case
    it is - the code does not exist, or it existed but was not in force on this
    date. All this plan does is refuse instead of reporting the zero that follows.
    """
    year, desde, hasta = _trimestre(eje, year, quarter, date_field)
    if year is None:
        return {"status": "REFUSED", "reason": f"no rows in Q{quarter} of any year"}

    # Resuelto al CIERRE del trimestre, y esa fecha viaja en la respuesta. Si alguna
    # cuenta cambia de padre dentro del periodo la propia herramienta lo dice - no
    # se afirma aqui que no pase, porque eso seria un dato de Meridian.
    cuentas = eje.usar(resolve_accounts, con=eje.con, root=root, as_of=hasta)
    if not cuentas["leaves"]:
        return {"status": "REFUSED", "root": root, "as_of": hasta,
                "reason": "the root resolved to no posting accounts; see the note"}

    mayor = eje.usar(query_ledger, con=eje.con, date_from=desde, date_to=hasta,
                     accounts=cuentas["leaves"], group_by=("cost_centre",),
                     date_field=date_field)
    fx = eje.usar(convert_currency, con=eje.con, rows=mayor["rows"])

    por_centro = {}
    for f in fx["rows"]:
        por_centro[f["cost_centre"]] = round(por_centro.get(f["cost_centre"], 0.0)
                                             + f["amount"], 2)
    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "period": f"Q{quarter} {year}",
        "root": root, "leaf_accounts": len(cuentas["leaves"]),
        "by_cost_centre": dict(sorted(por_centro.items(), key=lambda x: -x[1])),
        "total": fx["total"], "currency": fx["currency"],
        "ledger_rows": mayor["row_count"],
        "excluded": fx["unconverted"],
    }


def spend_comparison(eje, root, year_a=None, year_b=None, date_field="accrual_date"):
    """One category across two years, resolved per validity window inside each.

    THE NUMBER THIS PLAN EXISTS TO GET RIGHT
    In the fixture, one 200.00 transaction sits on 6230 dated 2024-07-10 - nine
    days after that account left Travel for Marketing. Included, 2024 reads
    1,200.00 and the answer is "travel doubled". Excluded, it reads 1,000.00.
    Both look like answers; only one is one.
    """
    anios = [r[0] for r in eje.con.execute(
        f"SELECT DISTINCT substr({date_field},1,4) FROM gl_transactions ORDER BY 1")
        ] if date_field in CAMPOS_FECHA else []
    if len(anios) < 2 and not (year_a and year_b):
        eje.trace.decision(f"This file holds {len(anios)} year(s) of ledger data "
                           f"({', '.join(anios) or 'none'}); a comparison needs two.")
        return {"status": "REFUSED", "reason": "fewer than two years in the ledger"}
    year_b = year_b or anios[-1]
    year_a = year_a or anios[-2]
    if not (year_a and year_b):
        eje.trace.decision("The question names no years and the ledger offers none to pick.")
        return {"status": "REFUSED", "reason": "no years available"}
    eje.trace.decision(
        f"Compared {year_b} against {year_a}. This file holds {', '.join(anios)}, and the "
        f"two most recent were taken; any pair can be asked for instead.")

    por_anio, cortes = {}, {}
    todas = []
    for anio in (year_a, year_b):
        filas, resoluciones = _sumar_periodo(eje, root, f"{anio}-01-01", f"{anio}-12-31",
                                             date_field)
        if filas is None:
            return {"status": "REFUSED", "root": root, "year": anio,
                    "reason": "the root resolved to no posting accounts; see the note"}
        cortes[anio] = [{"from": i, "to": f, "accounts": len(h)} for i, f, h in resoluciones]
        if len(resoluciones) > 1:
            eje.trace.decision(
                f"{anio} was split into {len(resoluciones)} window(s) at "
                f"{', '.join(r[0] for r in resoluciones[1:])} because the chart of accounts "
                f"changes there. Each window was resolved with the hierarchy in force during "
                f"it, so a transaction counts under the parent it had ON ITS OWN DATE.")
        todas += filas
        por_anio[anio] = filas

    fx = eje.usar(convert_currency, con=eje.con, rows=todas)
    total = {a: 0.0 for a in (year_a, year_b)}
    for f in fx["rows"]:
        total[f["period_month"][:4]] = round(total[f["period_month"][:4]] + f["amount"], 2)

    diferencia = round(total[year_b] - total[year_a], 2)
    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "root": root, "currency": fx["currency"],
        year_a: total[year_a], year_b: total[year_b],
        "difference": diferencia,
        "percent": round(diferencia / total[year_a] * 100, 1) if total[year_a] else None,
        "windows": cortes,
        "ledger_rows": {a: sum(f["rows"] for f in filas) for a, filas in por_anio.items()},
        "excluded": fx["unconverted"],
    }


def consolidated_spend(eje, year=None, quarter=3, date_field="accrual_date"):
    """Total spend for a quarter in USD, and what could not be converted.

    Two tools, and they are kept apart on purpose: query_ledger never sums across
    currencies, so a missing rate cannot vanish inside a subtotal. It comes back
    as `unconverted`, which is what makes this answer PARTIAL rather than wrong.
    """
    year, desde, hasta = _trimestre(eje, year, quarter, date_field)
    if year is None:
        return {"status": "REFUSED", "period": f"Q{quarter}", "reason": "no rows in that quarter"}

    mayor = eje.usar(query_ledger, con=eje.con, date_from=desde, date_to=hasta,
                     date_field=date_field)
    fx = eje.usar(convert_currency, con=eje.con, rows=mayor["rows"])

    return {
        # No se deduce del texto ni se decide de memoria: `unconverted` es una
        # medicion de la herramienta. Vacia significa que nada se quedo fuera.
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "period": f"Q{quarter} {year}",
        "total": fx["total"],
        "currency": fx["currency"],
        "ledger_rows": mayor["row_count"],
        "rows_converted": fx["rows_converted"],
        "excluded": fx["unconverted"],
    }


RUTINAS = {
    "opex_by_cost_centre": opex_by_cost_centre,
    "spend_comparison": spend_comparison,
    "consolidated_spend": consolidated_spend,
}


# -- el ejecutor -----------------------------------------------------------------

def _comprobar_ruta(nombre, trace):
    """plans.py claims a sequence of tools. Here that claim is checked.

    It raises instead of noting, because the two are never both right: either the
    plan changed and the declaration was not updated, or the declaration was
    wrong from the start. Both are bugs in this repository, and neither can
    happen to somebody else's data.

    WHAT IT CHECKS IS THE SET, AND IT TOOK TWO CORRECTIONS TO GET THERE.
    It began by demanding the exact sequence, and fired on a correct refusal:
    asked for a root that does not exist, the plan stopped after one tool where
    three were declared. Requiring a prefix fixed that and then broke on
    spend_comparison, where the DATA decides the length - a year whose chart of
    accounts changes mid-year is resolved and queried once per window, so the
    sequence is resolve, query, resolve, query, convert.

    A declaration cannot fix a length the data chooses. What it can fix is which
    tools are involved, and that is the part worth guarding: a plan reaching for
    a tool nobody declared, or quietly skipping one. Order was never the claim
    that mattered - the trace shows the real order, in full, every run.
    """
    declarado = list(PLANS[nombre]["tools"])
    real = [p["tool"] for p in trace.steps]
    intrusos = sorted(set(real) - set(declarado))
    if intrusos:
        raise AssertionError(
            f"{nombre}: the run called {intrusos}, which plans.py does not declare. "
            f"One of the two is wrong; do not relax this check.")
    faltan = [t for t in dict.fromkeys(declarado) if t not in real]
    if trace.status != "REFUSED" and faltan:
        raise AssertionError(
            f"{nombre}: the run never called {faltan} but did not refuse either, while "
            f"plans.py declares {declarado}. A short path with a confident answer is the bug.")


def run(nombre, con, datos_dir=None, dataset=None, **params):
    """Run one plan by name. Returns the Trace, with no answer written yet."""
    if nombre not in RUTINAS:
        falta = sorted(set(PLANS) - set(RUTINAS))
        raise KeyError(f"no routine for '{nombre}'. Available: {sorted(RUTINAS)}. "
                       f"Declared in plans.py but not built yet: {falta}")

    trace = Trace(PLANS[nombre]["question"], dataset=dataset, con=con)
    trace.plan = nombre
    if datos_dir is None and trace.source and trace.source["path"]:
        datos_dir = Path(trace.source["path"])

    hallazgos = RUTINAS[nombre](Ejecucion(con, datos_dir, trace), **params)
    trace.findings = {k: v for k, v in hallazgos.items() if k != "status"}
    trace.finish(None, hallazgos["status"])
    _comprobar_ruta(nombre, trace)
    return trace


if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else "consolidated_spend"
    db = RAIZ / (sys.argv[2] if len(sys.argv) > 2 else "data.db")
    if not db.exists():
        sys.exit(f"{db.name} not found. Run: python -m src.load")
    # Todo llega como texto y se queda como texto. Convertir '6000' a entero lo
    # haria dejar de casar contra una columna TEXT - cero filas y ni un aviso.
    params = dict(a.split("=", 1) for a in sys.argv[3:] if "=" in a)
    con = sqlite3.connect(db)
    print(run(nombre, con, dataset=db.name, **params).render())
    con.close()
