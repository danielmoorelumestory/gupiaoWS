"""诊断：B 多出来的买入（金叉之外因「站上10日线」触发）到底贡献了什么。全部已知高波动 40 只，全历史。
1) 按入场触发拆分 B 的交易：金叉买 / 站上10日线买；按出场拆分：死叉卖 / 空头破10日线卖。
2) 大涨月份的参与度：标的当月涨幅 ≥15% 记为大涨月，统计现行与 B 在这些月份的持仓天数占比，及这些月份的策略收益。"""
import math, statistics
from collections import defaultdict
from multiprocessing import Pool
import R2站上10日线买对照 as T, run_extended as X
FULL = ("1900-01-01", "2026-11-10")
def job(code):
    d = T.M.PANEL[code]; gold, dead = d["macds"][(12, 26, 9)]
    a = T.simulate_rgm(d, T.VAR["现行"], FULL, 20, retain=True); b = T.simulate_rgm(d, T.VAR["B同A加空头破10日卖"], FULL, 20, retain=True)
    tr = []
    for t in b["trades"]:
        if t["forced_end"]: continue
        es, xs = t["entry_signal_index"], t["exit_signal_index"]
        tr.append(dict(entry="金叉" if gold[es] else "站上10日", exit="死叉" if dead[xs] else "破10日", ret=t["net_return"], days=t["exit_index"] - t["entry_index"]))
    # 月度：标的涨幅与两策略持仓/收益
    cl = [float(r["adjusted_close"]) for r in d["rows"]]; dates = d["dates"]; idx = {x: i for i, x in enumerate(dates)}
    mon = defaultdict(list)
    for na, nb in zip(a["nav"], b["nav"]): mon[na["date"][:7]].append((na, nb))
    months = []
    keys = sorted(mon); prev_close = None; pa = pb = 1.0
    for m in keys:
        rows = mon[m]; i0, i1 = idx[rows[0][0]["date"]], idx[rows[-1][0]["date"]]
        base = cl[i0 - 1] if i0 > 0 else cl[i0]
        months.append(dict(ret=cl[i1] / base - 1, ha=sum(x[0]["held_session"] for x in rows) / len(rows), hb=sum(x[1]["held_session"] for x in rows) / len(rows),
                           sa=rows[-1][0]["nav"] / pa - 1, sb=rows[-1][1]["nav"] / pb - 1))
        pa, pb = rows[-1][0]["nav"], rows[-1][1]["nav"]
    return code, tr, months[1:]
if __name__ == "__main__":
    pool, new, audit = X.build()
    def vol(rows):
        c = [float(r["adjusted_close"]) for r in rows]; return statistics.pstdev([math.log(c[i]/c[i-1]) for i in range(1, len(c))]) * math.sqrt(244)
    GRP = ["P"+k for k, d in pool.items() if vol(d["rows"]) >= .31] + ["N"+it["code"] for it in audit if it.get("status") == "eligible" and it["vol"] >= .31 and it["code"] in new]
    with Pool(8, initializer=T.init) as p: res = p.map(job, GRP)
    allt = [t for _, tr, _ in res for t in tr]
    print(f"B 的已完成交易共 {len(allt)} 笔（40 只合计）\n")
    print(f"{'入场':<8}{'出场':<8}{'笔数':>6}{'胜率':>8}{'平均收益':>10}{'中位收益':>10}{'≥20%大赚笔数':>14}{'≤-10%大亏笔数':>14}{'平均持有天':>10}{'收益合计(笔×均)':>16}")
    for e in ("金叉", "站上10日"):
        for x in ("死叉", "破10日", None):
            s = [t for t in allt if t["entry"] == e and (x is None or t["exit"] == x)]
            if not s: continue
            print(f"{e:<8}{(x or '合计'):<8}{len(s):>6}{sum(t['ret']>0 for t in s)/len(s)*100:>7.1f}%{statistics.mean(t['ret'] for t in s)*100:>9.2f}%{statistics.median(t['ret'] for t in s)*100:>9.2f}%{sum(t['ret']>=.2 for t in s):>14}{sum(t['ret']<=-.1 for t in s):>14}{statistics.mean(t['days'] for t in s):>10.1f}{sum(t['ret'] for t in s)*100:>15.0f}%")
    big = sorted((t for t in allt if t["ret"] >= .2), key=lambda t: -t["ret"])
    print(f"\nB 中收益 ≥20% 的大赚交易 {len(big)} 笔：金叉入场 {sum(t['entry']=='金叉' for t in big)} 笔，站上10日入场 {sum(t['entry']=='站上10日' for t in big)} 笔")
    print("\n## 大涨月份参与度（标的当月涨幅分档；持仓 = 当月持仓天数占比平均；策略收益 = 当月策略净值涨幅平均）")
    ms = [m for _, _, mm in res for m in mm]
    for lo, hi, lab in ((.15, 9, "大涨月 ≥15%"), (.05, .15, "上涨 5~15%"), (-.05, .05, "震荡 ±5%"), (-.15, -.05, "下跌 5~15%"), (-9, -.15, "大跌 ≤-15%")):
        s = [m for m in ms if lo <= m["ret"] < hi]
        print(f"  {lab:<10} {len(s):>4} 个月  标的平均 {statistics.mean(m['ret'] for m in s)*100:+6.1f}%  持仓 现行 {statistics.mean(m['ha'] for m in s)*100:4.0f}% / B {statistics.mean(m['hb'] for m in s)*100:4.0f}%  策略收益 现行 {statistics.mean(m['sa'] for m in s)*100:+5.2f}% / B {statistics.mean(m['sb'] for m in s)*100:+5.2f}%  差 {statistics.mean(m['sb']-m['sa'] for m in s)*100:+5.2f}")
