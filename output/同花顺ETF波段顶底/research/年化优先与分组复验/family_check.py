"""事后诊断（非预设）：高波动组里反复出现的 E3+MACD16/35/9 尾盘卖家族，与纯 MACD 尾盘卖逐只/区间对比。"""
import json, random, statistics
import cs_common as C
from cs_common import P
from grid import identifier
sel = json.load(open("高波动_selection.json")); H1, H2 = set(sel["H1"]), set(sel["H2"])
b = C.blank
fam = {"E3/X2 16/35/9（金叉且>MA10买，死叉卖）": {**b, "entry":"E3","exit":"X2","macd":[16,35,9]},
       "E3/X3 n9 hi70 16/35/9（+死叉时需<MA10或曾≥70回落）": {**b, "entry":"E3","exit":"X3","n":9,"hi":70,"macd":[16,35,9]},
       "MACD/X2 16/35/9（只换慢参数）": {**b, "entry":"MACD","exit":"X2","macd":[16,35,9]}}
for c in fam.values(): assert identifier(c) in C.grid
C.init(); base = C.grid[C.MACD_KEY]
for w, grp, gname in (("train", H1, "高波动"), ("validation", H1, "高波动"), ("test", H2, "高波动"), ("train", None, "全池"), ("validation", None, "全池"), ("test", None, "全池")):
    m = C.run(("m", base, True, w))[3]
    for k, c in fam.items():
        a = C.run((k, c, True, w))[3]
        codes = [x for x in a if (grp is None or x in grp) and a[x]["cagr"] is not None and m[x]["cagr"] is not None]
        rnd = random.Random(20261113)
        diffs = sorted(statistics.median(a[x]["cagr"] for x in s) - statistics.median(m[x]["cagr"] for x in s) for s in ([rnd.choice(codes) for _ in codes] for _ in range(1000)))
        print(f"{w:<10}{gname} {k}: {statistics.median(a[x]['cagr'] for x in codes)*100:6.2f}% vs 纯MACD {statistics.median(m[x]['cagr'] for x in codes)*100:6.2f}%  差95%[{diffs[25]*100:+.2f},{diffs[974]*100:+.2f}]  逐只胜 {sum(a[x]['cagr']>m[x]['cagr'] for x in codes)}/{len(codes)}")
