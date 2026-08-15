"""The model call. One function, the standard library, and a ceiling.

WHY NO SDK
The whole repository has no dependencies: clone it, run it with Python 3.12, done.
An OpenAI-compatible chat call is JSON over HTTPS, and urllib does that. The SDK
would buy streaming, typed responses and retries; none of the eight questions
needs any of them, and every one of them is another thing for a reviewer to
install before they can see anything work.

WHY AN OPENAI-COMPATIBLE ENDPOINT AND NOT GOOGLE'S OWN
The brief says whoever runs this supplies their own credentials, because they will
run it with theirs. Gemini, Groq, OpenAI, OpenRouter, Ollama and llama.cpp all
speak this same protocol, so the provider is two environment variables and no code
change. Defaults point at Google AI Studio's free tier, which the brief names.

    MODEL_API_KEY    required, never committed
    MODEL_BASE_URL   default: Gemini's OpenAI-compatible endpoint
    MODEL_NAME       default: gemini-3.6-flash

Flash, not Pro, and that is measured rather than preferred: Gemini 2.5 Pro's free
tier allows 5 requests per minute and 50 per day. The eval suite alone is eight
questions across two datasets in two variants - well past 50.

THE CEILING
"Every loop has a ceiling - steps, tokens, and money." A Budget instance carries
all three, refuses the call that would cross a limit, and reports what was spent.
It refuses rather than truncating, because a silently shortened run produces an
answer that looks complete.

REASONING TOKENS ARE INVISIBLE AND THEY DOMINATE. Measured against
gemini-3.6-flash asking for a single word:

    max_tokens  finish   prompt  completion  TOTAL  unaccounted
        20      length      8         0        24       16      -> empty string
       100      stop        8         1       101       92
      1500      stop        8         1       121      112

The model reasons before answering; those tokens count against max_tokens and are
billed inside total_tokens, but appear in NEITHER prompt_tokens NOR
completion_tokens. Two consequences, both handled here:

1. Budget tracks total_tokens. Summing prompt + completion undercounted the real
   spend by 90%, and a ceiling that cannot see the spend is not a ceiling.
2. A tight max_tokens does not produce a short answer, it produces an EMPTY one -
   HTTP 200, finish_reason 'length', completion_tokens 0, no exception. That is
   the exact failure mode this whole exercise is about, so it raises now.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
BASE_POR_DEFECTO = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELO_POR_DEFECTO = "gemini-3.6-flash"


def cargar_env(ruta=None):
    """Read .env into the environment. utf-8-sig because a file written by
    PowerShell carries a BOM, which turns the first key into '\\ufeffMODEL_API_KEY'
    and is invisible in every editor."""
    ruta = Path(ruta) if ruta else RAIZ / ".env"
    if not ruta.exists():
        return False
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return True


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Steps, tokens and money. Refuses the call that would cross a limit."""

    def __init__(self, max_calls=12, max_tokens=200_000, max_usd=0.50):
        self.max_calls, self.max_tokens, self.max_usd = max_calls, max_tokens, max_usd
        self.calls = self.input_tokens = self.output_tokens = self.total_tokens = 0
        self.usd = 0.0

    def check(self):
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"step ceiling reached: {self.calls} model calls")
        if self.total_tokens >= self.max_tokens:
            raise BudgetExceeded(f"token ceiling reached: {self.total_tokens:,}")
        if self.usd >= self.max_usd:
            raise BudgetExceeded(f"cost ceiling reached: ${self.usd:.4f}")

    def record(self, entrada, salida, total, usd):
        self.calls += 1
        self.input_tokens += entrada
        self.output_tokens += salida
        # total, no entrada+salida: los tokens de razonamiento se facturan aqui
        # dentro y no aparecen en ninguno de los otros dos.
        self.total_tokens += max(total, entrada + salida)
        self.usd += usd

    @property
    def reasoning_tokens(self):
        return self.total_tokens - self.input_tokens - self.output_tokens

    def summary(self):
        return {"model_calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "total_tokens": self.total_tokens, "usd": round(self.usd, 6),
                "ceilings": {"calls": self.max_calls, "tokens": self.max_tokens,
                             "usd": self.max_usd}}


