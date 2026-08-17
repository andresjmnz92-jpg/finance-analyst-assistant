"""Ask the assistant a question.

    python -m src.ui.ask "What did we spend on operating expenses in Q2, by cost center?"
    python -m src.ui.ask "Did we pay anyone twice?" --db fixtures.db --save
    python -m src.ui.ask --plan cost_per_fte --param root=6100    # no model at all

WHAT IT PRINTS, AND WHY IT PRINTS ALL OF IT
The brief asks for an interface that "must show the work, not just the
conclusion", so this prints the trace: every tool call with its arguments, the
SQL that produced each figure, every caveat beside the step that raised it, what
the model cost, and only then the answer. A reader who disagrees with a number
can re-run the statement that made it without asking anyone.

THREE WAYS TO RUN, AND THE MIDDLE ONE IS THE POINT

    --plan <name>     runs a plan by name with NO model at all - every figure in
                      this repository can be produced this way, which is what
                      "real computation, testable without the model" means. Add
                      --writer to also spend one model call writing a paragraph
                      over it.
    (a question)      the model reads the question, names a plan and fills its
                      parameters; the code validates both and runs it; the model
                      then writes one paragraph over figures it did not compute.
    --no-writer       routes and runs a question, then prints the figures
                      without prose.

CREDENTIALS ARE YOURS
MODEL_API_KEY comes from the environment or a .env that is not in this
repository. --model and --base-url override MODEL_NAME and MODEL_BASE_URL, so
switching provider needs no file edited: everything speaks the OpenAI-compatible
protocol, with the caveats measured in NOTES.md.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# The paragraph is written by a model, and models write typographic punctuation:
# a non-breaking hyphen in "2024-2023", an en dash between two figures. Windows
# consoles default to cp1252, which has neither, so printing the trace raised
# UnicodeEncodeError and killed the run - on whichever questions the model
# happened to reach for one, since this provider refuses temperature=0 and no two
# runs write the same prose. errors="replace" rather than plain utf-8: a terminal
# that cannot render a character should show a placeholder, never end the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agent.model import Budget, cargar_env                    # noqa: E402
from src.agent.router import anotar, elegir                       # noqa: E402
from src.agent.run import RUTINAS, run                            # noqa: E402
from src.agent.writer import redactar                             # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m src.ui.ask", description=__doc__.split("\n")[0])
    p.add_argument("question", nargs="*", help="the question, in plain English")
    p.add_argument("--plan", help=f"run a plan by name with no model: {', '.join(RUTINAS)}")
    p.add_argument("--param", action="append", default=[], metavar="k=v",
                   help="parameter for --plan; repeatable")
    p.add_argument("--db", default="data.db", help="database file (default: data.db)")
    p.add_argument("--no-writer", action="store_true", help="figures only, no prose")
    p.add_argument("--writer", action="store_true",
                   help="spend a model call writing prose over --plan (off by default)")
    p.add_argument("--save", action="store_true", help="write the trace to traces/")
    p.add_argument("--model", help="overrides MODEL_NAME")
    p.add_argument("--base-url", help="overrides MODEL_BASE_URL")
    a = p.parse_args(argv)

    pregunta = " ".join(a.question).strip()
    if not pregunta and not a.plan:
        p.error("give a question, or --plan <name>")

    cargar_env()
    if a.model:
        os.environ["MODEL_NAME"] = a.model
    if a.base_url:
        os.environ["MODEL_BASE_URL"] = a.base_url

    db = Path(a.db) if Path(a.db).is_absolute() else RAIZ / a.db
    if not db.exists():
        sys.exit(f"{db.name} not found. Build it first:  python -m src.load")
    con = sqlite3.connect(db)
    presupuesto = Budget()

    if a.plan:
        if a.plan not in RUTINAS:
            sys.exit(f"'{a.plan}' is not a plan. Available: {', '.join(RUTINAS)}")
        # Everything arrives as text and stays as text: turning '6000' into an integer
        # stops it matching a TEXT column - zero rows, and not one warning.
        params = dict(x.split("=", 1) for x in a.param if "=" in x)
        trace = run(a.plan, con, dataset=db.name, **params)
    else:
        eleccion = elegir(pregunta, con, presupuesto, RUTINAS)
        if not eleccion["plan"]:
            print(f'question:  "{pregunta}"\n\nNO PLAN\n  {eleccion["why"]}')
            return 1
        trace = run(eleccion["plan"], con, dataset=db.name, **eleccion["params"])
        trace.question = pregunta
        anotar(trace, eleccion)

    # --plan runs with no model unless prose was asked for explicitly: the claim this
    # repository makes is "real computation, testable without the model", and that has
    # to hold for every plan, not just the ones that happen to refuse before reaching
    # the writer.
    escribir = a.writer if a.plan else not a.no_writer
    if escribir:
        redactar(trace, presupuesto)

    # Written before it is printed, not after. The run that is worth keeping is
    # the one that went wrong, and that is exactly the run whose printing can
    # fail - so saving second lost the evidence in the only case that needed it.
    #
    # The name carries the dataset too, not just the plan. traces/duplicate_payments.json
    # is committed evidence from data.db; saving a run against fixtures.db under the same
    # bare name overwrote it silently - 10,916 ledger rows replaced by 18, no warning.
    nombre = f"{trace.plan}.json" if db.name == "data.db" else f"{trace.plan}__{db.stem}.json"
    guardado = trace.save(RAIZ / "traces", nombre=nombre) if a.save else None
    print(trace.render())
    if guardado:
        print(f"\ntrace written to {guardado}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
