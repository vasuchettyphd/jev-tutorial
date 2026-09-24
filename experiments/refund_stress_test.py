"""Stress-test Jev on rule-based refund routing.

Generates random refund cases under a multi-rule policy, computes the correct
outcome in code, and asks Jev three ways:

  A. raw        - Jev gets purchase dates and item prices, so it must do the
                  date math, the totals, the rules, and read the message.
  B. prepped    - code precomputes days_since_purchase and order_total; Jev
                  still applies the rules and reads the message.
  C. hybrid     - Jev only answers "does the message describe a defect?";
                  code applies every rule.

Usage: python3 refund_stress_test.py [n_cases] [seed]     (defaults: 300 7)
Each case makes 3 calls. Writes results/refund_stress_test_seed<seed>.json.
"""
import json, os, random, sys, concurrent.futures as cf
from datetime import date, timedelta
from jev import ask

TODAY = date(2026, 9, 24)
MAX_CASES = 1000  # 3 calls per case; guards against a typo like 15000

POLICY = """Refund policy.
Step 1. Final-sale items are never refunded (DENY) unless the item is defective.
Step 2. Find the return window:
  - Defective items: 365 days, whatever the tier or category.
  - Electronics that are not defective: 15 days for every tier, except platinum customers who get 30 days.
  - Everything else: standard 30 days, silver 45 days, gold 60 days, platinum 90 days.
  A request on the last day of the window is still inside it.
Step 3. A request outside its window is DENY.
Step 4. Route a refundable request by order total (sum of price x qty over all items):
  under $100 -> AUTO_REFUND; $100 up to $499.99 -> MANAGER; $500 or more -> FINANCE.
A change of mind, wrong size, damaged packaging with a working item, or damage the customer caused is not a defect."""

OUTCOMES = {
    "AUTO_REFUND": "Refund automatically",
    "MANAGER": "Refundable, needs manager approval",
    "FINANCE": "Refundable, needs finance approval",
    "DENY": "Not refundable under the policy",
}

CATALOG = {
    "apparel": [("jacket", 89.0), ("jeans", 49.5), ("sneakers", 120.0), ("t-shirt", 19.99)],
    "home": [("lamp", 34.5), ("blender", 79.0), ("rug", 210.0), ("chair", 145.0)],
    "electronics": [("headphones", 199.0), ("charger", 24.99), ("tablet", 449.0), ("speaker", 99.99)],
}

# Messages that fit each category: (message, is_defective). Mix of plain, slangy,
# sarcastic, and deliberately misleading phrasings. 36 distinct messages.
MESSAGES = {
    "apparel": [
        ("The seam split the first time I wore it.", True),
        ("The zipper jams every single time I use it.", True),
        ("Stitching came undone after one gentle wash, followed the care label.", True),
        ("The dye bled all over my other clothes on a cold wash.", True),
        ("A button fell off the first day, the thread was barely attached.", True),
        ("Sole started peeling away from the shoe after a week of normal walking.", True),
        ("Wrong size, it's too small for me.", False),
        ("The color looked different online. Nothing wrong with it though.", False),
        ("I changed my mind, I don't need it anymore.", False),
        ("It broke my heart to return it but it doesn't go with anything I own.", False),
        ("Found it cheaper somewhere else.", False),
        ("snagged it on a fence while hiking, my fault, can i still return", False),
    ],
    "home": [
        ("One of the legs is shorter than the others so it wobbles, clearly made wrong.", True),
        ("Oh fantastic, a blender that doesn't blend. Love that for me.", True),
        ("Paint started peeling off within a week of normal use.", True),
        ("The lamp flickers and buzzes no matter which bulb I use.", True),
        ("Motor smells like burning after 30 seconds on low.", True),
        ("Rug is shedding clumps everywhere after one vacuum.", True),
        ("The box was crushed in shipping but the lamp itself works fine.", False),
        ("Honestly it works great, it's just not what I pictured.", False),
        ("My partner already bought one, so we have two now.", False),
        ("It's heavier than I expected and I can't lift it easily.", False),
        ("It's not broken or anything, I just never used it.", False),
        ("My dog chewed one of the chair legs.", False),
    ],
    "electronics": [
        ("It stopped charging after four days.", True),
        ("Arrived with a cracked screen, straight out of the box.", True),
        ("Doesn't turn on at all. Tried three outlets.", True),
        ("worked for like a day then nothing, no lights no sound", True),
        ("Left earbud has no sound, right one is fine.", True),
        ("battery goes from 100 to 0 in like 20 min, brand new", True),
        ("Had trouble pairing at first but after a restart it works perfectly.", False),
        ("It's too loud for my apartment. Works exactly as advertised.", False),
        ("I dropped it down the stairs and now it won't turn on.", False),
        ("Bought the wrong model, this one works fine but isn't compatible with my laptop.", False),
        ("Got the same thing as a gift so I don't need this one.", False),
        ("The packaging was torn open but everything inside works.", False),
    ],
}
TIERS = {"standard": 30, "silver": 45, "gold": 60, "platinum": 90}