def ask(messages, budget, temperature=0.0, max_output_tokens=4000, timeout=60,
        usd_per_m_input=0.0, usd_per_m_output=0.0):
    """One chat completion. Returns text plus what it cost.

    temperature 0 by default: the same question must produce the same routing
    decision twice, or the trace stops being evidence of anything.
    """
    clave = os.environ.get("MODEL_API_KEY")
    if not clave:
        raise RuntimeError(
            "MODEL_API_KEY is not set. Create a .env in the repository root with\n"
            "    MODEL_API_KEY=your-key\n"
            "Get one free at https://aistudio.google.com/apikey — nothing is committed.")

    base = os.environ.get("MODEL_BASE_URL", BASE_POR_DEFECTO).rstrip("/")
    modelo = os.environ.get("MODEL_NAME", MODELO_POR_DEFECTO)
    budget.check()

    def enviar(cuerpo):
        req = urllib.request.Request(
            f"{base}/chat/completions", data=json.dumps(cuerpo).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {clave}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    # "OPENAI-COMPATIBLE" IS NOT ONE PROTOCOL, AND THIS IS MEASURED.
    # NOTES.md claimed a provider swap was two environment variables. Against
    # gpt-5-mini it was two variables and two 400s:
    #
    #   max_tokens    rejected, "use max_completion_tokens instead"
    #   temperature   rejected, "does not support 0.0 with this model"
    #
    # The first is a rename. The second removes a design decision - temperature 0
    # is why the same question routes the same way twice, and on that model it is
    # not on offer. Each adjustment is recorded and travels back with the answer,
    # because a run that could not be deterministic must not look like one that
    # was.
    cuerpo = {"model": modelo, "messages": messages,
              "temperature": temperature, "max_tokens": max_output_tokens}
    ajustes, datos = [], None
    t0 = time.time()
    for _ in range(3):
        try:
            datos = enviar(cuerpo)
            break
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")
            if e.code == 400 and "max_completion_tokens" in detalle and "max_tokens" in cuerpo:
                cuerpo["max_completion_tokens"] = cuerpo.pop("max_tokens")
                ajustes.append("max_tokens renamed to max_completion_tokens")
            elif e.code == 400 and "temperature" in detalle and "temperature" in cuerpo:
                cuerpo.pop("temperature")
                ajustes.append(f"temperature={temperature} refused by this model; the "
                               f"provider default was used and the run is NOT deterministic")
            else:
                raise RuntimeError(f"model call failed ({e.code}): {detalle[:400]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"could not reach {base}: {e.reason}") from None
    if datos is None:
        raise RuntimeError(f"model call failed after adjusting {ajustes}")

    uso = datos.get("usage") or {}
    entrada = uso.get("prompt_tokens", 0)
    salida = uso.get("completion_tokens", 0)
    total = uso.get("total_tokens", entrada + salida)
    # El pensamiento se factura como salida aunque no se reporte como tal.
    usd = entrada / 1e6 * usd_per_m_input + (total - entrada) / 1e6 * usd_per_m_output
    budget.record(entrada, salida, total, usd)

    eleccion = datos["choices"][0]
    texto = (eleccion["message"].get("content") or "").strip()
    razon = eleccion.get("finish_reason")

    # Un 200 con el texto vacio es el peor fallo posible: parece que funciono.
    # Pasa cuando max_tokens no deja sitio despues del razonamiento - medido, para
    # una respuesta de UNA palabra hacen falta mas de 100 tokens.
    if not texto:
        raise RuntimeError(
            f"model returned an empty message (finish_reason={razon!r}, "
            f"{total - entrada} tokens spent past the prompt). "
            + ("max_output_tokens is too low: reasoning consumes it before any text is "
               "written. Measured on gemini-3.6-flash, one word of output needs over 100."
               if razon == "length" else "No text and no length cut - inspect the raw response."))

    return {
        "text": texto, "model": datos.get("model", modelo), "finish_reason": razon,
        "compatibility_adjustments": ajustes,
        "input_tokens": entrada, "output_tokens": salida, "total_tokens": total,
        "reasoning_tokens": total - entrada - salida,
        "usd": round(usd, 6), "seconds": round(time.time() - t0, 2),
    }
