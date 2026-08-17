"""The router: it reads the question and picks the plan. That is all it does.

    "Something decides which tools to call, in what order, and when the question
     is answered. That decision is the center of this exercise."

Note the wording: SOMETHING decides, not A MODEL decides. The order of the tool
calls was decided in advance and written down in plans.py, because all eight
questions have a path that can be written down. What could not be written down in
advance is which of the eight a sentence in English is asking for, and which
account a phrase like "operating expenses" or "headcount" means.

So the model does exactly two things here: name a plan and fill its parameters.
It never invents a step, never chooses a tool, and never touches a number.

WHAT THE CODE REFUSES TO LET IT DO

    a plan that does not exist        rejected, and the answer says so
    a parameter the plan cannot take  dropped, and the drop is reported
    an account code that is not real  resolve_accounts returns no leaves and the
                                      plan refuses, which is already how every
                                      root reaches a plan

The last one is the reason the router hands over a CODE and not a name: the
validation already exists and did not have to be written twice. The model picks
from list_account_names, which is the whole chart - 33 names and 1,219 characters
against Meridian - so choosing is reading, not remembering.

WHY THE PARAMETERS ARE FILTERED RATHER THAN TRUSTED
A model that returns {"plan": "consolidated_spend", "params": {"year": "2024",
"currency": "EUR"}} is not lying, it is guessing at an interface. Passing that
through raises TypeError deep inside a plan; dropping it silently answers a
different question. It is dropped and named.
"""

import inspect
import json
import re

from src.agent.model import ask
from src.agent.plans import PLANS, describe
from src.tools.accounts import list_account_names

SISTEMA = (
    "You route a finance question to one of a fixed set of plans. Reply with JSON only, no "
    "prose and no code fences:\n"
    '{"plan": "<name>", "params": {...}, "why": "<one short sentence>"}\n\n'
    "- `plan` must be one of the names listed. If none of them fits the question, use "
    '"plan": null and say why.\n'
    "- `params` may only contain the parameters listed for that plan. Omit any you cannot fill "
    "from the question; the plan has defaults and will declare what it assumed.\n"
    "- Where a plan takes `root`, give the ACCOUNT CODE from the chart below whose meaning "
    "matches the words in the question. Pick the rollup that contains the others rather than "
    "one of its children."
)


# Internal knobs. Offering one invites filling it: the router returned
# date_field="transaction_date", a column that does not exist. No English question
# decides whether a period runs on accrual or posting date - that is a convention of
# the system, and the answer already declares which one it used.
INTERNOS = ("date_field",)


def _parametros(funcion, visibles=True):
    """The parameters a plan accepts. `visibles` hides the internal knobs."""
    return [n for n in inspect.signature(funcion).parameters
            if n != "eje" and not (visibles and n in INTERNOS)]


def _menu(rutinas):
    lineas = []
    for nombre, funcion in rutinas.items():
        lineas.append(f"- {describe(nombre)}\n    parameters: {', '.join(_parametros(funcion))}")
    return "\n".join(lineas)


def _json(texto):
    """Models fence their JSON however they feel like. Take the first object."""
    limpio = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio < 0 or fin < 0:
        raise ValueError(f"the router did not return JSON: {texto[:200]!r}")
    return json.loads(limpio[inicio:fin + 1])


def elegir(pregunta, con, budget, rutinas, as_of=None):
    """Question in, {plan, params, why, dropped} out. Validated, never trusted."""
    as_of = as_of or con.execute(
        "SELECT MAX(accrual_date) FROM gl_transactions").fetchone()[0]
    cuentas = list_account_names(con, as_of)["result"]["accounts"]
    catalogo = "\n".join(f"  {c['account_code']}  {c['account_name']}"
                         + (f"  (under {c['parent_code']})" if c["parent_code"] else "  (top)")
                         for c in cuentas)

    salida = ask([{"role": "system", "content": SISTEMA},
                  {"role": "user", "content":
                      f"Question: {pregunta}\n\nPlans:\n{_menu(rutinas)}\n\n"
                      f"Chart of accounts in force on {as_of}:\n{catalogo}"}], budget)
    elegido = _json(salida["text"])

    nombre = elegido.get("plan")
    if nombre not in rutinas:
        return {"plan": None, "params": {}, "dropped": {}, "model": salida,
                "why": (f"'{nombre}' is not a plan in this system. The eight it knows are "
                        f"{', '.join(rutinas)}." if nombre else
                        elegido.get("why") or "the router found no plan for this question")}

    permitidos = _parametros(rutinas[nombre])
    crudos = elegido.get("params") or {}
    params = {k: v for k, v in crudos.items() if k in permitidos and v is not None}
    sobrantes = {k: v for k, v in crudos.items() if k not in permitidos}
    return {"plan": nombre, "params": params, "dropped": sobrantes,
            "why": elegido.get("why", ""), "model": salida}


def anotar(trace, eleccion):
    """Put the routing decision in the trace, including what was thrown away."""
    trace.model_call(eleccion["model"])
    trace.decision(
        f"The question was routed to '{eleccion['plan']}'"
        + (f" with {eleccion['params']}" if eleccion["params"] else " with no parameters")
        + f". Reason given: {eleccion['why']}"
        + (f". IGNORED: {eleccion['dropped']} - this plan does not take those, and passing "
           f"them would have answered a different question quietly."
           if eleccion["dropped"] else "."))
    for ajuste in eleccion["model"].get("compatibility_adjustments") or []:
        trace.decision(f"Model compatibility: {ajuste}.")
