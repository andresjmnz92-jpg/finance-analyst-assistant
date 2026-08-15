"""The trace: what the assistant did, written down as it does it.

    "I need to see exactly what it did, because if it hands a client a wrong
     number once, we're finished."

That sentence is the product, not a logging requirement. A correct figure nobody
can retrace is worth the same as a wrong one to a manager who has to defend it.

WHAT EACH STEP RECORDS, AND WHY EACH FIELD IS THERE

    tool        which tool ran
    args        what it was given - the difference between two runs is here
    summary     a few lines about what came back, NOT the rows themselves
    notes       every caveat the tool raised, kept beside the step that raised it
    sql         the exact statement and parameters, so the number can be re-run
    seconds     what it cost in time

Results are summarised rather than stored. A trace holding 1,348 rows is not
legible to anyone, which is the one thing it has to be. The SQL is kept in full
instead: it is smaller than the data and it lets a reader reproduce the figure
rather than take it on trust.

The dataset is recorded too - name, row count and the folder it was loaded from.
Earlier today a set of tools reported measurements from a file that was not
loaded, and nothing in the output said which file was in hand. That is now the
first line of every trace.

TWO FORMS, ONE NOTEBOOK
`as_dict` is for the eval runner, which needs to assert that an answer declared
what it had to declare. `render` is for the person reading it. Both come from the
same record, so they cannot drift apart.
"""

import json
import time
from pathlib import Path


class Trace:
    def __init__(self, question, dataset=None, con=None):
        self.question = question
        self.dataset = dataset
        self.steps = []
        self.answer = None
        self.status = None          # COMPLETE / PARTIAL / REFUSED
        self.model = {"calls": 0, "tokens": 0, "usd": 0.0}
        self.started = time.time()
        self.plan = None
        self.source = self._procedencia(con) if con else None

    @staticmethod
    def _procedencia(con):
        """Which file is actually loaded. Written by the loader into _source."""
        try:
            ruta = con.execute("SELECT value FROM _source WHERE key='path'").fetchone()
            filas = con.execute("SELECT COUNT(*) FROM gl_transactions").fetchone()
            return {"path": ruta[0] if ruta else None, "ledger_rows": filas[0]}
        except Exception:
            return None

    def step(self, tool, args, output, seconds=None):
        """Record one tool call. `output` is a tool's {result, notes, sql} dict."""
        resultado = output.get("result", {})
        self.steps.append({
            "n": len(self.steps) + 1,
            "tool": tool,
            "args": {k: v for k, v in args.items() if k != "con"},
            "summary": _resumir(resultado),
            "notes": list(output.get("notes", [])),
            "sql": [{"statement": s, "params": list(p)} for s, p in output.get("sql", [])],
            "seconds": round(seconds, 3) if seconds is not None else None,
        })
        return output

    def model_call(self, resultado):
        self.model["calls"] += 1
        self.model["tokens"] += resultado.get("total_tokens", 0)
        self.model["usd"] += resultado.get("usd", 0.0)

    def finish(self, answer, status):
        self.answer, self.status = answer, status
        return self

    # -- las dos formas de leer el mismo cuaderno --------------------------------

    def as_dict(self):
        return {
            "question": self.question, "plan": self.plan, "dataset": self.dataset,
            "source": self.source, "status": self.status, "answer": self.answer,
            "steps": self.steps, "model": {**self.model, "usd": round(self.model["usd"], 6)},
            "seconds": round(time.time() - self.started, 2),
            "all_notes": [n for s in self.steps for n in s["notes"]],
        }

    def save(self, carpeta="traces", nombre=None):
        carpeta = Path(carpeta)
        carpeta.mkdir(exist_ok=True)
        nombre = nombre or f"{(self.plan or 'run')}.json"
        ruta = carpeta / nombre
        ruta.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return ruta

    def render(self):
        d = self.as_dict()
        out = [f'question:  "{d["question"]}"']
        if d["plan"]:
            out.append(f'plan:      {d["plan"]}')
        if d["source"]:
            out.append(f'dataset:   {d["dataset"] or "?"}  '
                       f'({d["source"]["ledger_rows"]:,} ledger rows, from {d["source"]["path"]})')
        out.append("")

        for s in d["steps"]:
            args = ", ".join(f"{k}={_corto(v)}" for k, v in s["args"].items()) or "no arguments"
            out.append(f'  step {s["n"]}   {s["tool"]}')
            out.append(f'           {args}')
            for linea in s["summary"]:
                out.append(f'           -> {linea}')
            for n in s["notes"]:
                out.append(f'           {_marca(n)} {_envolver(n)}')
            if s["seconds"] is not None:
                out.append(f'           {s["seconds"]}s')
            out.append("")

        m = d["model"]
        out.append(f'  model:   {m["calls"]} call(s), {m["tokens"]:,} tokens, ${m["usd"]:.4f}')
        out.append(f'  total:   {d["seconds"]}s')
        if d["answer"]:
            out.append("")
            out.append(f'ANSWER - {d["status"]}')
            for linea in d["answer"].splitlines():
                out.append(f'  {linea}')
        return "\n".join(out)


def _marca(nota):
    """Un aviso que se lee igual que el resto no es un aviso.

    Las herramientas escriben en MAYUSCULAS lo que el lector no puede saltarse:
    NOT CONVERTED, TWO BUDGET SETS, AMBIGUOUS RATES. Se busca una palabra de tres
    o mas letras, toda en mayusculas, cerca del principio de la nota.

    DOS INTENTOS FALLIDOS ANTES DE ESTE, LOS DOS SILENCIOSOS:
      1. Comparar los primeros 20 caracteres con su version en mayusculas.
         "NOT CONVERTED - no rate" falla ya en la palabra 'no'.
      2. Un patron de regex escrito con la secuencia de limite de palabra dentro
         de una cadena que no era raw. Python la convirtio en el caracter de
         retroceso (0x08) - invisible en el editor - y el patron quedo buscando
         "retroceso + mayusculas + retroceso", que no casa nunca. No dio error, y
         solo se vio inspeccionando co_consts del bytecode compilado.
    Sin regex: comparar palabras no tiene caracteres que escapar.
    """
    palabras = nota[:40].split()
    return "  ->!" if any(len(w) >= 3 and w.isalpha() and w.isupper() for w in palabras) else "note"

def _resumir(resultado):
    """A few lines about what a tool returned. Never the rows themselves."""
    if not isinstance(resultado, dict):
        return [str(resultado)[:120]]
    lineas = []
    for k, v in resultado.items():
        if isinstance(v, list):
            lineas.append(f"{k}: {len(v)} item(s)" if len(v) > 6 else f"{k}: {_corto(v)}")
        elif isinstance(v, dict):
            lineas.append(f"{k}: {_corto(v)}")
        elif isinstance(v, float):
            lineas.append(f"{k}: {v:,.2f}")
        else:
            lineas.append(f"{k}: {v}")
    return lineas


def _corto(v, tope=90):
    s = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (list, dict)) else str(v)
    return s if len(s) <= tope else s[:tope - 3] + "..."


def _envolver(texto, ancho=88, sangria=" " * 17):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + 1 > ancho:
            lineas.append(actual); actual = p
        else:
            actual = f"{actual} {p}".strip()
    lineas.append(actual)
    return f"\n{sangria}".join(lineas)
