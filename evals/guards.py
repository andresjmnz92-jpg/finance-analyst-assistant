"""Fail if a guard that only fires against OTHER data has stopped firing.

    python -m evals.guards

WHY THIS FILE EXISTS, AND IT IS THE SAME REASON TWICE

An adversarial review found six defects in one afternoon. Every one of them is
invisible against Meridian and appears against data shaped differently - which is
what the brief says will happen. Fixing them produced guard code that NOTHING
exercises, because the data in this repository cannot reach it.

Untested guard code is a comment with a semicolon. So each case is reproduced
here by mutating a COPY of the fixture: a budget line set to zero, a ledger row
in a currency that has no rate at all, a year nobody has data for. The copy is
temporary and the fixture on disk is never touched.

The other half of the reason: asked how the earlier fixes had been verified, the
honest answer was that the edge cases were written after the fix, checked once in
a terminal, and lost. A check that ran once is a claim, not a test.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.run import run                              # noqa: E402
from src.tools.ledger import query_ledger                  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def _copia(con_origen):
    """A throwaway copy of the fixture, so a mutation cannot outlive the check."""
    destino = Path(tempfile.mkdtemp()) / "guards.db"
    shutil.copy(RAIZ / con_origen, destino)
    return destino


def ano_inexistente(fallos):
    """A year that was ASKED for and has no rows must refuse, not answer zero.

    Measured before the fix: `quarter=3 year=2099` returned status COMPLETE and
    total 0.00. The year is the argument the model supplies after reading the
    question, so it is the likeliest wrong one to ever arrive.
    """
    con = sqlite3.connect(_copia("fixtures.db"))
    t = run("consolidated_spend", con, dataset="guards.db", quarter=3, year="2099").as_dict()
    if t["status"] != "REFUSED":
        fallos.append(f"a year with no rows returned {t['status']} instead of REFUSED")
    if not any("2099" in n for n in t["all_notes"]):
        fallos.append("the refusal does not name the year that was asked for")
    con.close()


def presupuesto_en_cero(fallos):
    """Spending against a zero budget is infinitely over, not zero percent over.

    Ranking it by a percent of None sorted it LAST, so the centre spending with no
    plan at all dropped out of the percent ranking silently.
    """
    ruta = _copia("fixtures.db")
    con = sqlite3.connect(ruta)
    con.execute("UPDATE budget SET budget_amount = 0 "
                "WHERE cost_centre='OPS-US' AND account_code='6610'")
    con.commit()
    peor = run("budget_variance", con, dataset="guards.db").as_dict()["findings"]["worst_by_percent"][0]
    if not peor.get("percent_undefined_zero_budget"):
        fallos.append(f"a zero budget with real spend did not rank first by percent; "
                      f"first was {peor['cost_centre']}/{peor['account_code']}")
    con.close()


def moneda_sin_tasa(fallos):
    """A currency absent from fx_rates has no lower bound, and must say so.

    The bound is what proves a deviation changes sign. Defaulting a missing
    currency to a rate of 0.0 reads as "nothing is missing" and can hide a real
    flip.
    """
    ruta = _copia("fixtures.db")
    con = sqlite3.connect(ruta)
    con.execute("INSERT INTO gl_transactions VALUES "
                "('T099','2024-08-01','2024-08-01','TS-EU','OPS-EU','6210',500,'GBP',"
                "'V005','','','guard')")
    con.commit()
    f = run("budget_variance", con, dataset="guards.db").as_dict()["findings"]
    marcadas = [c for c in f["worst_by_value"] + f["worst_by_percent"]
                if "GBP" in (c.get("no_rate_at_all_for") or [])]
    if not marcadas:
        fallos.append("a currency with no rate anywhere in fx_rates was not flagged; its "
                      "missing amount was silently bounded at zero")
    con.close()


def creditos_por_moneda(fallos):
    """Negative amounts are reported per currency, never added across them.

    The first version summed them together. Against Meridian that produced
    -329,539.17, which is 68,917.97 CAD and 112,441.83 EUR and 148,179.37 USD
    stacked - inside the tool whose docstring says it never sums across
    currencies.
    """
    ruta = _copia("fixtures.db")
    con = sqlite3.connect(ruta)
    con.execute("INSERT INTO gl_transactions VALUES "
                "('T098','2024-08-02','2024-08-02','TS-EU','OPS-EU','6210',-100,'EUR',"
                "'V005','','','guard credit'),"
                "('T097','2024-08-02','2024-08-02','TS-US','OPS-US','6610',-100,'USD',"
                "'V001','','','guard credit')")
    con.commit()
    notas = query_ledger(con, date_from="2024-08-01", date_to="2024-08-31")["notes"]
    aviso = [n for n in notas if "Negative amounts" in n]
    if not aviso:
        fallos.append("negative amounts present and no note said so")
    elif not ("EUR" in aviso[0] and "USD" in aviso[0]):
        fallos.append(f"the credit note does not name both currencies separately: {aviso[0]}")
    con.close()


COMPROBACIONES = [ano_inexistente, presupuesto_en_cero, moneda_sin_tasa, creditos_por_moneda]


def main():
    fallos = []
    for c in COMPROBACIONES:
        antes = len(fallos)
        c(fallos)
        print(f"  {c.__name__:22s} {'ok' if len(fallos) == antes else 'FAIL'}")

    print(f"\n{len(COMPROBACIONES)} guard(s) exercised against mutated copies of the fixture.")
    if fallos:
        print("\nFAIL:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS - every guard still fires on the data shape it was written for.")


if __name__ == "__main__":
    main()
