"""Stress-test the one judgment the hybrid approach hands to Jev: reading a
customer message and deciding whether it describes a defect.

Messages are hand-labelled and deliberately tricky: negation, sarcasm, typos,
rambling, defects that were already fixed, defects in something else, other
languages, and messages that mention damage without claiming a defect.

Usage: python3 defect_reading_test.py
Writes results/defect_reading_test.json.
"""
import json, os, concurrent.futures as cf
from jev import ask
from refund_stress_test import DEFECT_Q

# (message, is_defective, why it is tricky)
CASES = [
    # Defective, but phrased to hide it
    ("not gonna lie it's kinda cute but it doesnt actually turn on lol", True, "casual, positive first"),
    ("Wow. Five stars for the packaging. Zero for the product, which is in two pieces.", True, "sarcasm"),
    ("the thingy on the side is supposed to click and it just... doesnt", True, "vague"),
    ("I'm not saying it's broken, but the screen flickers constantly and then goes black.", True, "denies, then describes"),
    ("Bought it for my mom's birthday, she loved the color, we had cake, and then when she plugged it in there was a pop and a burning smell.", True, "rambling, buried"),
    ("heater blows cold air only. set to max. still cold.", True, "terse"),
    ("La cafetera gotea por abajo desde el primer dia.", True, "Spanish: leaks from day one"),
    ("battery goes from 100 to 0 in like 20 min, brand new", True, "performance defect"),
    ("It works, technically, if you hold the cable at exactly the right angle.", True, "sarcastic 'works'"),
    ("Stitching came undone after one gentle wash, followed the care label exactly.", True, "cites correct use"),
    ("The left earbud has no sound. Right one is great.", True, "partial"),
    ("Arrived fine. Two weeks later the handle snapped off while pouring.", True, "starts fine"),
    ("chair creaks and one leg bends when I sit, im 60kg", True, "user rules out misuse"),
    # Not defective, but phrased to look like it
    ("The box was destroyed, looked like it was run over. Item inside is perfect though.", False, "damage to packaging only"),
    ("It broke my heart to return it, it's beautiful, but it doesn't match my couch.", False, "'broke' idiom"),
    ("This thing is killing it, works amazing, I just bought the wrong model.", False, "slang, wrong model"),
    ("Had a problem pairing it at first but I restarted my phone and now it works perfectly.", False, "problem already solved"),
    ("It's too loud for my apartment. Works exactly as advertised.", False, "complaint, not defect"),
    ("The shoes are fine, my feet are the problem. Need a wider size.", False, "self-blame"),
    ("I dropped it down the stairs and now it won't turn on.", False, "customer caused damage"),
    ("My dog chewed through the cable.", False, "customer caused damage"),
    ("It's not defective. I just don't want it anymore.", False, "explicit negation"),
    ("I read reviews saying these break after a month so I'd rather return it before that happens.", False, "hypothetical future defect"),
    ("My last one from you was defective. This one is fine but I've lost trust.", False, "defect was a different item"),
    ("Works great. Returning because I got the same thing as a gift.", False, "duplicate"),
    ("The color is a bit darker than the photo, and it's slower than my old one. Otherwise fine.", False, "mild dislikes"),
    ("Es muy grande para mi cocina, pero funciona bien.", False, "Spanish: too big, works fine"),
    ("scratched it myself moving it, my bad, can i still return?", False, "self-inflicted"),
    ("Instructions were confusing, took me an hour to assemble, but it's solid now.", False, "setup friction"),
    ("It did stop working once, but it was the outlet, not the lamp.", False, "misattributed failure"),
]


def run(c):
    p = ask({"message": c[0]}, {"defect": DEFECT_Q})["answers"]["defect"]["noul"]
    return c, p


if __name__ == "__main__":
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(run, CASES))
    ok = 0
    for (msg, want, why), p in rows:
        hit = (p >= 0.5) == want
        ok += hit
        print(f"  {'OK ' if hit else 'XX '} want={str(want):5} p={p:.2f}  [{why}] {msg[:70]}")
    print(f"\n{ok}/{len(rows)} correct")
    unsure = [p for _, p in rows if 0.2 < p < 0.8]
    print(f"{len(unsure)} answers in the unsure band 0.2-0.8")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "defect_reading_test.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump([{"message": m, "defective": d, "why": w, "p": p} for (m, d, w), p in rows], f, indent=1)
