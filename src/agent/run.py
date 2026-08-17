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

import re
import sqlite3
import sys
import time
from pathlib import Path

from src.agent.plans import PLANS
from src.agent.trace import Trace
from src.tools.accounts import resolve_accounts
from src.tools.budget import query_budget
from src.tools.documents import read_document
from src.tools.duplicates import find_duplicate_payments
from src.tools.fx import convert_currency
from src.tools.ledger import CAMPOS_FECHA, query_ledger
from src.tools.vendors import normalize_vendors

RAIZ = Path(__file__).resolve().parent.parent.parent

# The last day of each quarter. None falls in February, so no calendar is needed:
# 31/30/30/31 is the whole table.
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


def _cuarto(quarter):
    """2, "2", "Q2" and "q2" are the same quarter. The model reads "Q2" in the
    question and writes "Q2" back, which is not a mistake - it is the interface
    asking for a number and being handed the word it was given."""
    return int(re.sub(r"[^0-9]", "", str(quarter)))


def _trimestre(eje, year, quarter, date_field):
    """Resolve "Q3" into real dates, and say out loud which year was taken.

    Shared by every plan that takes a quarter, so the sentence declaring the
    choice is written once. Two plans wording the same decision differently is
    how a caveat quietly stops matching what the code did.

    A YEAR THAT WAS GIVEN IS CHECKED AS HARD AS ONE THAT WAS PICKED.
    The first version only measured the years available in order to CHOOSE one,
    and skipped the check entirely when a year arrived as an argument. Asked for
    Q3 2099 it returned COMPLETE, total 0.00 - a year with no rows reading as a
    quarter with no spend. The model is what supplies that argument, having read
    it out of the question, so this is the likeliest way a wrong year ever
    arrives.
    """
    quarter = _cuarto(quarter)
    desde_mes, hasta_mes = f"{(quarter - 1) * 3 + 1:02d}", f"{quarter * 3:02d}"
    anios = _anios_con_datos(eje.con, date_field, desde_mes, hasta_mes)
    if not anios:
        eje.trace.decision(f"No rows fall in Q{quarter} of any year in this file.")
        return None, None, None
    if year is None:
        year = anios[-1]
        if len(anios) > 1:
            eje.trace.decision(
                f"The question does not say which year. This file holds Q{quarter} rows in "
                f"{', '.join(anios)}; the most recent ({year}) was used, and the same plan "
                f"answers any of them.")
    elif str(year) not in anios:
        eje.trace.decision(
            f"Q{quarter} {year} was asked for and this file has no rows in it. The years "
            f"with Q{quarter} data are {', '.join(anios)}. Answering zero would read as no "
            f"spend rather than no data.")
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


def _identidad(prov):
    """Turn normalize_vendors' output into two lookups: a name, and a group.

    The ledger stores vendor_id and nothing else, so any breakdown printed
    straight from it reads "V1021 202,994.59" - a code nobody can act on. And the
    same company appears under several codes, so a breakdown that does not group
    shows one vendor twice and calls them two.
    """
    nombre = {v["vendor_id"]: v["vendor_name"] for v in prov["vendors"]}
    grupo, cabeza = {}, {}
    for g in prov["candidate_groups"]:
        cabeza[g["key"]] = max(g["members"], key=lambda m: m["txns"])["vendor_name"]
        for m in g["members"]:
            grupo[m["vendor_id"]] = g["key"]
    return nombre, grupo, cabeza


def _sumar_periodo(eje, root, desde, hasta, date_field, group_by=()):
    """Resolve and query a period window by window. Returns the ledger rows.

    Every plan that sums a rollup over a period goes through here, and that is
    the point. opex_by_cost_centre resolved ONCE at the close of the quarter and
    justified it in a comment: "if an account changes parent inside the period
    the tool says so". Half true. resolve_accounts warns about multi-window
    accounts that are inside the rollup AS OF the date it was given, so an
    account that LEFT the rollup earlier in the period is not in that scope and
    never triggers the warning - its transactions from while it still belonged
    simply vanish from the total. Windows remove the whole class instead of
    warning about half of it.
    """
    filas, resoluciones = [], []
    for ini, fin in _ventanas(eje.con, desde, hasta):
        cuentas = eje.usar(resolve_accounts, con=eje.con, root=root, as_of=ini)
        if not cuentas["leaves"]:
            return None, resoluciones
        resoluciones.append((ini, fin, cuentas["leaves"]))
        trozo = eje.usar(query_ledger, con=eje.con, date_from=ini, date_to=fin,
                         accounts=cuentas["leaves"], group_by=group_by,
                         date_field=date_field)
        filas += trozo["rows"]
    return filas, resoluciones


