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
        self.calls = self.input_tokens = self.output_tokens = 0
        self.usd = 0.0

    def check(self):
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"step ceiling reached: {self.calls} model calls")
        if self.input_tokens + self.output_tokens >= self.max_tokens:
            raise BudgetExceeded(f"token ceiling reached: {self.spent_tokens:,}")
        if self.usd >= self.max_usd:
            raise BudgetExceeded(f"cost ceiling reached: ${self.usd:.4f}")

    def record(self, entrada, salida, usd):
        self.calls += 1
        self.input_tokens += entrada
        self.output_tokens += salida
        self.usd += usd

    @property
    def spent_tokens(self):
        return self.input_tokens + self.output_tokens

    def summary(self):
        return {"model_calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "usd": round(self.usd, 6),
                "ceilings": {"calls": self.max_calls, "tokens": self.max_tokens,
                             "usd": self.max_usd}}


def ask(messages, budget, temperature=0.0, max_output_tokens=1500, timeout=60,
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

    cuerpo = json.dumps({"model": modelo, "messages": messages,
                         "temperature": temperature,
                         "max_tokens": max_output_tokens}).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=cuerpo,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {clave}"})

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            datos = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"model call failed ({e.code}): {detalle}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {base}: {e.reason}") from None

    uso = datos.get("usage") or {}
    entrada = uso.get("prompt_tokens", 0)
    salida = uso.get("completion_tokens", 0)
    usd = entrada / 1e6 * usd_per_m_input + salida / 1e6 * usd_per_m_output
    budget.record(entrada, salida, usd)

    return {
        "text": (datos["choices"][0]["message"].get("content") or "").strip(),
        "model": datos.get("model", modelo),
        "input_tokens": entrada, "output_tokens": salida,
        "usd": round(usd, 6), "seconds": round(time.time() - t0, 2),
    }
