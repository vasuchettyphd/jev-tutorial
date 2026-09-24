"""The "why not just code?" baseline: detect defects with a keyword check
instead of Jev, on the same messages Jev was tested on.

The keyword list and negation rule were written once, as a developer would
before seeing the test messages, and were not tuned to improve the score.
Runs offline: no API key needed.

Usage: python3 keyword_baseline.py
"""
import re
from refund_stress_test import MESSAGES
from defect_reading_test import CASES

KEYWORDS = [
    "broken", "broke", "defective", "defect", "faulty", "damaged", "cracked",
    "doesn't work", "doesnt work", "not working", "stopped working",
    "won't turn on", "wont turn on", "doesn't turn on", "doesnt turn on",
    "dead", "leak", "leaks", "leaking", "snapped", "split", "fell off",
    "came undone", "peeling", "torn", "ripped", "malfunction", "no sound",
    "flickers", "burning", "jams", "stuck",
]
NEGATIONS = ("not", "isn't", "isnt", "never", "no")


def keyword_says_defect(msg):
    text = msg.lower()
    for kw in KEYWORDS:
        for m in re.finditer(r"\b" + re.escape(kw) + r"\b", text):
            before = text[:m.start()].split()[-3:]  # skip "not broken", "isn't defective"
            if not any(w.strip(".,!?") in NEGATIONS for w in before):
                return True
    return False


def score(rows, label):
    ok = 0
    for msg, want in rows:
        hit = keyword_says_defect(msg) == want
        ok += hit
        if label == "tricky":
            print(f"  {'OK ' if hit else 'XX '} want={str(want):5} {msg[:75]}")
    print(f"{label}: {ok}/{len(rows)} correct\n")
    return ok


if __name__ == "__main__":
    plain = [(m, d) for cat in MESSAGES.values() for m, d in cat]
    score(plain, "stress-test messages (plain)")
    score([(m, d) for m, d, _ in CASES], "tricky")
