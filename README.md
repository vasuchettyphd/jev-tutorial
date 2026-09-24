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

Its errors cluster right at the thresholds, which is where the rule makes a difference. Its confidence score doesn't reliably warn you when that happens.

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
```

TypeSafe designs Jev to give stable answers across repeated runs, but exact numbers may shift between model versions.

## Further reading

- [TypeSafe docs index](https://docs.typesafe.ai/llms.txt)
- [How to build with TypeSafe](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)
- [Intent routing pattern](https://docs.typesafe.ai/patterns/intent-routing)
- [Confidence](https://docs.typesafe.ai/confidence)
