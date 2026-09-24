"""Test a "good at" claim outside customer support: does a short document
support a claim? Cases are hand-labelled and deliberately tricky: paraphrase,
claims that are contradicted, claims the document never mentions, numbers
that almost match, hedged statements and conditions that aren't met.

Usage: python3 claim_support_test.py
Writes results/claim_support_test.json.
"""
import json, os, concurrent.futures as cf
from jev import ask

SUPPORT_Q = {"type": "noul", "instructions": (
    "Does `document` support `claim`? Answer yes only if the document states the claim "
    "or directly implies it. A claim the document contradicts, doesn't mention, or only "
    "says might be true is not supported.")}

LEASE = ("The tenant may keep one cat or one dog under 20 kg. Rent is due on the 1st of each month "
         "and a late fee of $50 applies after the 5th. The landlord pays for water; the tenant pays "
         "for electricity and internet. Either party may end the lease with 60 days' written notice.")
RELEASE = ("Version 4.2 adds dark mode on Android and iOS. Offline sync, announced for this release, "
           "has moved to 4.3. We fixed a crash when opening PDFs larger than 50 MB. This is the last "
           "version that supports Android 9.")
STUDY = ("In a 12-week trial with 240 adults, the group taking the supplement lost on average 1.1 kg "
         "more than the placebo group. The difference was not statistically significant. Side effects "
         "were mild and similar in both groups. The study was funded by the supplement's manufacturer.")
MENU = ("All mains are served with rice or fries. The vegetable curry is vegan. The lasagne contains "
        "beef and pork. Gluten-free pasta is available on request for a $2 charge. The kitchen closes at 10pm.")

# (document, claim, supported, why it is tricky)
CASES = [
    (LEASE, "A small dog is allowed.", True, "paraphrase of 'dog under 20 kg'"),
    (LEASE, "The tenant can have two cats.", False, "contradicted: one pet"),
    (LEASE, "Paying rent on the 4th incurs no late fee.", True, "implied by 'after the 5th'"),
    (LEASE, "The tenant pays the water bill.", False, "contradicted: landlord pays"),
    (LEASE, "The lease can be ended with one month's notice.", False, "number almost matches"),
    (LEASE, "Smoking is not allowed in the flat.", False, "not mentioned"),
    (RELEASE, "Offline sync ships in 4.2.", False, "announced, then moved"),
    (RELEASE, "Dark mode is available on iPhone in 4.2.", True, "iOS -> iPhone"),
    (RELEASE, "4.2 no longer crashes on a 60 MB PDF.", True, "instance of a general fix"),
    (RELEASE, "Android 9 users can still install 4.2.", True, "'last version that supports'"),
    (RELEASE, "4.2 is faster than 4.1.", False, "not mentioned"),
    (RELEASE, "Offline sync is planned for a later version.", True, "moved to 4.3"),
    (STUDY, "The supplement causes weight loss.", False, "difference not significant"),
    (STUDY, "Participants on the supplement lost about a kilo more on average.", True, "1.1 kg paraphrased"),
    (STUDY, "The trial lasted three months.", True, "12 weeks"),
    (STUDY, "The supplement had no side effects.", False, "mild side effects"),
    (STUDY, "The study was independently funded.", False, "contradicted"),
    (STUDY, "More than 200 people took part.", True, "240"),
    (MENU, "The vegetable curry contains no animal products.", True, "vegan, paraphrased"),
    (MENU, "The lasagne is suitable for someone who doesn't eat pork.", False, "implied contradiction"),
    (MENU, "Gluten-free pasta is free of charge.", False, "$2 charge"),
    (MENU, "You can order food at 10:30pm.", False, "kitchen closes at 10"),
    (MENU, "Every main comes with a side.", True, "rice or fries"),
    (MENU, "The curry is spicy.", False, "not mentioned"),
]


def run(c):
    p = ask({"document": c[0], "claim": c[1]}, {"supported": SUPPORT_Q})["answers"]["supported"]["noul"]
    return c, p


if __name__ == "__main__":
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(run, CASES))
    ok = 0
    for (_, claim, want, why), p in rows:
        hit = (p >= 0.5) == want
        ok += hit
        print(f"  {'OK ' if hit else 'XX '} want={str(want):5} p={p:.2f}  [{why}] {claim[:60]}")
    print(f"\n{ok}/{len(rows)} correct")
    unsure = [p for _, p in rows if 0.2 < p < 0.8]
    print(f"{len(unsure)} answers in the unsure band 0.2-0.8")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "claim_support_test.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump([{"claim": cl, "supported": s, "why": w, "p": p} for (_, cl, s, w), p in rows], f, indent=1)
