# Jev: what it's good at and what it isn't

A short, hands-on guide to [TypeSafe Jev 1.13](https://openrouter.ai/typesafe/jev-1.13) accessed through OpenRouter. The results below come from about 960 live calls, costing a few cents in total. Where a claim comes from TypeSafe's docs instead, or hasn't been tested yet, the text says so. The scripts in [`experiments/`](experiments/) reproduce everything.

## What Jev is

Jev doesn't write text. You give it some input text (the **state**) and a set of **questions**, each with a fixed list of possible answers. It returns the answers with probabilities.

| Type | Example | Returns |
|---|---|---|
| **choice** | Which team handles this? billing / shipping / account | `"billing"`, a probability for each option, and a confidence |
| **score** | How angry is this customer, on a 0-2 scale you define? | `1.4` (an illustration: score questions aren't tested in this guide yet) |
| **noul** (yes/no) | Does this ask for a refund? | `0.99`, the probability that the answer is yes |

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

These eight were easy, and Jev was 1.00 confident on all of them. The tricky-message test further down is the harder check of how well it reads.

## Routing with logic (rules over facts): usually right, and wrong exactly where it matters

I gave it a refund policy: under $100 and within 30 days means auto-refund, $100 or more means a manager approves, older than 30 days means deny, and gold-tier customers get 60 days. Then I asked it for the outcome directly:

```
OK  $45    14d standard  -> AUTO_REFUND  conf=1.00
OK  $45    50d gold      -> AUTO_REFUND  conf=0.79   (applied the gold exception)
XX  $100   31d standard  -> MANAGER      conf=0.97   <- should be DENY, and it was 97% sure
```

It got 7 of 8 right. The miss was one day past the limit, and it was confidently wrong. A handful of small computation checks (sums, counts, dates) showed the same pattern:

```
XX  log has 3 "fail" entries - "more than 3?"  -> p=0.84 yes   (wrong)
OK  prices sum to 101 - "over 100?"            -> p=0.75       (right, but unsure)
```

Its errors cluster right at the thresholds, which is where the rule makes a difference, and here it was 97% confident about a wrong answer. Eight cases is a small sample, though.

## Stress test: 300 cases, a much harder policy

Eight cases is a small sample, so I scaled it up ([`refund_stress_test.py`](experiments/refund_stress_test.py)). The policy is now four steps with several interacting rules:

1. Final-sale items are never refunded, unless defective.
2. Find the return window. Defective items get 365 days. Non-defective electronics get 15 days (30 for platinum customers). Everything else goes by tier: standard 30 days, silver 45, gold 60, platinum 90. The last day of the window counts as inside it.
3. Anything outside its window is denied.
4. Refundable requests are routed by order total: under $100 is AUTO_REFUND, $100-$499.99 goes to MANAGER, $500 or more goes to FINANCE.

Each case has a customer tier, a category, a final-sale flag, 1-3 items with quantities, a purchase date, and a customer message that fits the category and may or may not describe a defect (36 distinct messages). Half the cases sit within 3 days of their window edge, which is where the earlier test failed. Code computes the correct answer for every case (checked by offline unit tests in [`test_truth.py`](experiments/test_truth.py)), and Jev is asked three ways:

- **A. Raw:** Jev gets purchase dates and item prices, so it has to do the date math, add up the total, apply the rules and read the message.
- **B. Prepped:** code works out `days_since_purchase` and `order_total_usd`. Jev still applies the rules and reads the message.
- **C. Hybrid:** Jev only answers "does this message describe a defect?" and code applies every rule.

```
                                  A raw          B prepped      C hybrid
all cases                         211/300 (70%)  236/300 (79%)  300/300 (100%)
far from any edge                 144/165 (87%)  151/165 (92%)  165/165 (100%)
within 3 days of window edge       63/129 (49%)   80/129 (62%)  129/129 (100%)
total within $10 of $100/$500       6/9 (67%)      8/9 (89%)      9/9 (100%)
final-sale                         61/70 (87%)    62/70 (89%)    70/70 (100%)
defective                          99/150 (66%)  112/150 (75%)  150/150 (100%)
electronics                        67/84 (80%)    76/84 (90%)    84/84 (100%)
```

(The "$10 of $100/$500" row only counts refundable cases, since the total doesn't matter for a denial. That's why it's small.)

What the harder test shows:

- **Stacked rules drag accuracy down.** It went from 7/8 on the simple policy to 70% here. Within 3 days of a window edge it's 49%: Jev gets the refund-or-deny call right less than half the time.
- **Doing the arithmetic in code helps, but doesn't fix it.** Prepped is 79%, and near an edge still only 62%. The rules themselves are hard for Jev, not just the math.
- **The most common miss is a defective item a few days past 365 being refunded anyway.** Jev seems to treat "defective" as "always refundable".
- **Don't over-read the hybrid's 100%.** In that mode code applies the rules, and it's fed Jev's answer about 36 distinct messages, all of which Jev read correctly. So 300/300 really means "36/36 messages read right, and `if` statements don't make mistakes". The tricky-message test below is the real test of the hybrid.

### Confidence helps a lot, but it's not a guarantee

"Act only when confidence is at least X, otherwise escalate":

```
             threshold   answers kept   accuracy of kept
A raw        0.9          45/300 (15%)   44/45  (98%)
A raw        0.95         38/300 (13%)   38/38  (100%)
B prepped    0.8         213/300 (71%)  194/213 (91%)
B prepped    0.9         179/300 (60%)  174/179 (97%)
B prepped    0.95        136/300 (45%)  135/136 (99%)
```

Jev usually knows when it's struggling. 235 of the 300 raw answers had confidence under 0.8, and gating at 0.9 lifts prepped accuracy from 79% to 97%. But it still makes confident mistakes. One prepped miss sent a final-sale, defective item 400 days old (35 days past its window) to FINANCE with 0.93 confidence. For a real refund flow, 97% probably isn't enough to let Jev apply the rules itself, which brings us back to the hybrid.

### Stress-testing the part Jev does in the hybrid

The hybrid only works if Jev reads messages correctly, so [`defect_reading_test.py`](experiments/defect_reading_test.py) throws 30 deliberately tricky, hand-labelled ones at it:

```
OK  p=0.97  "Wow. Five stars for the packaging. Zero for the product, which is in two pieces."
OK  p=0.95  "La cafetera gotea por abajo desde el primer dia."          (Spanish: leaks)
OK  p=0.73  "It works, technically, if you hold the cable at exactly the right angle."
OK  p=0.02  "It broke my heart to return it, it's beautiful, but it doesn't match my couch."
OK  p=0.11  "It did stop working once, but it was the outlet, not the lamp."
OK  p=0.39  "I dropped it down the stairs and now it won't turn on."   (customer's fault)
XX  p=0.65  "My last one from you was defective. This one is fine but I've lost trust."
```

It got 29/30. It handled sarcasm, idioms, Spanish, buried details, customer-caused damage and problems that had already been fixed. The one miss is a defect that belonged to a *different* item. Five answers landed in the unsure 0.2-0.8 band, which is exactly the queue a human would review. The full output is saved in `results/defect_reading_test.json`.

## Why not just code? Why Jev?

The stress test could look like "code beat Jev, so skip Jev". That's not what it shows. Code won at the rules, but it can't read the messages. In the hybrid, the one input code couldn't produce was "does this message describe a defect?", and Jev supplied it.

**Why not just code?** Because code doesn't read, it matches. I wrote a keyword check for defects ([`keyword_baseline.py`](experiments/keyword_baseline.py)): about 30 words like "broken", "leaking" and "stopped working", plus a rule that skips a match after "not". I wrote it once and didn't tune it to the test. Then I ran it on the same messages Jev read:

```
                                          keywords      Jev
stress-test messages (plain, 36)          26/36 (72%)   36/36 (100%)
tricky messages (hand-labelled, 30)       19/30 (63%)   29/30 (97%)

XX  "It broke my heart to return it, it's beautiful, but it doesn't match my couch."  (idiom)
XX  "I dropped it down the stairs and now it won't turn on."                          (customer's fault)
XX  "Wow. Five stars for the packaging. Zero for the product, which is in two pieces." (no keyword)
XX  "La cafetera gotea por abajo desde el primer dia."                                 (Spanish)
```

Keywords miss any defect described in words they don't list, and they flag any non-defect that happens to use one. Adding more keywords just trades one kind of miss for the other. Even on the plain messages from the stress test, keywords got 72%. The hybrid's 100% only works because the reading step is right.

**Why not a general-purpose LLM?** You can use one. Jev's case is narrower. Every answer is one of your fixed options with a probability, so there's no free text to parse. The confidence score gives you a threshold for sending cases to a human. A call costs about $0.000015. I didn't test Jev's accuracy against a general LLM, so this guide doesn't claim either one reads text better.

So it's not Jev *or* code. Jev sits where messy text enters the system and turns it into a few facts. Code does everything after that.

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
| Sentiment, urgency, frustration scores (not tested here yet) | Rules with exact cutoffs |
| Yes/no facts about text ("mentions an order ID?", "asks for a password?") | Anything needing an exact answer |
| Checking whether a document supports a claim (not tested here yet) | Writing replies, summaries or code; it can't generate text |
| Many narrow questions at once, in one cheap call | Open-ended "figure out what to do" work |

## Other things I found

- **Always add an `other` / `unclear` option.** It has to pick one of your options, so "hi" was routed to `product` with 0.71 confidence. That's one example, but the fix costs nothing.
- **Messages about two things get squashed into one label.** "Arrived broken AND you charged me twice" came back as billing at 0.99. That's one example, not a measured rate. If a message can be about several things, ask a separate yes/no question per team rather than one choice.
- **Use confidence as a filter.** A good pattern: if confidence is below about 0.8, send the ticket to a human or a smarter LLM. Tune that threshold on your own data.
- **Ask narrow questions.** "Is this spam?" works worse than 5 small yes/no questions combined in code. That's [TypeSafe's own top recommendation](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).
- **Cost:** about $0.000015 per call (around 350 input tokens), so roughly 70,000 triage calls per dollar.

## What these tests don't show

- **How well Jev reads outside customer support.** I wrote and labelled every test message myself, and they're all support tickets and refund requests (two in Spanish). The "Jev reads well" finding rests on about 80 messages. The "bad at rules" finding rests on 300 cases.
- **Whether Jev reads better than a general-purpose LLM.** The only comparison here is a keyword check.
- **Score questions, long or cluttered input, and repeat-run stability.** None of these are tested yet.

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
python3 refund_stress_test.py 300 7   # 300 random cases, seed 7; writes results/refund_stress_test_seed7.json
python3 defect_reading_test.py        # 30 tricky hand-labelled messages; writes results/defect_reading_test.json
python3 claim_support_test.py         # 24 hand-labelled document/claim pairs (results not in this guide yet)
python3 stability_test.py 5           # tricky-message test run 5 times, to check stability (results not in this guide yet)
python3 keyword_baseline.py           # keyword check on the same messages, for comparison (no API key needed)
python3 -m unittest test_truth        # offline checks of the stress test's answer key (no API key needed)
```

The stress test makes 3 calls per case (900 for 300 cases) and refuses more than 1,000 cases. Its calls carry the long policy text, so they cost about twice as much as a triage call (roughly $0.00003 each), and a full run comes to a few cents. Failed calls are retried on rate limits and server errors only. A bad key or an empty balance stops straight away.

TypeSafe designs Jev to give stable answers across repeated runs. I haven't tested that yet, and exact numbers may shift between model versions.

## Further reading

- [TypeSafe docs index](https://docs.typesafe.ai/llms.txt)
- [How to build with TypeSafe](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)
- [Intent routing pattern](https://docs.typesafe.ai/patterns/intent-routing)
- [Confidence](https://docs.typesafe.ai/confidence)
