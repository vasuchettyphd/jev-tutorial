import json, concurrent.futures as cf
from jev import ask
from triage_vs_logic import TEAM
C=["The item arrived broken AND you charged me twice for it",
   "hi",
   "Can I change the card my subscription bills to? I can't find the setting after logging in",
   "your app sucks"]
def runC(t):
    a=ask({"ticket":t},{"team":TEAM})["answers"]["team"]; return t,a
D=[ # (state, question, truth)
 ({"items":[{"price":40},{"price":35},{"price":30}]},"Is the sum of `items[*].price` greater than 100?",True),   #105
 ({"items":[{"price":40},{"price":35},{"price":20}]},"Is the sum of `items[*].price` greater than 100?",False),  #95
 ({"items":[{"price":51},{"price":49},{"price":1}]},"Is the sum of `items[*].price` greater than 100?",True),    #101
 ({"log":["ok","fail","ok","fail","fail","ok","fail"]},"Does `log` contain more than 3 entries equal to \"fail\"?",True), #4
 ({"log":["ok","fail","ok","fail","ok","ok","fail"]},"Does `log` contain more than 3 entries equal to \"fail\"?",False), #3
 ({"a":"2026-03-14","b":"2026-04-15"},"Is `b` more than 31 days after `a`?",True),  #32
 ({"a":"2026-03-14","b":"2026-04-13"},"Is `b` more than 31 days after `a`?",False), #30
 ({"text":"Alice is Bob's manager. Bob is Carol's manager. Carol manages Dan."},"Is Alice in Dan's management chain?",True),
 ({"text":"Alice is Bob's manager. Bob is Carol's manager. Eve manages Dan."},"Is Alice in Dan's management chain?",False),
]
def runD(d):
    n=ask(d[0],{"q":{"type":"noul","instructions":d[1]}})["answers"]["q"]["noul"]; return d,n
if __name__ == "__main__":
    with cf.ThreadPoolExecutor(8) as ex: rc=list(ex.map(runC,C)); rd=list(ex.map(runD,D))
    print("C: AMBIGUOUS TRIAGE")
    for t,a in rc: print(f"  got={a['choice']:8} conf={a['confidence']:.2f} probs={ {k:round(v,2) for k,v in a['probabilities'].items()} }  {t}")
    print("D: COMPUTATION / MULTI-HOP (noul = P(yes))"); ok=0
    for d,n in rd:
        ok+=(n>.5)==d[2]; print(f"  {'OK ' if (n>.5)==d[2] else 'XX '} truth={str(d[2]):5} p={n:.2f}  {d[1][:60]}  {json.dumps(d[0])[:60]}")
    print(f"  {ok}/{len(D)}")