# -- the plans -------------------------------------------------------------------

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

    The period is cut into windows by _sumar_periodo, same as spend_comparison.
    This plan used to resolve once at the close of the quarter, which is only safe
    while no account leaves the rollup mid-period - and nothing was checking that.
    """
    quarter = _cuarto(quarter)
    year, desde, hasta = _trimestre(eje, year, quarter, date_field)
    if year is None:
        return {"status": "REFUSED", "reason": f"no rows in Q{quarter} of that year"}

    filas, resoluciones = _sumar_periodo(eje, root, desde, hasta, date_field,
                                         group_by=("cost_centre",))
    if filas is None:
        return {"status": "REFUSED", "root": root,
                "reason": "the root resolved to no posting accounts; see the note"}
    if len(resoluciones) > 1:
        eje.trace.decision(
            f"Q{quarter} {year} was split into {len(resoluciones)} window(s) at "
            f"{', '.join(r[0] for r in resoluciones[1:])} because the chart of accounts "
            f"changes there, so each transaction counts under the parent it had on its "
            f"own date.")
    fx = eje.usar(convert_currency, con=eje.con, rows=filas)

    por_centro = {}
    for f in fx["rows"]:
        por_centro[f["cost_centre"]] = round(por_centro.get(f["cost_centre"], 0.0)
                                             + f["amount"], 2)
    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "period": f"Q{quarter} {year}",
        "root": root,
        "windows": [{"from": i, "to": f, "accounts": len(h)} for i, f, h in resoluciones],
        "by_cost_centre": dict(sorted(por_centro.items(), key=lambda x: -x[1])),
        "total": fx["total"], "currency": fx["currency"],
        "ledger_rows": sum(f["rows"] for f in filas),
        "excluded": fx["unconverted"],
    }


def spend_comparison(eje, root, year_a=None, year_b=None, date_field="accrual_date"):
    """One category across two years, resolved per validity window inside each.

    THE NUMBER THIS PLAN EXISTS TO GET RIGHT
    In the fixture, one 200.00 transaction sits on 6230 dated 2024-07-10 - nine
    days after that account left Travel for Marketing. Included, 2024 reads
    1,200.00 and the answer is "travel doubled". Excluded, it reads 1,000.00.
    Both look like answers; only one is one.

    THE YEARS ARE CHECKED AS HARD AS THE ACCOUNTS, AND THEY WERE NOT.
    _trimestre already refuses a year with no rows and says why; this plan never
    inherited that. Asked for 2099 against 2024 it answered "spend fell 100%" -
    a year with no rows summing to zero, and a zero reading as a measurement.
    Asked for 2024 against 2024 it added the same year to itself and reported a
    difference of 0.00 over double the real total. The model supplies both
    arguments, having read them out of the question.
    """
    anios = [r[0] for r in eje.con.execute(
        f"SELECT DISTINCT substr({date_field},1,4) FROM gl_transactions ORDER BY 1")
        ] if date_field in CAMPOS_FECHA else []
    # Recorded BEFORE the defaults fill them in: which years the caller actually named
    # is the difference between a year that was taken and one that was given, and the
    # decision below has to say which happened.
    pedidos = [str(a) for a in (year_a, year_b) if a is not None]
    if len(anios) < 2 and not (year_a and year_b):
        eje.trace.decision(f"This file holds {len(anios)} year(s) of ledger data "
                           f"({', '.join(anios) or 'none'}); a comparison needs two.")
        return {"status": "REFUSED", "reason": "fewer than two years in the ledger"}
    # SORTED, rather than trusting the order they arrive in. The router returned
    # year_a=2024 and year_b=2023, which flips the sign of the difference - and it was
    # not wrong: "a" and "b" mean nothing. Sorting removes the question instead of
    # answering it.
    year_b = year_b or anios[-1]
    year_a = year_a or anios[-2]
    year_a, year_b = sorted((str(year_a), str(year_b)))
    if not (year_a and year_b):
        eje.trace.decision("The question names no years and the ledger offers none to pick.")
        return {"status": "REFUSED", "reason": "no years available"}
    ausentes = [a for a in dict.fromkeys((year_a, year_b)) if a not in anios]
    if ausentes:
        eje.trace.decision(
            f"{', '.join(ausentes)} was asked for and this file has no ledger rows in it. The "
            f"years with data are {', '.join(anios) or 'none'}. Answering zero would read as no "
            f"spend rather than no data.")
        return {"status": "REFUSED", "root": root,
                "reason": f"no rows in {', '.join(ausentes)}"}
    if year_a == year_b:
        eje.trace.decision(
            f"{year_a} was given on both sides of the comparison. Summing it against itself "
            f"reports double the year's spend and a difference of zero, which is not a "
            f"measurement of anything. Ask for two different years.")
        return {"status": "REFUSED", "root": root,
                "reason": f"{year_a} was given twice, so there are fewer than two years to "
                          f"compare"}
    if len(pedidos) == 2:
        eje.trace.decision(
            f"Compared {year_b} against {year_a}, the two years the question named. This file "
            f"holds {', '.join(anios)}; no year was chosen here.")
    elif len(pedidos) == 1:
        eje.trace.decision(
            f"Compared {year_b} against {year_a}. Only {pedidos[0]} was asked for; "
            f"{year_a if year_b in pedidos else year_b} was taken from the years this file "
            f"holds ({', '.join(anios)}). Any pair can be asked for instead.")
    else:
        eje.trace.decision(
            f"Compared {year_b} against {year_a}. The question names no years; this file holds "
            f"{', '.join(anios)}, and the two most recent were taken. Any pair can be asked "
            f"for instead.")

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


def largest_vendors(eje, top=10, date_from=None, date_to=None, date_field="accrual_date"):
    """The largest vendors, ranked twice: grouped, and as the file stores them.

    WHY TWO RANKINGS AND WHICH ONE IS THE ANSWER

    Meridian lists Nordwind four times, one record per person who could not find
    the existing one. Split, its best variant does not reach the top ten; grouped,
    it is the LARGEST vendor in the company. The ranking is therefore not a
    sum, it is a decision - and the brief asks for an interface that "must show
    the work, not just the conclusion".

    So the grouped ranking is THE answer, and the ungrouped one is printed beside
    it so the reader can check the decision instead of trusting it. What is not
    done is handing over two lists and letting the analyst choose: something has
    to decide when the question is answered, and that something is this plan.

    WHAT THE RANKING IS SILENT ABOUT UNLESS IT SAYS SO
    Rows with no vendor - payroll - are not a vendor and cannot be ranked. In
    Meridian they are 45.8% of all spend. A top ten that does not say so is
    ordering half the money while sounding like it ordered all of it.
    """
    top = int(top)
    prov = eje.usar(normalize_vendors, con=eje.con)
    cajon = {c["vendor_id"] for c in prov["catch_all_vendors"]}

    if not (date_from or date_to):
        eje.trace.decision(
            "The question names no period, so the whole ledger was ranked. The date note on "
            "the query below states the range that actually covers.")

    mayor = eje.usar(query_ledger, con=eje.con, date_from=date_from, date_to=date_to,
                     group_by=("vendor_id",), date_field=date_field)
    fx = eje.usar(convert_currency, con=eje.con, rows=mayor["rows"])

    # convert_currency groups what it could not convert by month and currency, so the
    # vendor is lost. It is recovered here by checking which INPUT rows fall in a gap:
    # "Euro Air also has 100 EUR unconverted" is half of that vendor's answer.
    huecos = {(h["period_month"], h["currency"]) for h in fx["unconverted"]}
    pendiente = {}
    for f in mayor["rows"]:
        if (f["period_month"], f["currency"]) in huecos:
            d = pendiente.setdefault(f["vendor_id"], {})
            d[f["currency"]] = round(d.get(f["currency"], 0.0) + f["amount"], 2)

    por_id = {}
    for f in fx["rows"]:
        por_id[f["vendor_id"]] = round(por_id.get(f["vendor_id"], 0.0) + f["amount"], 2)
    total_todo = round(sum(por_id.values()), 2)
    sin_proveedor = por_id.pop("", 0.0)

    nombre, grupo, cabeza = _identidad(prov)

    def ordenar(agrupar):
        acumulado = {}
        for vid, usd in por_id.items():
            k = grupo.get(vid, vid) if agrupar else vid
            e = acumulado.setdefault(k, {"key": k, "vendor_ids": [], "usd": 0.0})
            e["vendor_ids"].append(vid)
            e["usd"] = round(e["usd"] + usd, 2)
        for e in acumulado.values():
            e["vendor"] = cabeza.get(e["key"], nombre.get(e["key"], e["key"]))
            e["catch_all"] = any(v in cajon for v in e["vendor_ids"])
            resto = {}
            for v in e["vendor_ids"]:
                for mon, imp in pendiente.get(v, {}).items():
                    resto[mon] = round(resto.get(mon, 0.0) + imp, 2)
            if resto:
                e["not_converted"] = resto
        return sorted(acumulado.values(), key=lambda x: -x["usd"])

    agrupado, suelto = ordenar(True), ordenar(False)
    puesto = {e["key"]: i for i, e in enumerate(suelto, 1)}

    cambios = []
    for g in prov["candidate_groups"]:
        ids = [m["vendor_id"] for m in g["members"]]
        arriba = min((puesto[v] for v in ids if v in puesto), default=None)
        ahora = next((i for i, e in enumerate(agrupado, 1) if e["key"] == g["key"]), None)
        cambios.append({
            "vendor": cabeza[g["key"]], "records": len(ids),
            "rank_grouped": ahora, "best_rank_split": arriba,
            "evidence": g["evidence"],
        })

    # TWO SENTENCES THE CODE HAS TO WRITE, AND WAS NOT WRITING.
    # The first version left both as raw keys in the findings, and an independent review
    # found the predictable result: the writer did not read them, and the answer ordered
    # half the money while sounding like it ordered all of it. The docstring above
    # already said why that was serious, before it happened.
    if total_todo:
        eje.trace.decision(
            f"{sin_proveedor / total_todo * 100:.0f}% of the spend in this period "
            f"({sin_proveedor:,.2f} USD) carries NO vendor at all - payroll and similar - and "
            f"cannot be ranked. This ranking orders the rest, not the total.")
    if cambios:
        eje.trace.decision(
            "The proposed vendor groupings WERE applied to this ranking. "
            + "; ".join(f"{c['vendor']} is {c['records']} records ranking #{c['rank_grouped']} "
                        f"together and #{c['best_rank_split']} at best apart" for c in cambios)
            + ". The tool proposes and does not merge; the decision to accept was taken here "
              "and the ungrouped ranking is reported beside it.")

    limpio = [dict(e) for e in agrupado[:top]]
    for e in limpio:
        e.pop("key", None)
    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "currency": fx["currency"],
        "top": limpio,
        "ungrouped_top": [{k: v for k, v in e.items() if k != "key"} for e in suelto[:top]],
        "grouping_changed": cambios,
        "vendors_ranked": len(agrupado),
        "unattributed": {"usd": sin_proveedor,
                         "share_of_spend": round(sin_proveedor / total_todo * 100, 1)
                         if total_todo else None},
        "excluded": fx["unconverted"],
    }


def budget_variance(eje, year=None, quarter=3, top=5, date_field="accrual_date"):
    """Worst cost centres against budget for a quarter, and what drives the worst.

    THREE THINGS HAVE TO SURVIVE THIS ANSWER, AND TWO OF THEM CHANGE IT

    1. The budget is duplicated. One centre carries two full sets of figures for
       the same twelve months with no version column, told apart only by their
       order in the file. So a deviation is not a number here, it is a RANGE, and
       reporting one figure without saying which set produced it is the confident
       wrong answer this exercise is built around.

    2. Actuals are in local currency and the budget is in USD, so a missing rate
       does not just shrink a total - it makes a centre look UNDER budget. In the
       fixture OPS-EU/6610 reads -100.00 and its real deviation is +100.00: the
       sign flips. That is not asserted here, it is bounded. The lowest rate on
       file for that currency is enough to prove the flip, and the bound is
       measured by convert_currency rather than assumed.

    3. Worst by value and worst by percent are different questions. Both are
       reported, because a small centre 400% over is a different problem from a
       large one 15% over, and the question does not say which it means.

    The driver is a second ledger query over the worst key alone. It consumes the
    first result and needs no second decision, which is why this stays a written
    path rather than something the model steers.
    """
    top = int(top)
    quarter = _cuarto(quarter)
    year, desde, hasta = _trimestre(eje, year, quarter, date_field)
    if year is None:
        return {"status": "REFUSED", "reason": f"no rows in Q{quarter} of any year"}

    mayor = eje.usar(query_ledger, con=eje.con, date_from=desde, date_to=hasta,
                     group_by=("entity", "cost_centre", "account_code"), date_field=date_field)
    fx = eje.usar(convert_currency, con=eje.con, rows=mayor["rows"])

    def clave(f):
        return (f["entity"], f["cost_centre"], f["account_code"])

    real, pendiente = {}, {}
    for f in fx["rows"]:
        real[clave(f)] = round(real.get(clave(f), 0.0) + f["amount"], 2)
    huecos = {(h["period_month"], h["currency"]) for h in fx["unconverted"]}
    for f in mayor["rows"]:
        if (f["period_month"], f["currency"]) in huecos:
            d = pendiente.setdefault(clave(f), {})
            d[f["currency"]] = round(d.get(f["currency"], 0.0) + f["amount"], 2)

    pres = eje.usar(query_budget, con=eje.con,
                    period_from=f"{desde[:7]}", period_to=f"{hasta[:7]}")
    plan = {}
    for b in pres["rows"]:
        k = (b["entity"], b["cost_centre"], b["account_code"])
        plan.setdefault(k, {})
        plan[k][b["version"]] = round(plan[k].get(b["version"], 0.0) + b["amount"], 2)

    minimo = {m: r[0] for m, r in fx["rate_range"].items()}
    comparacion = []
    for k in sorted(set(plan) | set(real)):
        faltante = pendiente.get(k, {})
        # NO LEDGER ROWS IS NOT "SPENT ZERO". real.get(k, 0.0) turned a centre that has a
        # budget and no rows at all into a -100% deviation, which is a measurement the data
        # never made. Rows that exist and could not be CONVERTED are a different case and
        # still count as zero here, because understated_by_at_least says what is missing.
        gastado = real.get(k, 0.0 if faltante else None)
        # A LOWER bound on what is missing: the lowest rate on file for that currency.
        # If the deviation already changes sign at the lowest rate, it changes at any
        # rate - and that can be stated without inventing the rate that does not exist.
        #
        # A currency that appears NOWHERE in fx_rates has no bound. It used to default
        # to 0.0, which reads as "nothing is missing" and could hide a real sign flip.
        # No rates, no bound, and that is said.
        sin_cota = sorted(m for m in faltante if m not in minimo)
        suelo = round(sum(imp * minimo[mon] for mon, imp in faltante.items()
                          if mon in minimo), 2)
        fila = {"entity": k[0], "cost_centre": k[1], "account_code": k[2],
                "actual": gastado, "budget": plan.get(k, {}), "deviation": {}}
        # No actuals, no deviation. An empty deviation keeps the centre out of both
        # rankings - the same door percent_undefined_zero_budget goes through - while the
        # budget it does carry is still published below.
        if gastado is None:
            fila["no_actuals"] = True
        for v, presupuestado in sorted(plan.get(k, {}).items()):
            if gastado is None:
                continue
            d = round(gastado - presupuestado, 2)
            fila["deviation"][v] = {
                "usd": d,
                "percent": round(d / presupuestado * 100, 1) if presupuestado else None}
            if faltante and d < 0 <= round(d + suelo, 2):
                fila["sign_flips"] = True
        # A zero budget with real spend: the percentage is not 0, it is undefined, and
        # ranking it as 0 drops the centre spending with no plan out of the list.
        if any(p == 0 for p in plan.get(k, {}).values()) and (gastado or 0) > 0:
            fila["percent_undefined_zero_budget"] = True
        if faltante:
            fila["not_converted"] = faltante
            fila["understated_by_at_least"] = suelo
            if sin_cota:
                fila["no_rate_at_all_for"] = sin_cota
        if not plan.get(k):
            fila["no_budget"] = True
        comparacion.append(fila)

    # WHAT DOES NOT PAIR UP IS SHOWN UNPAIRED, NEVER DROPPED. Both rankings need a
    # deviation, and a deviation needs both sides, so a centre that has only one of them
    # falls out of every list this plan prints. no_budget was already being computed and
    # nothing read it: the centre with the largest spend of the quarter left no trace in
    # the answer. These two lists are that trace, and they carry the figure that exists -
    # the spend for one, the plan for the other - because half a pair is still a fact.
    sin_presupuesto = [{"entity": c["entity"], "cost_centre": c["cost_centre"],
                        "account_code": c["account_code"], "actual": c["actual"]}
                       for c in comparacion if c.get("no_budget")]
    sin_gasto = [{"entity": c["entity"], "cost_centre": c["cost_centre"],
                  "account_code": c["account_code"], "budget": c["budget"]}
                 for c in comparacion if c.get("no_actuals")]

    def peores(metrica):
        con_pres = [c for c in comparacion if c["deviation"]]

        def puntua(c):
            if metrica == "percent" and c.get("percent_undefined_zero_budget"):
                return float("inf")
            return max((d[metrica] for d in c["deviation"].values() if d[metrica] is not None),
                       default=0)
        return sorted(con_pres, key=lambda c: -puntua(c))[:top]

    por_valor, por_pct = peores("usd"), peores("percent")
    if not por_valor:
        return {"status": "REFUSED", "period": f"Q{quarter} {year}",
                "reason": "no key has both actuals and a budget in this period; the budget "
                          "may not cover it"}

    # p always has ledger rows behind it: peores() only ranks rows with a deviation, and a
    # deviation now requires BOTH sides. So this breakdown cannot come back empty without
    # the first query being empty too. The unpaired centres are reported above instead -
    # breaking a centre down by vendor when the whole point is that it has no plan to
    # break against would answer a question nobody asked.
    p = por_valor[0]
    desglose = eje.usar(query_ledger, con=eje.con, date_from=desde, date_to=hasta,
                        entity=p["entity"], cost_centre=p["cost_centre"],
                        accounts=[p["account_code"]], group_by=("vendor_id",),
                        date_field=date_field)
    motor = eje.usar(convert_currency, con=eje.con, rows=desglose["rows"])
    # The breakdown was asked for in order to NAME who drove it, so it comes out with
    # names and with one company's records added together. Without this, Meridian prints
    # V1088 and V1042 as two vendors, and they are two records of Nordwind.
    prov = eje.usar(normalize_vendors, con=eje.con)
    nombre, grupo, cabeza = _identidad(prov)
    por_prov = {}
    for f in motor["rows"]:
        vid = f["vendor_id"]
        etiqueta = ("(no vendor)" if not vid else
                    cabeza.get(grupo.get(vid), nombre.get(vid, vid)))
        por_prov[etiqueta] = round(por_prov.get(etiqueta, 0.0) + f["amount"], 2)

    # Both lists are NAMED, because they are two different answers to the same question
    # and handing them over as two similar-looking arrays invites confusing them. An
    # independent review proved it: the writer presented 6110 as one of the worst "by
    # value and percent" when it is not in the percent list at all, and skipped 6630,
    # which is. It did not misread - it was given two identical-looking lists with
    # nothing in prose to separate them.
    def _nombrar(lista, metrica):
        return "; ".join(
            f"{c['cost_centre']}/{c['account_code']} "
            + ("(" + " to ".join(f"{d['usd']:+,.0f}" for d in c["deviation"].values()) + " USD)"
               if metrica == "usd" else
               "(" + " to ".join(f"{d['percent']:+.0f}%" for d in c["deviation"].values()
                                 if d["percent"] is not None) + ")")
            for c in lista[:3])

    eje.trace.decision(
        f"Worst by VALUE, in order: {_nombrar(por_valor, 'usd')}. "
        f"Worst by PERCENT, in order: {_nombrar(por_pct, 'percent')}. "
        f"They are different questions and the lists differ; a range is given per entry "
        f"because the budget exists twice and nothing says which set is current.")

    if sin_presupuesto or sin_gasto:
        eje.trace.decision(
            f"{len(sin_presupuesto)} centre/account pair(s) SPENT WITH NO BUDGET LINE and "
            f"{len(sin_gasto)} carry A BUDGET WITH NO ROWS. Neither can have a deviation, so "
            f"neither appears in the two rankings above - they are listed on their own so the "
            f"money is not lost between the lists. Spent with no budget: "
            + ("; ".join(f'{c["cost_centre"]}/{c["account_code"]} ({c["actual"]:,.2f} USD)'
                         for c in sin_presupuesto) or "none")
            + ". Budgeted with no spend: "
            + ("; ".join(f'{c["cost_centre"]}/{c["account_code"]} ('
                         + " to ".join(f"{b:,.2f}" for b in c["budget"].values())
                         + " USD)" for c in sin_gasto) or "none")
            + ". A budget with no rows is NOT spend of zero, and it is not reported as -100%.")

    volteados = [c for c in comparacion if c.get("sign_flips")]
    if volteados:
        eje.trace.decision(
            f"{len(volteados)} centre/account pair(s) read as UNDER budget only because rows "
            f"could not be converted: "
            + "; ".join(f'{c["cost_centre"]}/{c["account_code"]}' for c in volteados)
            + ". At the lowest rate on file for the missing currency the deviation is already "
              "positive, so the sign is wrong rather than the magnitude.")

    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "period": f"Q{quarter} {year}", "currency": fx["currency"],
        "worst_by_value": por_valor,
        "worst_by_percent": por_pct,
        "spend_with_no_budget": sin_presupuesto,
        "budget_with_no_spend": sin_gasto,
        "budget_versions": pres["versions"],
        "centres_with_two_sets": pres["centres_with_two_sets"],
        "driver": {"entity": p["entity"], "cost_centre": p["cost_centre"],
                   "account_code": p["account_code"],
                   "by_vendor": dict(sorted(por_prov.items(), key=lambda x: -x[1]))},
        "sign_flipped_by_missing_rates": [
            {k: c[k] for k in ("cost_centre", "account_code", "deviation",
                               "not_converted", "understated_by_at_least")}
            for c in volteados],
        "excluded": fx["unconverted"],
    }


# Two lists and not one. A field called employee_id WOULD be a denominator, so it
# belongs in the column scan; a sentence about "employee meals" is not, and with the
# wide list the memo's quote arrived buried under three paragraphs about per-diems.
DENOMINADOR_COLUMNA = ("fte", "full-time", "full time", "headcount", "head count", "employee")
DENOMINADOR_FRASE = ("fte", "full-time equivalent", "full time equivalent", "headcount",
                     "head count")


def cost_per_fte(eje, root, date_field="accrual_date"):
    """Headcount cost per FTE. It refuses, and the refusal is the answer.

    THE NUMERATOR EXISTS AND THE DENOMINATOR DOES NOT

    Payroll cost is in the ledger and is given. The number of FTEs is in none of
    the five files, so every quotient this question invites is invented. The
    tempting substitutes are all wrong and all plausible: distinct employees (no
    such column), row counts (a monthly payroll run is not a person), entity
    counts (three countries are not three people).

    WHY THE REFUSAL DOES NOT REST ON THE DOCUMENT ALONE
    Meridian's board memo says outright that headcount lives in the HR system and
    not in the finance ledger, and that sentence is quoted. But a refusal that
    depends on finding a sentence is a refusal that stops working the moment the
    wording changes. The structural argument is checked first and needs no
    document: no column in any loaded table holds a headcount, and a denominator
    that is not a column cannot be summed.

    Both are reported, because they fail differently. The schema check survives a
    rewrite of the memo; the memo explains WHY the column is missing, which is
    what a manager actually needs to hear before going to ask the People team.
    """
    columnas = {}
    for (tabla,) in eje.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'"):
        for fila in eje.con.execute(f"PRAGMA table_info({tabla})"):
            if any(p in fila[1].lower() for p in DENOMINADOR_COLUMNA):
                columnas.setdefault(tabla, []).append(fila[1])

    rango = eje.con.execute(
        f"SELECT MIN({date_field}), MAX({date_field}) FROM gl_transactions").fetchone()
    filas, resoluciones = _sumar_periodo(eje, root, rango[0], rango[1], date_field)
    if filas is None:
        return {"status": "REFUSED", "root": root,
                "reason": "the root resolved to no posting accounts; see the note"}
    coste = {}
    for f in filas:
        coste[f["currency"]] = round(coste.get(f["currency"], 0.0) + f["amount"], 2)

    # Documents are read whole and searched with whitespace normalised. A line-based
    # search already failed on this question: the sentence that decides it spans a line
    # break, and grep returned nothing.
    catalogo = eje.usar(read_document, datos_dir=eje.datos_dir)
    dicho = []
    for nombre in catalogo["documents"]:
        doc = eje.usar(read_document, datos_dir=eje.datos_dir, name=nombre)
        texto = re.sub(r"\s+", " ", doc["text"])
        for m in re.finditer(r"[^.]*\.", texto):
            frase = m.group(0).strip()
            if any(p in frase.lower() for p in DENOMINADOR_FRASE):
                dicho.append({"document": nombre, "sentence": frase})

    eje.trace.decision(
        "The denominator is absent. No column in any loaded table holds a headcount, an FTE "
        "count or an employee identifier"
        + (f" - the only near matches are {columnas}" if columnas else "")
        + ". A quotient built from distinct employees, row counts or entity counts would be "
          "invented: a monthly payroll run is not a person and three entities are not three "
          "people.")
    if dicho:
        eje.trace.decision(
            "The document pack says so as well: "
            + " ".join(f'{d["document"]}: "{d["sentence"]}"' for d in dicho))
    else:
        eje.trace.decision(
            "No document in this pack mentions headcount or FTE at all, so nothing explains "
            "where the figure does live. The refusal rests on the schema alone.")

    return {
        "status": "REFUSED",
        "reason": "the ledger holds the payroll cost but no headcount figure exists in this "
                  "dataset, so any cost per FTE would be invented",
        "root": root,
        "payroll_cost_by_currency": coste,
        "periods_resolved": [{"from": i, "to": f, "accounts": len(h)} for i, f, h in resoluciones],
        "ledger_rows": sum(f["rows"] for f in filas),
        "denominator_columns_found": columnas,
        "what_the_documents_say": dicho,
    }


def duplicate_payments(eje, date_from=None, date_to=None):
    """Payments that could be the same one made twice. Candidates, never verdicts.

    THE QUESTION IS "DID WE PAY ANYONE TWICE" AND THE HONEST ANSWER IS "HERE IS
    WHAT COULD BE, AND WHY NOBODY CAN TELL FROM THIS DATA"

    In the fixture, four of the five groups are false positives: two flights three
    months apart, two meals in different months, two identical invoices a year
    apart. Nothing in these columns separates them from the one planted duplicate.
    A tool that reported a single confident duplicate would have thrown away the
    four it could not judge, and would be wrong about the one it kept as often as
    not.

    RUN TWICE, BECAUSE THE VENDOR DECISION CHANGES THE ANSWER
    The same company under two spellings hides a duplicate from a vendor_id match.
    normalize_vendors proposes groups and refuses to apply them; this plan is the
    caller that decides, and it decides to apply them - a missed duplicate costs
    money and an extra candidate costs a reviewer five minutes. Both runs are
    reported so the decision can be checked rather than trusted.
    """
    prov = eje.usar(normalize_vendors, con=eje.con)
    suelto = eje.usar(find_duplicate_payments, con=eje.con,
                      date_from=date_from, date_to=date_to)
    agrupado = eje.usar(find_duplicate_payments, con=eje.con,
                        vendor_groups=prov["candidate_groups"],
                        date_from=date_from, date_to=date_to)

    eje.trace.decision(
        f"The proposed vendor groupings WERE applied before matching. Without them: "
        f"{suelto['group_count']} candidate group(s) covering {suelto['extra_rows']} extra "
        f"row(s). With them: {agrupado['group_count']} group(s) and "
        f"{agrupado['extra_rows']} extra row(s). Applying them can only widen the net, and "
        f"the ungrouped result is reported beside it.")

    return {
        "status": "COMPLETE",
        "candidate_groups": agrupado["candidate_groups"],
        "group_count": agrupado["group_count"],
        "extra_rows": agrupado["extra_rows"],
        "without_vendor_grouping": {"group_count": suelto["group_count"],
                                    "extra_rows": suelto["extra_rows"]},
        "rows_without_vendor": agrupado["rows_without_vendor"],
    }


def policy_breaches(eje, root, threshold=1000, date_field="accrual_date"):
    """Transactions that look like they breached the T&E policy. Candidates.

    ONE RULE OF SIX IS CHECKABLE, AND SAYING WHICH FIVE ARE NOT IS THE ANSWER

    Meridian's policy carries six rules. Read against the columns that exist:

        economy class under six hours      needs flight duration and fare class
        nightly cap 275 / 190             needs city and nights
        per-diem 85 per day               needs days travelled
        entertainment over 500 needs a VP  needs attendees, and client meals share
                                           an account with employee meals
        expenses >= 1,000 need an approval  amount and approval_ref ARE columns
        non-reimbursable list              needs to know what was bought

    Five of the six ask for facts this dataset does not hold. Only the approval
    rule is answerable, and reporting that plainly is worth more than five
    guesses.

    THE 88% TRAP, MEASURED
    The approval rule applied to the WHOLE ledger flags 6,376 of 7,237 rows -
    88% of everything over the threshold. Applied to travel accounts only: 12 of
    873, which is 1%. The policy says which expenses it governs, so scope is not
    a refinement, it is the difference between a finding and a wall of noise.
    Scope comes from `root`, resolved per validity window like every other plan.

    WHY CANDIDATES AND NOT BREACHES
    An expense over the threshold with no approval_ref might have been approved
    on paper, approved late, or approved under a reference nobody typed in. The
    rule is checkable; the conclusion is not.
    """
    threshold = float(threshold)

    # THE RULE CITES ITS SOURCE, OR IS DECLARED AS HAVING NONE.
    # The threshold arrives as a parameter - set by the model after reading the policy,
    # or by hand. If it appears in no document in the pack, the rule is an assertion by
    # whoever asked rather than the policy's, and that changes what the answer is worth.
    # "No claim without a source" is the brief's own line.
    catalogo = eje.usar(read_document, datos_dir=eje.datos_dir)
    fuente, titulos = [], {}
    entero = f"{int(threshold):,}"
    for nombre in catalogo["documents"]:
        doc = eje.usar(read_document, datos_dir=eje.datos_dir, name=nombre)
        # Section headings, kept from the same read: the what-was-not-checked
        # sentence below is BUILT from them, never asserted.
        # Fenced blocks are dropped first: a `## comment` inside ``` is shell, not a
        # heading, and citing it would attribute to the policy a section it never had.
        sin_bloques = re.sub(r"```.*?```", "", doc["text"], flags=re.S)
        titulos[nombre] = re.findall(r"^#{2,}\s*(.+?)\s*$", sin_bloques, re.M)
        texto = re.sub(r"\s+", " ", doc["text"])
        for m in re.finditer(r"[^.]*\.", texto):
            frase = m.group(0).strip()
            if (entero in frase or str(int(threshold)) in frase) and "approv" in frase.lower():
                fuente.append({"document": nombre, "sentence": re.sub(r"\*+", "", frase)})

    rango = eje.con.execute(
        f"SELECT MIN({date_field}), MAX({date_field}) FROM gl_transactions").fetchone()
    filas, resoluciones = _sumar_periodo(eje, root, rango[0], rango[1], date_field,
                                         group_by=("account_code",))
    if filas is None:
        return {"status": "REFUSED", "root": root,
                "reason": "the policy scope resolved to no posting accounts; see the note"}
    en_alcance = sorted({c for _, _, hojas in resoluciones for c in hojas})

    # ONE CONDITION PER WINDOW, and the first version did not do that. It collected the
    # leaves of every window and queried the whole period, so an account in scope only
    # until June still counted in August. The fixture catches it on purpose: with the
    # union it returns 6 candidates where its contract says 5, and the extra one is the
    # meal of 2024-07-10 on an account that had already moved to marketing. The sentence
    # this plan prints claimed "resolved window by window" while the code did otherwise.
    trozos, params = [], []
    for ini, fin, hojas in resoluciones:
        if not hojas:
            continue
        trozos.append(f"({date_field} BETWEEN ? AND ? AND account_code IN "
                      f"({','.join('?' * len(hojas))}))")
        params += [ini, fin] + list(hojas)
    sql = (f"SELECT txn_id, {date_field}, entity, cost_centre, account_code, amount, currency, "
           f"substr({date_field},1,7), vendor_id, memo FROM gl_transactions "
           f"WHERE ({' OR '.join(trozos)}) AND (approval_ref = '' OR approval_ref IS NULL)")
    sospechosas = [dict(zip(("txn_id", "date", "entity", "cost_centre", "account_code", "amount",
                             "currency", "period_month", "vendor_id", "memo"), r))
                   for r in eje.con.execute(sql, params)]
    marcas = ",".join("?" * len(en_alcance))
    fx = eje.usar(convert_currency, con=eje.con, rows=sospechosas)

    candidatos = [{**f, "usd": f["amount"], "rule": f"expense >= {threshold:,.0f} USD with no "
                                                   f"approval reference recorded"}
                  for f in fx["rows"] if f["amount"] >= threshold]
    candidatos.sort(key=lambda c: -c["usd"])

    # 6230 moves from Travel to Marketing mid-2024, so reading by hierarchy and reading
    # by account name do not count the same rows. Either is acceptable if stated;
    # silence is not.
    # What the by-name reading would ADD: rows in those same accounts falling outside
    # the window in which the account belonged to the group. The first version compared
    # against the chart of accounts and returned 0 every time - a reassuring figure that
    # measured nothing.
    por_nombre = eje.con.execute(
        f"SELECT COUNT(*) FROM gl_transactions WHERE account_code IN ({marcas}) "
        f"AND (approval_ref='' OR approval_ref IS NULL)", en_alcance).fetchone()[0]
    fuera = por_nombre - len(sospechosas)

    eje.trace.decision(
        f"Scope is what the policy governs, not the whole ledger. It was resolved from "
        f"'{root}' to {len(en_alcance)} posting account(s) per validity window. The same rule "
        f"applied to every account in this file flags "
        + str(eje.con.execute(
            "SELECT COUNT(*) FROM gl_transactions WHERE amount >= ? AND "
            "(approval_ref='' OR approval_ref IS NULL)", (threshold,)).fetchone()[0])
        + " row(s), which is a wall of noise rather than a finding.")
    if fuente:
        eje.trace.decision(
            "The rule applied is the policy's own, quoted: "
            + " ".join(f'{d["document"]}: "{d["sentence"]}"' for d in fuente))
    else:
        eje.trace.decision(
            f"No document in this pack states a {threshold:,.0f} approval threshold, so the "
            f"rule applied came from whoever asked and not from the policy. The candidates "
            f"below are still measured, but they breach a rule this dataset does not carry.")
    # The first version of this decision enumerated Meridian's six rules in a fixed
    # string - fare class, room rate, per-diem - and was already FALSE against the
    # fixture, whose policy has four sections and none of those rules. It escaped
    # no_borrowed_facts because that eval reads tool notes and this is a plan
    # decision. Now the sentence is built from the headings of the documents this
    # very run read, so it cannot describe a policy it was not given.
    docs_regla = list(dict.fromkeys(d["document"] for d in fuente)) or [
        n for n in catalogo["documents"] if "policy" in n.lower()]
    # Deduplicated, order preserved: two documents naming a section alike would
    # otherwise count it twice and inflate the "N section(s)" the sentence prints.
    secciones = list(dict.fromkeys(s for n in docs_regla for s in titulos.get(n, [])))
    resto = (f"The policy it came from ({', '.join(docs_regla)}) states "
             f"{len(secciones)} section(s): {'; '.join(secciones)}. The rest "
             if secciones else "All other rules the pack may state ")
    eje.trace.decision(
        "One rule was checked, because only its facts are columns: amount and "
        "approval_ref exist, so the approval-reference rule is answerable from this "
        "file. " + resto +
        "were not checked against these columns: turning policy text into checkable "
        "rules is a reading this plan does not take - it is the model's declared "
        "decision in the full pipeline.")
    eje.trace.decision(
        f"An account that changed parent inside the period is in scope only while it belonged "
        f"there, because scope was resolved window by window. Read by account NAME instead of "
        f"by hierarchy, {fuera} further unapproved row(s) in those same accounts come into "
        f"view - how many of them clear the threshold is not computed, because this reading "
        f"was not the one taken. Either is defensible; this one is stated.")

    return {
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "root": root, "threshold_usd": threshold,
        "accounts_in_scope": en_alcance,
        "candidate_count": len(candidatos),
        "candidates": candidatos[:20],
        "rule_source": fuente,
        "rules_checked": 1,
        "rows_examined": len(sospechosas),
        "excluded": fx["unconverted"],
    }


def consolidated_spend(eje, year=None, quarter=3, date_field="accrual_date"):
    """Total spend for a quarter in USD, and what could not be converted.

    Two tools, and they are kept apart on purpose: query_ledger never sums across
    currencies, so a missing rate cannot vanish inside a subtotal. It comes back
    as `unconverted`, which is what makes this answer PARTIAL rather than wrong.
    """
    quarter = _cuarto(quarter)
    year, desde, hasta = _trimestre(eje, year, quarter, date_field)
    if year is None:
        return {"status": "REFUSED", "period": f"Q{quarter}", "reason": "no rows in that quarter"}

    mayor = eje.usar(query_ledger, con=eje.con, date_from=desde, date_to=hasta,
                     date_field=date_field)
    fx = eje.usar(convert_currency, con=eje.con, rows=mayor["rows"])

    # THE OTHER YEARS ARE RUN TOO, AND NOT FOR COMPLETENESS.
    # "The most recent year was used, and the same plan answers any of them" is true and
    # is not what needs saying. This file can total Q3 2023 completely and Q3 2024 not at
    # all, because September is missing a rate - and that difference IS the answer to one
    # of the two questions the brief expects to have no clean one. EXPECTED.md, written
    # before this code, already gave both years for exactly that reason.
    #
    # It costs a couple of queries per candidate year. Measured: the whole plan runs in
    # 0.01s. A ten-year file would mean ten passes - still cheap, and said here so nobody
    # meets it as a surprise.
    otros = {}
    desde_mes, hasta_mes = f"{(int(quarter) - 1) * 3 + 1:02d}", f"{int(quarter) * 3:02d}"
    for candidato in _anios_con_datos(eje.con, date_field, desde_mes, hasta_mes):
        if candidato == str(year):
            continue
        m = eje.usar(query_ledger, con=eje.con, date_from=f"{candidato}-{desde_mes}-01",
                     date_to=f"{candidato}-{FIN_TRIMESTRE[int(quarter)]}", date_field=date_field)
        c = eje.usar(convert_currency, con=eje.con, rows=m["rows"])
        otros[f"Q{quarter} {candidato}"] = {
            "total": c["total"], "status": "PARTIAL" if c["unconverted"] else "COMPLETE",
            "excluded": c["unconverted"]}
    completos = [p for p, v in ({f"Q{quarter} {year}": {"status": "PARTIAL" if fx["unconverted"]
                                                        else "COMPLETE"}} | otros).items()
                 if v["status"] == "COMPLETE"]
    if otros:
        eje.trace.decision(
            f"Every year with Q{quarter} data was totalled, not just the one reported: "
            + "; ".join(f'{p} = {v["total"]:,.2f} {v["status"]}' for p, v in otros.items())
            + ". "
            + (f"Only {', '.join(completos)} can be totalled completely from this file; the rest "
               f"exclude rows with no FX rate."
               if completos and len(completos) < len(otros) + 1
               else "All of them convert completely." if completos
               else "None of them converts completely."))

    return {
        # Not inferred from the text and not decided from memory: `unconverted` is the
        # tool's own measurement. Empty means nothing was left out.
        "status": "PARTIAL" if fx["unconverted"] else "COMPLETE",
        "period": f"Q{quarter} {year}",
        "other_years": otros,
        "total": fx["total"],
        "currency": fx["currency"],
        "ledger_rows": mayor["row_count"],
        "rows_converted": fx["rows_converted"],
        "excluded": fx["unconverted"],
    }


RUTINAS = {
    "opex_by_cost_centre": opex_by_cost_centre,
    "largest_vendors": largest_vendors,
    "budget_variance": budget_variance,
    "cost_per_fte": cost_per_fte,
    "duplicate_payments": duplicate_payments,
    "policy_breaches": policy_breaches,
    "spend_comparison": spend_comparison,
    "consolidated_spend": consolidated_spend,
}


# -- the executor ----------------------------------------------------------------

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
    # Everything arrives as text and stays as text. Turning '6000' into an integer would
    # stop it matching a TEXT column - zero rows, and not one warning.
    params = dict(a.split("=", 1) for a in sys.argv[3:] if "=" in a)
    con = sqlite3.connect(db)
    print(run(nombre, con, dataset=db.name, **params).render())
    con.close()
