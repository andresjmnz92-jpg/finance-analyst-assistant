"""The writer: it turns measured numbers into a sentence, and it cannot do more.

THE MODEL WRITES ONE PARAGRAPH. THE CODE WRITES EVERYTHING ELSE.

The first design asked the model to carry the caveats into its answer. That is a
request, and the failure it invites is the exact one this exercise punishes: the
total of 10,003,879.96 is correct AND 147 rows are missing from it. A model that
prints the figure and forgets the warning has produced a wrong number wearing a
right one's clothes.

So the caveats are not the model's job at all:

    the paragraph   written by the model
    the figures     printed from findings by code
    the caveats     printed VERBATIM from what the tools measured, by code

It cannot forget what it was never asked to hold. And a second gain that was not
the goal: the caveats reach the reader in the words of the tool that measured
them. Paraphrasing a warning is the easiest way to soften one.

WHAT THIS REMOVES FROM THE PROMPT, WHICH IS THE POINT
"Do not forget the caveats", "say which year you chose", "if you refuse, do not
give a total" - all three stop depending on the model. A refusal never reaches
the model at all: there is nothing to summarise and every way of phrasing it is a
way of hedging it.

Moving instructions into a file would not have done this. What takes a rule out
of the prompt is making it impossible to break, not writing it down elsewhere.

THE ONE RULE THAT STAYS A REQUEST, AND ITS GUARD
The paragraph may still contain a figure, so it can still contain a wrong one.
Every number it writes is checked against the numbers present in the findings and
the notes. A figure that is in neither is ANNOTATED above the answer, naming what
could not be verified. It is not deleted and the answer is not asked for again.

That is a correction, and the reason is in ARCHITECTURE.md: the first version
rejected the paragraph and retried twice, and it was wrong all three times it
fired - over a truncated figure, a correct sign, and the numerals in a bulleted
list. A guard that is wrong deletes correct answers and spends two model calls
doing it. Detection over prose is a heuristic, so it adds rather than removes.

The guard's limit, stated because it is real: a single plan offers hundreds of
distinct numbers to match against. Checking membership proves a figure CAME FROM
the data. It does not prove the figure belongs in the sentence it is sitting in -
a total copied correctly and attached to the wrong vendor passes. That is
semantic and it is not closed here.

THE FLOOR
Figures and caveats are printed from the findings by code, whatever the model
writes. The floor of this system is correct and ugly, never fluent and unchecked.
"""

import json
import re

from src.agent.model import ask
from src.agent.plans import PLANS

# Anything with a figure inside. Normalised by dropping thousands separators and
# trailing zeros, so that 1,231,309.12 and 1231309.120 are the same number.
NUMERO = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

# ONE RULE, AND THE OTHER TWO WERE MEASURED AND REMOVED.
#
# This prompt held seven rules, then three. Two of the three existed to stop
# behaviour whose cause was in the DATA, not in the model's obedience:
#
#   "do not claim more than the caveats support"  - it overclaimed because it
#       could not SEE the caveats. Showing them fixed it and left the rule with
#       nothing to do.
#   "answer, do not describe the method"          - it described the method
#       because the caveats it had just been handed are ten lines of method. The
#       rule was patching this file's own input.
#
# Measured against gpt-5-mini over three plans, three rules against one: the
# paragraphs came out equivalent. Neither version overclaimed, neither drifted
# into methodology, and the three-rule version repeated the caveats anyway - the
# exact thing one of its rules forbade.
#
# So, before writing a rule in bold: is the problem data or obedience? If it is
# data, fix the data and the rule is never written. What survives is the one
# thing that would do damage, and behind it there is a guard in code rather than
# trust.
SISTEMA = (
    "You are an FP&A analyst's assistant. You are given the RESULT of work already done by "
    "tools: the figures are measured and final.\n\n"
    "Answer the question in plain English for a finance manager, in one short paragraph.\n\n"
    "- Never calculate. Use only figures that appear in the data given to you."
)


