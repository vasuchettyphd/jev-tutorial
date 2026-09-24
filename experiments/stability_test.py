"""Check TypeSafe's claim that Jev gives stable answers across repeated runs:
ask the 30 tricky defect questions several times and see how much the
probabilities move and whether any yes/no answer flips.

Usage: python3 stability_test.py [runs]    (default 5 runs, 150 calls)
Writes results/stability_test.json.
"""
import json, os, sys, concurrent.futures as cf
from defect_reading_test import CASES, run


def spread(ps):
    return max(ps) - min(ps)


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    if not 2 <= runs <= 20:
        sys.exit("runs must be between 2 and 20")
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(run, CASES * runs))
    probs = {c[0]: [] for c in CASES}
    for (msg, _, _), p in rows:
        probs[msg].append(p)

    flips = 0
    for msg, want, why in CASES:
        ps = probs[msg]
        flipped = len({p >= 0.5 for p in ps}) > 1
        flips += flipped
        print(f"  {'FLIP' if flipped else '    '} spread={spread(ps):.2f} "
              f"p={' '.join(f'{p:.2f}' for p in ps)}  {msg[:55]}")
    spreads = sorted(spread(probs[c[0]]) for c in CASES)
    print(f"\n{runs} runs of {len(CASES)} messages")
    print(f"yes/no answer changed between runs: {flips}/{len(CASES)} messages")
    print(f"probability spread: median {spreads[len(spreads) // 2]:.2f}, max {spreads[-1]:.2f}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "stability_test.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump([{"message": m, "defective": d, "why": w, "p": probs[m]} for m, d, w in CASES], f, indent=1)
