"""read_document - hand back an internal document whole.

WHERE I DELIBERATELY DID NOT BUILD ANYTHING

This is the tool that could have been a retrieval system, and the brief asks
explicitly where an agent was not used. Meridian ships four documents totalling
under 6 KB - a travel policy, a board memo and two contracts. All four fit in a
prompt several times over.

Chunking them, embedding them and retrieving the top passages would add an
embedding model, a vector store, a similarity threshold and a whole new class of
failure: the paragraph that answers the question ranks fourth and never arrives.
For four short files it buys nothing. They are read whole.

The size guard exists so this decision fails loudly rather than quietly if a
future document pack is larger, instead of silently stuffing a prompt.

WHY THESE DOCUMENTS DECIDE TWO OF THE EIGHT ANSWERS

The FTE question is answered by the board memo saying headcount "is not maintained
in the finance ledger" - which turns a refusal from "I could not find it" into
"your own documentation says it does not live here". And the T&E question is
answered by reading the policy's thresholds and, just as importantly, by noticing
which of its rules these columns cannot test.
"""

from pathlib import Path

LIMITE_KB = 64  # por documento; superado, se devuelve el texto Y un aviso


def read_document(datos_dir, name=None):
    """Return one document whole, or list what is available when name is None."""
    carpeta = Path(datos_dir) / "docs"
    if not carpeta.is_dir():
        return {"result": {"documents": []},
                "notes": [f"No docs folder under {datos_dir}. Any question that depends on "
                          f"policy or contract wording cannot be answered from this dataset."],
                "sql": []}

    disponibles = sorted(p.name for p in carpeta.glob("*.md"))
    if name is None:
        return {"result": {"documents": disponibles},
                "notes": [f"{len(disponibles)} document(s) available. They are read whole; "
                          f"there is no retrieval step."],
                "sql": []}

    ruta = carpeta / name if name.endswith(".md") else carpeta / f"{name}.md"
    if not ruta.exists():
        # Devolver la lista en vez de un error a secas: quien pregunta suele haber
        # escrito mal el nombre, y la lista es la correccion.
        return {"result": {"document": None, "documents": disponibles},
                "notes": [f"'{name}' is not in this document pack. Available: "
                          f"{', '.join(disponibles)}. Nothing was read."],
                "sql": []}

    texto = ruta.read_text(encoding="utf-8")
    kb = len(texto.encode("utf-8")) / 1024
    notas = [f"Read whole, {kb:.1f} KB. No chunking, no retrieval: with a pack this small "
             f"the passage that answers a question cannot rank too low to arrive."]
    if kb > LIMITE_KB:
        notas.append(f"OVER {LIMITE_KB} KB. Read-whole was chosen for a pack of four short "
                     f"files. At this size that decision needs revisiting rather than "
                     f"quietly filling a prompt.")

    return {"result": {"document": ruta.name, "text": texto, "size_kb": round(kb, 1),
                       "documents": disponibles},
            "notes": notas, "sql": []}
