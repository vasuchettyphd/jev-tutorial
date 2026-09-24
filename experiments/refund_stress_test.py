"""Stress-test Jev on rule-based refund routing.

Generates random refund cases under a multi-rule policy, computes the correct
outcome in code, and asks Jev three ways:

  A. raw        - Jev gets purchase dates and item prices, so it must do the
                  date math, the totals, the rules, and read the message.
  B. prepped    - code precomputes days_since_purchase and order_total; Jev
                  still applies the rules and reads the message.
  C. hybrid     - Jev only answers "does the message describe a defect?";
                  code applies every rule.

Usage: python3 refund_stress_test.py [n_cases] [seed]
Writes results/refund_stress_test.json.
"""
import json, os, random, sys, time, urllib.request, concurrent.futures as cf
from datetime import date, timedelta

KEY = os.environ["OPENROUTER_API_KEY"]
TODAY = date(2026, 9, 24)


def ask(state, questions, tries=4):
    body = json.dumps({"model": "typesafe/jev-1.13", "state": state, "questions": questions}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=body,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


POLICY = """Refund policy. Apply the rules in order; the first rule that matches decides.
1. Final-sale items are never refunded (DENY) unless the item is defective.
2. Defective items may be refunded up to 365 days after purchase, whatever the tier or category.
3. Otherwise the return window depends on customer tier: standard 30 days, silver 45 days, gold 60 days, platinum 90 days.
4. Electronics have a shorter window: 15 days for every tier, except platinum customers who get 30 days.
5. A request outside its window is DENY.
6. A refundable request is routed by order total (sum of price x qty over all items):
   under $100 -> AUTO_REFUND; $100 up to $499.99 -> MANAGER; $500 or more -> FINANCE.
A change of mind, wrong size, damaged packaging with a working item, or damage the customer caused is not a defect."""

OUTCOMES = {
    "AUTO_REFUND": "Refund automatically",
    "MANAGER": "Refundable, needs manager approval",
    "FINANCE": "Refundable, needs finance approval",
    "DENY": "Not refundable under the policy",
}

# (message, is_defective). Mix of plain, slangy, sarcastic, and deliberately misleading.
MESSAGES = [
    ("It stopped charging after four days.", True),
    ("Arrived with a cracked screen, straight out of the box.", True),
    ("The seam split the first time I wore it.", True),
    ("Doesn't turn on at all. Tried three outlets.", True),
    ("worked for like a day then nothing, no lights no sound", True),
    ("The zipper jams every single time I use it.", True),
    ("Oh fantastic, a blender that doesn't blend. Love that for me.", True),
    ("One of the legs is shorter than the others so it wobbles, clearly made wrong.", True),
    ("Paint started peeling off within a week of normal use.", True),
    ("The box was crushed in shipping but the lamp itself works fine.", False),
    ("I changed my mind, I don't need it anymore.", False),
    ("Wrong size, it's too small for me.", False),
    ("Honestly it works great, it's just not what I pictured.", False),
    ("Found it cheaper somewhere else.", False),
    ("My partner already bought one, so we have two now.", False),
    ("It's not broken or anything, I just never used it.", False),
    ("The color looked different online. Nothing wrong with it though.", False),
    ("It's heavier than I expected and I can't lift it easily.", False),
]

CATALOG = {
    "apparel": [("jacket", 89.0), ("jeans", 49.5), ("sneakers", 120.0), ("t-shirt", 19.99)],
    "home": [("lamp", 34.5), ("blender", 79.0), ("rug", 210.0), ("chair", 145.0)],
    "electronics": [("headphones", 199.0), ("charger", 24.99), ("tablet", 449.0), ("speaker", 99.99)],
}
TIERS = {"standard": 30, "silver": 45, "gold": 60, "platinum": 90}


def window(tier, category):
    if category == "electronics":
        return 30 if tier == "platinum" else 15
    return TIERS[tier]


def truth(case):
    days, total = case["days"], case["total"]
    if case["final_sale"] and not case["defective"]:
        return "DENY"
    limit = 365 if case["defective"] else window(case["tier"], case["category"])
    if days > limit:
        return "DENY"
    return "AUTO_REFUND" if total < 100 else "MANAGER" if total < 500 else "FINANCE"


def make_case(rng):
    tier = rng.choice(list(TIERS))
    category = rng.choice(list(CATALOG))
    msg, defective = rng.choice(MESSAGES)
    final_sale = rng.random() < 0.2
    items = []
    for _ in range(rng.choice([1, 1, 2, 3])):
        name, price = rng.choice(CATALOG[category])
        items.append({"name": name, "price_usd": price, "qty": rng.choice([1, 1, 1, 2, 3])})
    total = round(sum(i["price_usd"] * i["qty"] for i in items), 2)
    # Half the cases sit within 3 days of the edge that applies to them.
    edge = 365 if defective else window(tier, category)
    days = edge + rng.randint(-3, 3) if rng.random() < 0.5 else rng.randint(1, 400)
    days = max(days, 1)
    case = {"tier": tier, "category": category, "final_sale": final_sale, "defective": defective,
            "message": msg, "items": items, "total": total, "days": days,
            "purchased": (TODAY - timedelta(days=days)).isoformat()}
    case["edge"] = edge
    case["near_day_edge"] = abs(days - edge) <= 3 and not (final_sale and not defective)
    case["near_total_edge"] = min(abs(total - 100), abs(total - 500)) <= 10
    case["truth"] = truth(case)
    return case


ROUTE_Q = {"type": "choice", "instructions": "Apply `policy` to this refund request. What is the outcome?",
           "criteria": OUTCOMES}
DEFECT_Q = {"type": "noul", "instructions": (
    "Does `message` say the item is defective, broken, or does not work as intended? "
    "Change of mind, wrong size, damaged packaging with a working item, or damage the customer caused do not count.")}


def order_raw(c):
    return {"customer_tier": c["tier"], "category": c["category"], "final_sale": c["final_sale"],
            "purchased": c["purchased"], "items": c["items"]}


def order_prepped(c):
    return {"customer_tier": c["tier"], "category": c["category"], "final_sale": c["final_sale"],
            "days_since_purchase": c["days"], "order_total_usd": c["total"]}


def run(c):
    a = ask({"policy": POLICY, "today": TODAY.isoformat(), "order": order_raw(c),
             "message": c["message"]}, {"route": ROUTE_Q})["answers"]["route"]
    b = ask({"policy": POLICY, "order": order_prepped(c), "message": c["message"]},
            {"route": ROUTE_Q})["answers"]["route"]
    d = ask({"message": c["message"]}, {"defect": DEFECT_Q})["answers"]["defect"]["noul"]
    hybrid = truth({**c, "defective": d >= 0.5})
    return {**c,
            "raw": {"choice": a["choice"], "conf": a["confidence"]},
            "prepped": {"choice": b["choice"], "conf": b["confidence"]},
            "hybrid": {"choice": hybrid, "defect_p": d}}


def pct(ok, n):
    return f"{ok}/{n} ({100 * ok / n:.0f}%)" if n else "-"


def report(rows):
    def acc(rows, v):
        return pct(sum(r[v]["choice"] == r["truth"] for r in rows), len(rows))

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
        print(f"{name:32} {acc(g, 'raw'):>14} {acc(g, 'prepped'):>14} {acc(g, 'hybrid'):>14}")
    print("\nDoes confidence warn you? (accuracy within each confidence band)")
    for v in ("raw", "prepped"):
        for lo, hi in ((0.95, 1.01), (0.8, 0.95), (0, 0.8)):
            g = [r for r in rows if lo <= r[v]["conf"] < hi]
            print(f"  {v:8} conf {lo:.2f}-{min(hi, 1):.2f}: {pct(sum(r[v]['choice'] == r['truth'] for r in g), len(g)):>14}"
                  f"  ({len(g)} cases)")
        cw = [r for r in rows if r[v]["conf"] >= 0.9 and r[v]["choice"] != r["truth"]]
        print(f"  {v:8} wrong with confidence >= 0.90: {len(cw)}")
    defect_ok = sum((r["hybrid"]["defect_p"] >= 0.5) == r["defective"] for r in rows)
    print(f"\nHybrid defect reading: {pct(defect_ok, len(rows))}")
    print("\nSample misses (raw):")
    for r in [r for r in rows if r["raw"]["choice"] != r["truth"]][:8]:
        print(f"  want={r['truth']:11} got={r['raw']['choice']:11} conf={r['raw']['conf']:.2f} "
              f"{r['tier']:8} {r['category']:11} fs={int(r['final_sale'])} def={int(r['defective'])} "
              f"{r['days']:3}d (edge {r['edge']}) ${r['total']}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    cases = [make_case(rng) for _ in range(n)]
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(run, cases))
    os.makedirs(os.path.join(os.path.dirname(__file__) or ".", "results"), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__) or ".", "results", "refund_stress_test.json"), "w") as f:
        json.dump(rows, f, indent=1)
    report(rows)
