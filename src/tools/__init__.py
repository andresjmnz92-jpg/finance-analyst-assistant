"""The tools. Each one is small, boring, and testable without a model.

Every tool returns a dict with the same three keys, because the trace has to be
legible to someone who did not write this:

    result  what the caller asked for
    notes   anything the caller must not ignore - missing rates, duplicate keys,
            grouping decisions taken. Never empty when something was ambiguous.
    sql     the exact statement and parameters that produced result

No tool raises on ambiguous data. It answers and puts the ambiguity in notes.
Raising would let a caller catch and drop it; a note travels with the answer.
"""
