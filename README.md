# Jev: what it's good at and what it isn't

A short, hands-on guide to [TypeSafe Jev 1.13](https://openrouter.ai/typesafe/jev-1.13) accessed through OpenRouter. Every claim below comes from live calls (about 30 of them, total cost under one cent). The scripts in [`experiments/`](experiments/) reproduce them.

## What Jev is

Jev doesn't write text. You give it some input text (the **state**) and a set of **questions**, each with a fixed list of possible answers. It returns the answers with probabilities.

| Type | Example | Returns |
|---|---|---|
| **choice** | Which team handles this? billing / shipping / account | `"billing"`, a probability for each option, and a confidence |
| **score** | How angry is this customer, on a 0-2 scale you define? | `1.4` |
| **noul** | Does this ask for a refund? | `0.99`, the probability that the answer is yes |

**A comparison that might help:** Jev is like an experienced mailroom clerk. Show them an envelope and they'll tell you at a glance which department it goes to. Don't ask them to work out whether the invoice inside is 31 days overdue under clause 4(b), even though they'll usually get that right too.

## Routing without logic (ticket triage): very good

This is its strength: reading messy human text and recognising what it's about.

```
OK  billing   conf=1.00  "Oh great, ANOTHER month paying for a plan I cancelled. Love it."
OK  shipping  conf=1.00  "my thing hasnt showed up and its been 2 weeks, where is it"
OK  account   conf=1.00  "Someone changed my email address without me knowing"
OK  product   conf=1.00  "The dashboard chart shows blank since the update"
-> 8/8, including the sarcastic one and the one full of typos
```

## Routing with logic (rules over facts): usually right, and wrong exactly where it matters

I gave it a refund policy: under $100 and within 30 days means auto-refund, $100 or more means a manager approves, older than 30 days means deny, and gold-tier customers get 60 days. Then I asked it for the outcome directly:

```
OK  $45    14d standard  -> AUTO_REFUND  conf=1.00
OK  $45    50d gold      -> AUTO_REFUND  conf=0.79   (applied the gold exception)
XX  $100   31d standard  -> MANAGER      conf=0.97   <- should be DENY, and it was 97% sure
```

It got 7 of 8 right. The miss was one day past the limit, and it was confidently wrong. Pure computation showed the same pattern:

```
XX  log has 3 "fail" entries - "more than 3?"  -> p=0.84 yes   (wrong)
OK  prices sum to 101 - "over 100?"            -> p=0.75       (right, but unsure)
```

Its errors cluster right at the thresholds, which is where the rule makes a difference. In this small test, confidence didn't always warn about them. The stress test below uses far more cases.

## Stress test: 300 cases, a much harder policy

Eight cases is a small sample, so I scaled it up ([`refund_stress_test.py`](experiments/refund_stress_test.py)). The policy now has six rules that interact:

1. Final-sale items are never refunded, unless defective.
2. Defective items can be refunded for up to 365 days.
3. Return windows by tier: standard 30 days, silver 45, gold 60, platinum 90.
4. Electronics get 15 days (platinum customers get 30).
5. Anything outside its window is denied.
6. Refundable requests are routed by order total: under $100 is AUTO_REFUND, $100-$499.99 goes to MANAGER, $500 or more goes to FINANCE.

Each case has a customer tier, a category, a final-sale flag, 1-3 items with quantities, a purchase date, and a customer message that may or may not describe a defect. Half the cases sit within 3 days of their window edge, which is where the earlier test failed. Code computes the correct answer for every case, and Jev is asked three ways:

- **A. Raw:** Jev gets purchase dates and item prices, so it has to do the date math, add up the total, apply the rules and read the message.
- **B. Prepped:** code works out `days_since_purchase` and `order_total_usd`. Jev still applies the rules and reads the message.
- **C. Hybrid:** Jev only answers "does this message describe a defect?" and code applies every rule.

```
                                  A raw          B prepped      C hybrid
all cases                         187/300 (62%)  245/300 (82%)  300/300 (100%)
far from any edge                 127/153 (83%)  142/153 (93%)  153/153 (100%)
within 3 days of window edge       52/134 (39%)   94/134 (70%)  134/134 (100%)
total within $10 of $100/$500      17/28 (61%)    20/28 (71%)    28/28 (100%)
final-sale                         43/58 (74%)    52/58 (90%)    58/58 (100%)
defective                          99/168 (59%)  121/168 (72%)  168/168 (100%)
electronics                        58/91 (64%)    75/91 (82%)    91/91 (100%)
```

What the harder test shows:

- **Stacked rules drag accuracy down fast.** It went from 7/8 on the simple policy to 62% here. Near a window edge it drops to 39%, which is worse than a coin flip between two outcomes.
- **Doing the arithmetic in code is worth about 20 points on its own** (62% to 82%), even though Jev still has to apply the rules.
- **The hybrid scored 100%, because the only thing Jev decided was what it's good at.** The rules themselves are just `if` statements.

### The good news: at scale, confidence is honest

With 300 cases, confidence turned out to be a reliable filter:

```
                   answers with confidence >= 0.9   accuracy
A raw              32/300  (11%)                    32/32  (100%)
B prepped         110/300  (37%)                   110/110 (100%)
B prepped, >= 0.8 165/300  (55%)                   160/165 (97%)
```

Jev mostly *knows* when it's struggling: 246 of the 300 raw answers had confidence under 0.8. So "act only above 0.9, otherwise escalate" would have made no mistakes on this run. It still isn't a guarantee: the small test above had one answer that was 97% confident and wrong, and an earlier 300-case run had one miss at 0.9 or above. Pick your threshold from your own data and the cost of a mistake.

### Stress-testing the part Jev does in the hybrid

The hybrid only works if Jev reads messages correctly, and the stress test used just 18 fairly plain messages. So [`defect_reading_test.py`](experiments/defect_reading_test.py) throws 32 deliberately tricky, hand-labelled ones at it:

```
OK  p=0.96  "Wow. Five stars for the packaging. Zero for the product, which is in two pieces."
OK  p=0.95  "La cafetera gotea por abajo desde el primer dia."          (Spanish: leaks)
OK  p=0.75  "It works, technically, if you hold the cable at exactly the right angle."
OK  p=0.02  "It broke my heart to return it, it's beautiful, but it doesn't match my couch."
OK  p=0.10  "It did stop working once, but it was the outlet, not the lamp."
OK  p=0.39  "I dropped it down the stairs and now it won't turn on."   (customer's fault)
XX  p=0.64  "My last one from you was defective. This one is fine but I've lost trust."
XX  p=0.12  "Not what I expected: it's missing the power adapter that the listing says is included."
```

It got 30/32 right. It handled sarcasm, idioms, Spanish, buried details and problems that had already been fixed. The two misses are both honest edge cases: a defect that belonged to a *different* item, and a missing part, which arguably isn't a "defect" under my wording at all. Six answers landed in the unsure 0.2-0.8 band, which is exactly the queue a human would review.

## The rule of thumb: Jev reads, code decides

```python
# Let Jev turn messy text into facts:
ans = jev(state={"ticket": msg}, questions={
    "wants_refund": {"type": "noul", "instructions": "Does `ticket` request a refund?"},
    "team": {"type": "choice", ...},
})
# Apply the rules in plain code:
days = (today - order.purchased).days
limit = 60 if customer.tier == "gold" else 30
if ans["wants_refund"] > 0.7 and days <= limit:
    route = "AUTO_REFUND" if order.total < 100 else "MANAGER"
```

| Good at (let Jev do it) | Bad at (keep in code) |
|---|---|
| Intent and topic routing | Dates, sums, counts, thresholds |
| Sentiment, urgency, frustration scores | Rules with exact cutoffs |
| Yes/no facts about text ("mentions an order ID?", "asks for a password?") | Anything needing an exact answer |
| Checking whether a document supports a claim | Writing replies, summaries or code; it can't generate text |
| Many narrow questions at once, in one cheap call | Open-ended "figure out what to do" work |

## Other things I found

- **Always add an `other` / `unclear` option.** It has to pick one of your options, so "hi" was routed to `product` with 0.71 confidence.
- **Messages about two things get squashed into one label.** "Arrived broken AND you charged me twice" came back as billing at 0.99. If a message can be about several things, ask a separate yes/no question per team rather than one choice.
- **Use confidence as a filter.** A good pattern: if confidence is below about 0.8, send the ticket to a human or a smarter LLM. Tune that threshold on your own data.
- **Ask narrow questions.** "Is this spam?" works worse than 5 small yes/no questions combined in code. That's [TypeSafe's own top recommendation](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).
- **Cost:** about $0.000015 per call (around 350 input tokens), so roughly 70,000 triage calls per dollar.