def window(tier, category, defective):
    if defective:
        return 365
    if category == "electronics":
        return 30 if tier == "platinum" else 15
    return TIERS[tier]


def truth(case):
    if case["final_sale"] and not case["defective"]:
        return "DENY"
    if case["days"] > window(case["tier"], case["category"], case["defective"]):
        return "DENY"
    total = case["total"]
    return "AUTO_REFUND" if total < 100 else "MANAGER" if total < 500 else "FINANCE"


def make_case(rng):
    tier = rng.choice(list(TIERS))
    category = rng.choice(list(CATALOG))
    msg, defective = rng.choice(MESSAGES[category])
    final_sale = rng.random() < 0.2
    items = []
    for _ in range(rng.choice([1, 1, 2, 3])):
        name, price = rng.choice(CATALOG[category])
        items.append({"name": name, "price_usd": price, "qty": rng.choice([1, 1, 1, 2, 3])})
    total = round(sum(i["price_usd"] * i["qty"] for i in items), 2)
    # Half the cases sit within 3 days of the edge that applies to them.
    edge = window(tier, category, defective)
    days = edge + rng.randint(-3, 3) if rng.random() < 0.5 else rng.randint(1, 400)
    days = max(days, 1)
    case = {"tier": tier, "category": category, "final_sale": final_sale, "defective": defective,
            "message": msg, "items": items, "total": total, "days": days, "edge": edge,
            "purchased": (TODAY - timedelta(days=days)).isoformat()}
    case["truth"] = truth(case)
    # Edge buckets only count cases where that edge actually decides the outcome.
    window_matters = not (final_sale and not defective)
    case["near_day_edge"] = window_matters and abs(days - edge) <= 3
    case["near_total_edge"] = case["truth"] != "DENY" and min(abs(total - 100), abs(total - 500)) <= 10
    return case


ROUTE_Q = {"type": "choice", "instructions": "Apply `policy` to this refund request. What is the outcome?",
           "criteria": OUTCOMES}
DEFECT_Q = {"type": "noul", "instructions": (
    "Does `message` say the item is defective, broken, or does not work as intended? "
    "Change of mind, wrong size, damaged packaging with a working item, "
    "or damage the customer caused do not count.")}


def order_raw(c):
    return {"customer_tier": c["tier"], "category": c["category"], "final_sale": c["final_sale"],
            "purchased": c["purchased"], "items": c["items"]}


def order_prepped(c):
    return {"customer_tier": c["tier"], "category": c["category"], "final_sale": c["final_sale"],
            "days_since_purchase": c["days"], "order_total_usd": c["total"]}


