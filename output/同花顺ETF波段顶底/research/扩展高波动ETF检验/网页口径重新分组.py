"""四组（创业板择时优选/待选、沪深300择时优选/待选）现行分组，2026-11-18 用户定，取代 全量逐年优秀AB筛选.py 的卡玛归组与研究锁定数据（截至 11-10）。

口径：数字来自 BusinessWeb 网格详情页同一套回测引擎与腾讯前复权行情（网页口径指标_20261118.json，截至 2026-11-18），
本地 astro preview 逐只打开 /note/lab/grid-trading/detail/?code=，读方案块 [data-plan-stats][data-metrics] 的未取整指标。
只算已平仓交易：最后一笔还没卖出时当作没买、按空仓算到最新一天，卖出后再计入。逐年为每个自然年单独回测，当年不足 120 个交易日不计。

入选（五项全过）：计入年≥3；逐年平均≥10%；正收益年份≥75%；最差一年≥−10%；全历史卡玛≥0.5。
补入：只差一项，且逐年平均≥10%、卡玛≥0.7。
归组：两套方案都过底线（逐年均≥10%、最差一年≥−10%、卡玛≥0.5）时依次比：
  ① 逐年平均，相差≥1 个百分点选高的；② 累计年化，相差≥1 个百分点选高的；
  ③ 盈利年份占比高的；占比相同时各年收益标准差相差≥1 个百分点选小的；④ 最大回撤小的。
待选组（观察池）成员不变，只按同一规则选方案。人工例外：159509 纳指科技合格但美股不收；512720 计算机国泰不合格，用户决定放创业板择时待选。
名单用同一段历史挑出，结果偏乐观。历史统计，不构成投资建议。

用法：python3 网页口径重新分组.py  → 打印分组并写 网页口径分组_20261118.json
"""
import json, statistics
R = json.load(open("网页口径指标_20261118.json"))
WATCH = ["512400", "515880", "159566", "159206", "588170", "515790", "512880", "515220", "159565", "159992", "159928", "512720"]
EXCLUDE = {"159509"}
def m(c, p):
    x = R[c].get(p) or {}
    if x.get("cagr") is None: return None
    ys = [v for _, v in x["yearly"]]
    return dict(cagr=x["cagr"], mdd=x["mdd"], cal=x["calmar"], n=x["years"], pos=x["positive"], avg=x["avg"], worst=x["worst"], sd=statistics.pstdev(ys) if len(ys) > 1 else 0)
def fails(s):
    return [k for k, ok in (("年数", s["n"] >= 3), ("逐年均", s["avg"] >= .10), ("正收益年", s["pos"] / max(s["n"], 1) >= .75), ("最差一年", s["worst"] >= -.10), ("卡玛", s["cal"] >= .5)) if not ok]
base = lambda s: s and s["avg"] >= .10 and s["worst"] >= -.10 and s["cal"] >= .5 and s["n"] >= 3
def pick(a, b):
    if not a: return "hs"
    if not b: return "cyb"
    if abs(a["avg"] - b["avg"]) >= .01: return "cyb" if a["avg"] > b["avg"] else "hs"
    if abs(a["cagr"] - b["cagr"]) >= .01: return "cyb" if a["cagr"] > b["cagr"] else "hs"
    ra, rb = a["pos"] / a["n"], b["pos"] / b["n"]
    if ra != rb: return "cyb" if ra > rb else "hs"
    if abs(a["sd"] - b["sd"]) >= .01: return "cyb" if a["sd"] < b["sd"] else "hs"
    return "cyb" if a["mdd"] >= b["mdd"] else "hs"
out = {"优选": {"cyb": [], "hs": []}, "待选": {"cyb": [], "hs": []}}
for c in R:
    if c in EXCLUDE: continue
    a, b = m(c, "cyb"), m(c, "hs")
    ok = {p: s for p, s in (("cyb", a), ("hs", b)) if s and not fails(s)}
    sup = {p: s for p, s in (("cyb", a), ("hs", b)) if s and len(fails(s)) == 1 and s["avg"] >= .10 and s["cal"] >= .7 and s["n"] >= 3}
    if (ok or sup) and c not in WATCH:
        cands = {p: s for p, s in (("cyb", a), ("hs", b)) if base(s)} or {**sup, **ok}
        g = pick(cands.get("cyb"), cands.get("hs")); out["优选"][g].append((c, "" if ok else "补入", m(c, g)))
    elif c in WATCH:
        g = pick(a, b); out["待选"][g].append((c, "", m(c, g)))
name = {"cyb": "创业板择时", "hs": "沪深300择时"}
for kind in ("优选", "待选"):
    for g in ("cyb", "hs"):
        rows = sorted(out[kind][g], key=lambda r: -r[2]["cal"])
        print(f"\n## {name[g]}{kind}：{len(rows)} 只")
        for c, tag, s in rows:
            print(f"  {c} {tag:2} 逐年均 {s['avg']*100:+5.1f}%  年化 {s['cagr']*100:5.1f}%  回撤 {s['mdd']*100:6.1f}%  盈利年 {s['pos']}/{s['n']}  卡玛 {s['cal']:.2f}")
json.dump({f"{name[g]}{k}": [c for c, _, s in sorted(out[k][g], key=lambda r: -r[2]["cal"])] for k in out for g in out[k]},
          open("网页口径分组_20261118.json", "w"), ensure_ascii=False, indent=1)