## How to call it

OpenRouter's normal chat endpoint rejects Jev. It uses its own endpoint, which is labelled alpha, so it may change:

```bash
curl https://openrouter.ai/api/alpha/decisions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"typesafe/jev-1.13","state":"I was charged twice, refund me",
       "questions":{"team":{"type":"choice","instructions":"Which team?",
                    "criteria":{"billing":"charges, refunds","shipping":"delivery"}}}}'
```

Response:

```json
{"answers":{"team":{"type":"choice","choice":"billing",
  "probabilities":{"billing":1,"shipping":0},"confidence":1}},
 "usage":{"input_tokens":352,"output_tokens":55,"cost":0.000014784}}
```

## Run the experiments

Needs Python 3 (standard library only) and `OPENROUTER_API_KEY` in your environment.

```bash
cd experiments
python3 triage_vs_logic.py            # triage vs rule-based refund routing
python3 ambiguity_and_computation.py  # ambiguous tickets, sums, counts, dates, multi-hop
python3 refund_stress_test.py 300 7   # 300 random cases, seed 7; writes results/refund_stress_test.json
python3 defect_reading_test.py        # 32 tricky hand-labelled customer messages
```

The stress test makes 3 calls per case (900 for 300 cases). At about $0.00003 per call, that comes to a few cents.

TypeSafe designs Jev to give stable answers across repeated runs, but exact numbers may shift between model versions.

## Further reading

- [TypeSafe docs index](https://docs.typesafe.ai/llms.txt)
- [How to build with TypeSafe](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)
- [Intent routing pattern](https://docs.typesafe.ai/patterns/intent-routing)
- [Confidence](https://docs.typesafe.ai/confidence)
