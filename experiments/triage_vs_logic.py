import os, json, urllib.request, concurrent.futures as cf
KEY=os.environ["OPENROUTER_API_KEY"]
def ask(state, questions):
    req=urllib.request.Request("https://openrouter.ai/api/alpha/decisions",
        data=json.dumps({"model":"typesafe/jev-1.13","state":state,"questions":questions}).encode(),
        headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req))

TEAM={"type":"choice","instructions":"Which team should handle `ticket`?",
 "criteria":{"billing":"Charges, invoices, refunds, subscriptions","shipping":"Delivery, tracking, lost or late packages",
             "account":"Login, password, profile, security","product":"How to use a product, features, bugs"}}

# ---------- A: triage, little logic (expected label) ----------
A=[("I was billed twice this month, fix it","billing"),
   ("Package says delivered but nothing on my porch","shipping"),
   ("Cant log in, reset email never arrives","account"),
   ("How do I export my data to CSV?","product"),
   ("Oh great, ANOTHER month paying for a plan I cancelled. Love it.","billing"),
   ("my thing hasnt showed up and its been 2 weeks, where is it","shipping"),
   ("Someone changed my email address without me knowing","account"),
   ("The dashboard chart shows blank since the update","product")]

# ---------- B: routing that needs logic over facts ----------
POLICY=("Refund rules: AUTO_REFUND if order total is under $100 AND purchase was within 30 days of today. "
        "MANAGER if total is $100 or more AND within 30 days. DENY if purchase was more than 30 days ago. "
        "Gold-tier customers get 60 days instead of 30.")
TODAY="2026-09-24"
B=[ # (order, expected)
 ({"total_usd":45,"purchased":"2026-09-10","tier":"standard"},"AUTO_REFUND"),
 ({"total_usd":250,"purchased":"2026-09-10","tier":"standard"},"MANAGER"),
 ({"total_usd":45,"purchased":"2026-07-01","tier":"standard"},"DENY"),
 ({"total_usd":45,"purchased":"2026-08-05","tier":"gold"},"AUTO_REFUND"),   # 50 days, gold
 ({"total_usd":99.99,"purchased":"2026-08-26","tier":"standard"},"AUTO_REFUND"), # 29 days
 ({"total_usd":100,"purchased":"2026-08-24","tier":"standard"},"DENY"),       # 31 days
 ({"total_usd":180,"purchased":"2026-08-01","tier":"gold"},"MANAGER"),        # 54 days gold
 ({"total_usd":30,"purchased":"2026-06-20","tier":"gold"},"DENY"),            # 96 days
]
ROUTE={"type":"choice","instructions":"Apply `policy` to `order` given `today`. Which outcome?",
 "criteria":{"AUTO_REFUND":"Auto refund","MANAGER":"Needs manager approval","DENY":"Deny refund"}}

def runA(t):
    r=ask({"ticket":t[0]},{"team":TEAM}); a=r["answers"]["team"]; return t,a["choice"],a["confidence"]
def runB(o):
    r=ask({"policy":POLICY,"today":TODAY,"order":o[0]},{"route":ROUTE,
       "within_30":{"type":"noul","instructions":"Was `order.purchased` 30 days or fewer before `today`?"},
       "under_100":{"type":"noul","instructions":"Is `order.total_usd` less than 100?"}})
    a=r["answers"]; return o,a["route"]["choice"],a["route"]["confidence"],a["within_30"]["noul"],a["under_100"]["noul"]

from datetime import date

if __name__ == "__main__":
    with cf.ThreadPoolExecutor(8) as ex:
        ra=list(ex.map(runA,A)); rb=list(ex.map(runB,B))
    print("A: TRIAGE"); ok=0
    for t,c,conf in ra:
        ok+=c==t[1]; print(f"  {'OK ' if c==t[1] else 'XX '} want={t[1]:8} got={c:8} conf={conf:.2f}  {t[0][:55]}")
    print(f"  {ok}/{len(A)}")
    print("B: LOGIC ROUTING (end-to-end in Jev)"); ok=0; ok30=0; ok100=0
    for o,c,conf,w30,u100 in rb:
        d=(date.fromisoformat(TODAY)-date.fromisoformat(o[0]["purchased"])).days
        ok+=c==o[1]; ok30+=(w30>.5)==(d<=30); ok100+=(u100>.5)==(o[0]["total_usd"]<100)
        print(f"  {'OK ' if c==o[1] else 'XX '} want={o[1]:11} got={c:11} conf={conf:.2f}  ${o[0]['total_usd']:<6} {d:3}d {o[0]['tier']:8}| within30?={w30:.2f} (true {d<=30})  under100?={u100:.2f}")
    print(f"  route {ok}/{len(B)}   date-noul {ok30}/{len(B)}   amount-noul {ok100}/{len(B)}")