def _numeros(texto):
    """The set of figures in a piece of text, normalised for comparison."""
    salida = set()
    for bruto in NUMERO.findall(texto):
        limpio = bruto.replace(",", "")
        try:
            valor = float(limpio)
        except ValueError:
            continue
        salida.add(round(valor, 2))
    return salida


def _fabricados(texto, permitidos):
    """Figures in the paragraph that no tool produced.

    Compared at the precision the model WROTE, not exactly. It printed
    "USD 4099409" where the measured figure is 4,099,409.58 - a truncation of a
    real number, which is imprecision and not invention, and the exact figure is
    printed two lines below it anyway. Rejecting that cost two retries and
    degraded a correct answer to raw output.

    The first attempt at a fix went the other way, handing the model a formatted
    menu of every number in the findings. It then wrote "account 6,200.00" and
    "for 2,023.00" - an account code and a year, dressed as money, because the
    menu could not tell them apart. Worse prose than the problem it solved, and
    removed.

    So: a figure is a fabrication when nothing measured is within one unit of its
    last written digit. Rounding stays allowed, invention does not.
    """
    malos = set()
    for bruto in NUMERO.findall(texto):
        limpio = bruto.replace(",", "")
        try:
            valor = float(limpio)
        except ValueError:
            continue
        # Only what could be a FIGURE. A small bare integer in prose is a count or a
        # bullet: the guard flagged 5.00 and 8.00 out of "5) Ridgeline, 8) ..." as
        # invented. Third false positive of the same family, and the damage this guard
        # exists to prevent is an invented amount of money, not an ordinal.
        if "." not in bruto and "," not in bruto and abs(valor) < 1000:
            continue
        decimales = len(limpio.split(".")[1]) if "." in limpio else 0
        tolerancia = 10.0 ** -decimales
        # And in ABSOLUTE VALUE. The measured finding is -204,257.95 and the model
        # wrote "a decrease of USD 204,257.95", which is correct English: the direction
        # lives in the word and the sign is not repeated. Comparing signed values, the
        # guard flagged an exact figure as invented in 2 of 6 runs.
        # What that costs, stated: an "increase" where there was a fall is no longer
        # caught by anything. That class of error is semantic, like attaching a total
        # to the wrong vendor, and this guard was never going to reach it.
        if not any(abs(valor - p) < tolerancia or abs(abs(valor) - abs(p)) < tolerancia
                   for p in permitidos):
            malos.add(valor)
    return sorted(malos)


def _permitidos(datos):
    """Every figure the model is allowed to use: the ones the tools produced."""
    return _numeros(json.dumps(datos["findings"], ensure_ascii=False) + " "
                    + " ".join(datos["all_notes"]) + " " + datos["question"])


def _bloque(titulo, lineas):
    return f"{titulo}\n" + "\n".join(f"  {l}" for l in lineas) if lineas else ""


def _figuras(datos, tope=12):
    """The figures, printed by code, WITHOUT collapsing the lists.

    The trace's summary shortens any list over six entries to "10 item(s)",
    which is right for a trace: it exists to be legible, and the SQL beside it
    lets anyone reproduce the rows. It is wrong here. Against largest_vendors the
    answer's FIGURES block read "top: 10 item(s)", so the ranking itself - the
    entire content of that answer - existed only inside the model's paragraph.

    The whole design says the figures are printed by code and the model only
    writes prose. That guarantee did not hold in the one answer made of nothing
    but figures.
    """
    def escalar(v):
        return f"{v:,.2f}" if isinstance(v, float) else str(v)

    lineas = []
    for k, v in (datos or {}).items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            lineas.append(f"{k}:")
            for i, fila in enumerate(v[:tope], 1):
                campos = ", ".join(f"{a}={escalar(b)}" for a, b in fila.items()
                                   if not isinstance(b, (list, dict)))
                lineas.append(f"  {i}. {campos}")
            if len(v) > tope:
                lineas.append(f"  ... and {len(v) - tope} more")
        elif isinstance(v, dict) and v:
            lineas.append(f"{k}: " + ", ".join(f"{a}={escalar(b)}" for a, b in v.items()
                                               if not isinstance(b, (list, dict))))
        elif isinstance(v, list):
            lineas.append(f"{k}: {json.dumps(v, ensure_ascii=False, default=str)[:200]}")
        else:
            lineas.append(f"{k}: {escalar(v)}")
    return lineas


