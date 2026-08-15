"""Fail if any tool asserts a fact it did not measure from the file it was given.

    python -m evals.no_borrowed_facts

WHY THIS EXISTS

Every tool returns `notes`, and notes travel into the final answer. An early
version of this codebase wrote Meridian's own measurements into those notes -
which date ranges disagree, how many duplicates were planted, which vendor was
spelled four ways. Correct for Meridian, and a fabricated claim about any other
dataset. The brief says the tools will be run against a second dataset, so those
notes were a plausible-but-false statement waiting to be printed.

The check is simple: run every tool against the fixture, whose contents are
entirely unrelated to Meridian, and fail if a note mentions anything that exists
only in Meridian. A tool may describe what it measured; it may not remember.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.accounts import resolve_accounts          # noqa: E402
from src.tools.budget import query_budget                # noqa: E402
from src.tools.documents import read_document            # noqa: E402
from src.tools.duplicates import find_duplicate_payments  # noqa: E402
from src.tools.fx import convert_currency                # noqa: E402
from src.tools.ledger import query_ledger                # noqa: E402
from src.tools.vendors import normalize_vendors          # noqa: E402

# Names, codes and figures that exist ONLY in Meridian. If one of these reaches a
# note while the fixture is loaded, the tool is quoting from memory.
PRESTADO = [
    "meridian", "nordwind", "delft", "kestrel", "northgate", "ops-amer", "ops-na",
    "aeroline", "10,909", "10,916", "600000", "1,231,309", "147 ",
    "seven planted", "the 7 planted", "228", "456", "2025-01", "2024-12-31",
]
# 'Sundry Supplier' NO esta en la lista, y el motivo importa: el fixture tambien
# lo tiene, asi que una nota que lo mencione lo esta MIDIENDO. Estuvo en la lista
# un minuto y el test fallo por eso - el primer fallo fue del test, no del codigo.
# Un detector de hechos prestados solo sirve con terminos que el otro dataset no
# comparte.


def revisar(db, datos_dir):
    con = sqlite3.connect(db)
    hojas = resolve_accounts(con, "6000", "2024-08-01")["result"]["leaves"]
    grupos = normalize_vendors(con)["result"]["candidate_groups"]
    filas = query_ledger(con, date_from="2024-07-01", date_to="2024-09-30",
                         accounts=hojas, group_by=("cost_centre",))

    salidas = {
        "resolve_accounts": resolve_accounts(con, "6200", "2024-07-15"),
        "query_ledger": filas,
        "convert_currency": convert_currency(con, filas["result"]["rows"]),
        "query_budget": query_budget(con, "2024-07", "2024-09"),
        "normalize_vendors": normalize_vendors(con),
        "find_duplicate_payments": find_duplicate_payments(con, vendor_groups=grupos),
        "read_document": read_document(datos_dir, "travel_expense_policy"),
    }

    fallos = []
    for nombre, salida in salidas.items():
        for nota in salida["notes"]:
            bajo = nota.lower()
            for termino in PRESTADO:
                if termino in bajo:
                    fallos.append((nombre, termino, nota[:160]))
    return salidas, fallos


def main():
    raiz = Path(__file__).resolve().parent.parent
    salidas, fallos = revisar(raiz / "fixtures.db", raiz / "evals" / "fixtures")

    print(f"{len(salidas)} tools run against the fixture, "
          f"{sum(len(s['notes']) for s in salidas.values())} notes produced.\n")
    for nombre, salida in salidas.items():
        print(f"  {nombre}: {len(salida['notes'])} note(s)")

    if fallos:
        print(f"\nFAIL - {len(fallos)} note(s) quote something only Meridian has:\n")
        for nombre, termino, nota in fallos:
            print(f"  {nombre}: contains {termino!r}\n      {nota}...\n")
        sys.exit(1)

    print("\nPASS - no note mentions anything outside the loaded dataset.")


if __name__ == "__main__":
    main()
