"""Run the eight questions end to end and judge what a machine can judge.

    python -m evals.eight

WHAT THIS RUNS
Every plan, over both datasets, with no model anywhere: the same `run()` the CLI
uses, which already enforces the declared tool route on every invocation. One
run failing must not silence the others, so each is caught and reported as its
own line - a sweep that dies on the first problem reports one bug and hides
fifteen results.

WHAT IT ASSERTS, AND THE RULE BEHIND IT
Nothing here stores an expected answer. EXPECTED.md set that rule for figures -
"an eval suite that asserts the answer is 4,879,539 passes here and fails
there" - and it holds for statuses too: six of the eight plans compute their
status from whether an FX rate was missing, which is a fact about the data,
not about the plan. So every expectation below is DERIVED from the dataset at
hand, never written down in advance. Against a dataset where nothing is
missing, COMPLETE is the correct status and this suite must agree.

WHAT IT CANNOT JUDGE
Whether the written paragraph carries the caveats well. That is prose, graded
by reading it. This file judges the half a machine can hold still: statuses
coherent with what the tools measured, refusals where the schema forces them,
requirements with a named emitter.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.plans import PLANS                          # noqa: E402
from src.agent.run import run                              # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

# Every plan with the parameters its question needs. Parameters are text,
# like the CLI: '6000' as an integer stops matching a TEXT column.
CASOS = [
    ("cost_per_fte", {"root": "6100"}),
    ("duplicate_payments", {}),
    # No year on purpose: the question does not give one, and declaring that
    # ambiguity is one of the behaviours under test.
    ("consolidated_spend", {"quarter": "3"}),
    # root is the decision the model takes in the full pipeline; this runner is
    # model-free, so the account 'operating expenses' resolves to is fixed here.
    ("opex_by_cost_centre", {"root": "6000", "quarter": "2"}),
    ("spend_comparison", {"root": "6200"}),
    ("largest_vendors", {}),
    ("budget_variance", {}),
    ("policy_breaches", {"root": "6200"}),
]

DATASETS = ["data.db", "fixtures.db"]

LEGALES = {"COMPLETE", "PARTIAL", "REFUSED"}

# The only two statuses stored in advance, because they are structural, not
# data: cost_per_fte refuses on the SCHEMA - no loaded table holds a headcount
# column, and the brief guarantees the second dataset has the same columns -
# and duplicate_payments never touches FX, so it has no PARTIAL to fall into.
# The other six compute their status from the data and are judged by coherence.
ESTRUCTURALES = {"cost_per_fte": "REFUSED", "duplicate_payments": "COMPLETE"}

# Every must_declare entry with a NAMED emitter: the place in a finished trace
# where that requirement is provably met. ARCHITECTURE.md asked for exactly
# this, so a requirement nobody satisfies fails loudly instead of quietly.
# Evidence is structure - findings keys and code-emitted notes - never the
# writer's paragraph; a prose check already failed three times in this repo.
# A plan in CASOS whose requirement has no emitter here is itself a failure.
EMISORES = {
    # cost_per_fte: the refusal must rest on the schema AND name its source.
    "that the denominator is absent":
        lambda t: "denominator_columns_found" in (t["findings"] or {})
        and not t["findings"]["denominator_columns_found"],
    # Key EXISTENCE, not truthiness: an empty list declares that NO document
    # mentions headcount - run.py's own branch for that case, and a legal refusal.
    "the source that says so":
        lambda t: "what_the_documents_say" in (t["findings"] or {}),
    # duplicate_payments: anchored on notes the TOOL emits unconditionally
    # (duplicates.py), the same way guards.py anchors on 'Negative amounts'.
    # Code-emitted strings are stable; the writer's prose is not.
    "the matching criterion":
        lambda t: any(n.startswith("Grouped on") for n in t["all_notes"]),
    "that these are candidates":
        lambda t: any("These are CANDIDATES" in n for n in t["all_notes"]),
    "recurring charges look identical":
        lambda t: any("can be indistinguishable" in n for n in t["all_notes"]),
    # consolidated_spend: three by structure, one by fx.py's own note.
    "which year":
        lambda t: (t["findings"] or {}).get("period"),
    "the FX basis":
        lambda t: any("month-average rate" in n for n in t["all_notes"]),
    # Key EXISTENCE, not truthiness: an empty excluded list is the declaration
    # that nothing was left out, and that is exactly what must be said.
    "what could not be converted":
        lambda t: "excluded" in (t["findings"] or {}),
    "which years can be totalled completely":
        lambda t: "other_years" in (t["findings"] or {}),
    # opex_by_cost_centre. 'which year' is shared and already holds: its
    # evidence lives in the same findings key, period.
    "which date field defines the period":
        lambda t: any("Period assigned by" in n for n in t["all_notes"]),
    "which account the phrase resolved to":
        lambda t: (t["findings"] or {}).get("root"),
    # spend_comparison: the windows finding is published whether or not the
    # chart changed mid-period - one window is also a declaration.
    "account validity windows":
        lambda t: "windows" in (t["findings"] or {}),
    # largest_vendors. Publishing BOTH rankings is the grouping declaration;
    # catch-alls ride the step summary, because the tool returns the
    # catch_all_vendors key unconditionally - empty is also an answer - while
    # its note only fires when the list is non-empty.
    "the vendor grouping applied":
        lambda t: "ungrouped_top" in (t["findings"] or {})
        and "grouping_changed" in (t["findings"] or {}),
    "catch-all vendors":
        lambda t: any(s["tool"] == "normalize_vendors"
                      and any(x.startswith("catch_all_vendors:") for x in s["summary"])
                      for s in t["steps"]),
    "the period covered":
        lambda t: any("names no period" in n or "period covered" in n
                      for n in t["all_notes"]),
    "spend with no vendor":
        lambda t: "unattributed" in (t["findings"] or {}),
    # budget_variance: all four are findings keys the return publishes
    # unconditionally - empty lists when the trap is not in the data, which is
    # itself the declaration that it was looked for and not found.
    "worst by value or by percent":
        lambda t: "worst_by_value" in (t["findings"] or {})
        and "worst_by_percent" in (t["findings"] or {}),
    "two budget sets":
        lambda t: "centres_with_two_sets" in (t["findings"] or {}),
    "unconverted rows by centre":
        lambda t: "excluded" in (t["findings"] or {})
        and "sign_flipped_by_missing_rates" in (t["findings"] or {}),
    "which sign flips because of them":
        lambda t: "sign_flipped_by_missing_rates" in (t["findings"] or {}),
    # policy_breaches: what WAS checked is structure; what was NOT rides the
    # decision run.py emits unconditionally, outside any branch.
    "which policy rules are checkable with these columns":
        lambda t: "rules_checked" in (t["findings"] or {}),
    "which are not":
        lambda t: any("were not checked against these columns" in n
                      for n in t["all_notes"]),
}


def comprobar(nombre, trace, fallos):
    """Every machine-checkable expectation for one finished run.

    The load-bearing rule: status must be COHERENT with the evidence the same
    run published. Six plans decide PARTIAL or COMPLETE from whether FX left
    rows unconverted, and they publish those rows as findings["excluded"] - so
    a COMPLETE with exclusions, or a PARTIAL naming nothing, is a lie whichever
    dataset produced it. That is the check that survives Keyrus's dataset:
    against a full FX grid, COMPLETE is correct and this suite agrees.
    """
    status = trace["status"]
    f = trace["findings"] or {}
    donde = f"{trace['dataset']}/{nombre}"

    if status not in LEGALES:
        fallos.append(f"{donde}: status {status!r} is not one of {sorted(LEGALES)}")
        return
    if nombre in ESTRUCTURALES and status != ESTRUCTURALES[nombre]:
        fallos.append(f"{donde}: {status}, but {ESTRUCTURALES[nombre]} is structural "
                      f"for this plan on any dataset with these columns")
    for requisito in PLANS[nombre]["must_declare"]:
        emisor = EMISORES.get(requisito)
        if emisor is None:
            fallos.append(f"{donde}: '{requisito}' has no named emitter in EMISORES - "
                          f"a requirement nobody checks is satisfied by luck")
        elif not emisor(trace):
            fallos.append(f"{donde}: '{requisito}' is declared in plans.py but its "
                          f"evidence is nowhere in the trace")
    if status == "REFUSED":
        if not f.get("reason"):
            fallos.append(f"{donde}: refused without naming a reason - a silent "
                          f"refusal is as unanswerable as a silent total")
        return
    excluido = f.get("excluded")
    if status == "COMPLETE" and excluido:
        fallos.append(f"{donde}: says COMPLETE while {len(excluido)} group(s) "
                      f"were left unconverted in its own findings")
    if status == "PARTIAL" and not excluido:
        fallos.append(f"{donde}: says PARTIAL but its findings name nothing "
                      f"that is missing")


def main():
    faltan = [d for d in DATASETS if not (RAIZ / d).exists()]
    if faltan:
        sys.exit(f"missing {', '.join(faltan)}. Build them first:\n"
                 f"  python -m src.load\n  python -m src.load evals/fixtures")

    fallos, corridas = [], 0
    for db in DATASETS:
        con = sqlite3.connect(RAIZ / db)
        for nombre, params in CASOS:
            antes = len(fallos)
            try:
                trace = run(nombre, con, dataset=db, **params).as_dict()
                comprobar(nombre, trace, fallos)
                estado = trace["status"]
            except Exception as e:            # noqa: BLE001 - one run, one line
                fallos.append(f"{db}/{nombre}: {type(e).__name__}: {e}")
                estado = "CRASHED"
            corridas += 1
            print(f"  {db:14s} {nombre:22s} {estado:9s} "
                  f"{'ok' if len(fallos) == antes else 'FAIL'}")
        con.close()

    print(f"\n{len(CASOS)} plan(s) x {len(DATASETS)} dataset(s), "
          f"{corridas} run(s), {len(fallos)} failure(s).")
    if fallos:
        print("\nFAIL:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS - every expectation above was derived from the dataset, none stored.")


if __name__ == "__main__":
    main()