def run(c):
    try:
        a = ask({"policy": POLICY, "today": TODAY.isoformat(), "order": order_raw(c),
                 "message": c["message"]}, {"route": ROUTE_Q})["answers"]["route"]
        b = ask({"policy": POLICY, "order": order_prepped(c), "message": c["message"]},
                {"route": ROUTE_Q})["answers"]["route"]
        d = ask({"message": c["message"]}, {"defect": DEFECT_Q})["answers"]["defect"]["noul"]
    except Exception as e:  # keep the rest of the run; report the failure
        return {**c, "error": f"{type(e).__name__}: {e}"}
    return {**c,
            "raw": {"choice": a["choice"], "conf": a["confidence"]},
            "prepped": {"choice": b["choice"], "conf": b["confidence"]},
            "hybrid": {"choice": truth({**c, "defective": d >= 0.5}), "defect_p": d}}


def pct(ok, n):
    return f"{ok}/{n} ({100 * ok / n:.0f}%)" if n else "-"


def correct(r, v):
    return r[v]["choice"] == r["truth"]


def report(rows):
    groups = {
        "all cases": rows,
        "far from any edge": [r for r in rows if not r["near_day_edge"] and not r["near_total_edge"]],
        "within 3 days of window edge": [r for r in rows if r["near_day_edge"]],
        "total within $10 of $100/$500": [r for r in rows if r["near_total_edge"]],
        "final-sale": [r for r in rows if r["final_sale"]],
        "defective": [r for r in rows if r["defective"]],
        "electronics": [r for r in rows if r["category"] == "electronics"],
    }
    print(f"{'':32} {'A raw':>14} {'B prepped':>14} {'C hybrid':>14}")
    for name, g in groups.items():
        cells = [pct(sum(correct(r, v) for r in g), len(g)) for v in ("raw", "prepped", "hybrid")]
        print(f"{name:32} {cells[0]:>14} {cells[1]:>14} {cells[2]:>14}")

    n = len(rows)
    print("\nConfidence gate: act only when confidence >= threshold")
    print(f"  {'':10} {'threshold':>9} {'answers kept':>16} {'accuracy of kept':>18}")
    for v in ("raw", "prepped"):
        for t in (0.8, 0.9, 0.95):
            g = [r for r in rows if r[v]["conf"] >= t]
            print(f"  {v:10} {t:>9} {pct(len(g), n):>16} {pct(sum(correct(r, v) for r in g), len(g)):>18}")
    for v in ("raw", "prepped"):
        low = sum(r[v]["conf"] < 0.8 for r in rows)
        print(f"  {v}: {low}/{n} answers had confidence below 0.8")

    msgs = {r["message"]: r["hybrid"]["defect_p"] >= 0.5 for r in rows}
    truths = {m: d for cat in MESSAGES.values() for m, d in cat}
    print(f"\nHybrid defect reading: {sum(msgs[m] == truths[m] for m in msgs)}/{len(msgs)} "
          f"distinct messages read correctly")

    print("\nSample misses (prepped):")
    for r in [r for r in rows if not correct(r, "prepped")][:8]:
        print(f"  want={r['truth']:11} got={r['prepped']['choice']:11} conf={r['prepped']['conf']:.2f} "
              f"{r['tier']:8} {r['category']:11} fs={int(r['final_sale'])} def={int(r['defective'])} "
              f"{r['days']:3}d (window {r['edge']}) ${r['total']}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    if not 1 <= n <= MAX_CASES:
        sys.exit(f"n_cases must be 1-{MAX_CASES} (each case makes 3 paid calls)")
    rng = random.Random(seed)
    cases = [make_case(rng) for _ in range(n)]
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(run, cases))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                       f"refund_stress_test_seed{seed}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rows, f, indent=1)
    failed = [r for r in rows if "error" in r]
    if failed:
        print(f"{len(failed)} cases failed and are excluded; first error: {failed[0]['error']}")
    report([r for r in rows if "error" not in r])