def _armar(parrafo, datos, aviso=None):
    """The answer as the reader gets it. Only the paragraph came from the model.

    Caveats are deduplicated HERE and not in the trace. A plan that cuts a period
    into three windows calls query_ledger three times, and each call honestly
    reports the same thing about the same file - the date convention, the
    currencies present. Fifteen lines where six are distinct is how a reader
    learns to skip the section that exists to be read.

    The trace still holds every note beside the step that produced it, because
    that is evidence. This is the answer, which is a different job.
    """
    partes = []
    if aviso:
        partes.append(f"[{aviso}]")
    if parrafo:
        partes.append(parrafo)
    partes.append(_bloque("FIGURES", _figuras(datos["findings"])))
    partes.append(_bloque("WHAT THIS ANSWER DEPENDS ON",
                          list(dict.fromkeys(datos["all_notes"]))))
    return "\n\n".join(p for p in partes if p)


def redactar(trace, budget, sistema=None):
    """Write the answer onto the trace and return it.

    A REFUSED run never reaches the model. There is no number to summarise and
    every phrasing of "I cannot answer this" that a model might improve on is a
    phrasing that hedges it.
    """
    datos = trace.as_dict()
    if datos["status"] == "REFUSED":
        motivo = (datos["findings"] or {}).get("reason", "the data does not support an answer")
        trace.answer = _armar(f"No answer can be given from this data: {motivo}.", datos)
        return trace.answer

    permitidos = _permitidos(datos)
    contrato = PLANS.get(datos["plan"], {}).get("must_declare", [])
    # The caveats ARE SHOWN to it even though it does not write them, and that came
    # from reading the first real answer: without seeing them it wrote "the business
    # achieved a meaningful reduction" over a fall its own caveats half explain as a
    # missing FX rate. Not repeating them is one thing; ignoring them is another.
    peticion = (
        f'Question: "{datos["question"]}"\n\n'
        f"Measured result:\n{json.dumps(datos['findings'], ensure_ascii=False, indent=1)}\n\n"
        f"This answer is {datos['status']}.\n\n"
        f"Caveats that will be printed under your paragraph, for you to respect and NOT to "
        f"repeat:\n"
        + "\n".join(f"- {n}" for n in dict.fromkeys(datos["all_notes"]))
        + (f"\n\nThe reader is entitled to know about: {'; '.join(contrato)}."
           if contrato else ""))

    salida = ask([{"role": "system", "content": sistema or SISTEMA},
                  {"role": "user", "content": peticion}], budget)
    trace.model_call(salida)
    inventados = _fabricados(salida["text"], permitidos)

    # THE GUARD ANNOTATES, IT DOES NOT DELETE - and that correction is not cosmetic.
    # The first version threw the paragraph away after two rejections and printed
    # the raw findings. It also rejected "USD 4099409", which is a truncation of a
    # figure that exists. A guard that is wrong is worse than no guard: it deleted
    # a correct answer over a formatting difference, and cost two model calls to
    # do it.
    #
    # Surgery only where detection is deterministic; where it is a heuristic over
    # natural language, the guard ADDS rather than removes. Finding a figure in
    # prose is a heuristic. So the paragraph is always shown, and anything that
    # does not match a measured figure is flagged above it, next to the figures
    # themselves. The reader sees both and can settle it in one glance.
    aviso = None
    if inventados:
        aviso = (f"Not verified: {', '.join(f'{n:,.2f}' for n in inventados)} in the summary "
                 f"below does not match any measured figure. The FIGURES section is what the "
                 f"tools returned.")
    trace.answer = _armar(salida["text"], datos, aviso=aviso)
    return trace.answer
