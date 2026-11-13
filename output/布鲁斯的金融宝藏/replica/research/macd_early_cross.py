"""提前算出金叉/死叉临界价，提前买卖。运行前写定，跑完不改。
临界价 P*_t：用 t-1 日收盘后的 EMA12、EMA26、DEA 反推，t 日收盘价 > P*_t 时 DIF_t > DEA_t（MACD 柱为正）。开盘前即可算出。
规则（单边 0.1%，复权连续价，空仓零收益，T+1：当天买入的不能当天卖）：
 基准：t 收盘金叉/死叉 → t+1 开盘成交。
 R1 尾盘成交：t 收盘确认金叉/死叉 → 按 t 收盘价成交（理想化上限：尾盘几分钟价格≈收盘价）。
 R2 盘中双向条件单：空仓时盘中最高 ≥ P* → 按 max(开盘, P*) 买；持仓时盘中最低 ≤ P* → 按 min(开盘, P*) 卖。
    若收盘没确认（假信号）：买入后收盘柱仍 ≤0 → 次日开盘卖；卖出后收盘柱仍 >0 → 次日开盘买回。当天卖出后不再当天买回。
 R3 只提前买：买入同 R2，卖出同基准。
 R4 只提前卖：买入同基准，卖出同 R2。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
ITEMS = json.load(open("data/page_etfs_plus.json"))
res = pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}); GOOD = set(res.loc[res.good.astype(str) == "True", "code"])
AF, AS, AD, COST = 2 / 13, 2 / 27, .2, .001
def sim(o, h, l, c, m, ps, i0, eb, es, tr):
    """eb/es: 是否盘中提前买/卖。返回净值序列、买入次数、假信号次数。"""
    nav = 1.0; hold = False; bday = -1; out = []; nb = 0; fake = 0; ent = 1
    def buy(p, k):
        nonlocal nav, hold, bday, nb, ent
        nav *= 1 - COST; ent = nav; hold = True; bday = k; nb += 1; return nav * c[k] / p
    for k in range(i0, len(c)):
        sold = False
        if hold:  # 开盘前持仓
            if not m[k - 1]:  # 昨收已是死叉（基准死叉或假买入）→ 开盘卖
                nav *= o[k] / c[k - 1] * (1 - COST); hold = False; sold = True; tr.append(nav / ent - 1)
            elif es and l[k] <= ps[k]:
                p = min(o[k], ps[k]); nav *= p / c[k - 1] * (1 - COST); hold = False; sold = True; tr.append(nav / ent - 1)
            else: nav *= c[k] / c[k - 1]
        if not hold and not sold:
            if m[k - 1]: nav = buy(o[k], k)  # 昨收金叉（基准或假卖出后买回）→ 开盘买
            elif eb and h[k] >= ps[k]: nav = buy(max(o[k], ps[k]), k)
        if hold and bday == k and not m[k]: fake += 1
        if sold and m[k] and es: fake += 1
        out.append(nav)
    return np.array(out), nb, fake
def sim_close(c, m, i0, tr):
    nav = 1.0; hold = bool(m[i0 - 1]); out = []; nb = int(hold); ent = 1 - COST if hold else 1
    if hold: nav *= 1 - COST
    for k in range(i0, len(c)):
        if hold: nav *= c[k] / c[k - 1]
        if m[k] != hold:
            nav *= 1 - COST
            if m[k]: ent = nav; nb += 1
            else: tr.append(nav / ent - 1)
            hold = m[k]
        out.append(nav)
    return np.array(out), nb, 0
def stats(nav, idx):
    n = pd.Series(nav, index=idx); a = n.iloc[-1] ** (365.25 / max(1, (idx[-1] - idx[0]).days)) - 1
    return a, (n / np.maximum(n.cummax(), 1) - 1).min(), n
K = ["基准", "R1尾盘", "R2双向", "R3只提前买", "R4只提前卖"]; rows = []; TR = {k: [] for k in K}; NAVB = {}; CHK = []
for code, name, grp in ITEMS:
    d, dv, mm, c = load(code); fac = c / d.close.values
    o, h, l = d.open.values * fac, d.high.values * fac, d.low.values * fac
    ef, es_, dif = ema(c, AF), ema(c, AS), None; dif = ef - es_; dea = ema(dif, AD); m = dif > dea
    ps = np.r_[np.nan, (dea[:-1] - (1 - AF) * ef[:-1] + (1 - AS) * es_[:-1]) / (AF - AS)]
    ok = np.isfinite(ps[1:]); CHK.append(((c[1:] > ps[1:]) == m[1:])[ok].mean())
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); yrs = (d.index[-1] - d.index[i0]).days / 365.25; mid = i0 + (len(d) - i0) // 2
    run = {"基准": lambda a, b, t: sim(o[:b], h[:b], l[:b], c[:b], m[:b], ps[:b], a, False, False, t),
           "R1尾盘": lambda a, b, t: sim_close(c[:b], m[:b], a, t),
           "R2双向": lambda a, b, t: sim(o[:b], h[:b], l[:b], c[:b], m[:b], ps[:b], a, True, True, t),
           "R3只提前买": lambda a, b, t: sim(o[:b], h[:b], l[:b], c[:b], m[:b], ps[:b], a, True, False, t),
           "R4只提前卖": lambda a, b, t: sim(o[:b], h[:b], l[:b], c[:b], m[:b], ps[:b], a, False, True, t)}
    r = dict(code=code, name=name, good=code in GOOD, years=yrs)
    for k, f in run.items():
        tr = []; nav, nb, fk = f(i0, len(d), tr); r[k], r[k + "_dd"], _ = stats(nav, d.index[i0:]); r[k + "_n"] = nb; r[k + "_fake"] = fk
        r[k + "_h1"] = stats(f(i0, mid, [])[0], d.index[i0:mid])[0]; r[k + "_h2"] = stats(f(mid, len(d), [])[0], d.index[mid:])[0]
        if yrs >= 3: TR[k] += [(code, x) for x in tr]
        j0 = d.index.searchsorted(pd.Timestamp("2023-01-03"))
        if j0 >= 70: nv = f(j0, len(d), [])[0]; r[k + "_B"], _, NAVB[(k, code)] = stats(nv, d.index[j0:])
    rows.append(r)
t = pd.DataFrame(rows); t.to_csv("research/macd_early_cross_results.csv", index=False)
print(f"临界价校验：收盘价>P* 与 MACD 多头一致率 {np.mean(CHK):.4%}")
P = lambda v: f"{v*100:+.2f}%"; L = t[t.years >= 3]
for nm, G in (("≥3年 50 只", L), ("MACD优秀 17 只", L[L.good]), ("其余 33 只", L[~L.good])):
    print(f"\n[{nm}] 2016 起（或上市第70日起）")
    for k in K:
        x = np.array([v for cd, v in TR[k] if cd in set(G.code)])
        cmp = f"｜胜基准 {(G[k] > G['基准']).sum()}/{len(G)} 前后半都胜 {((G[k+'_h1'] > G['基准_h1']) & (G[k+'_h2'] > G['基准_h2'])).sum()} 回撤更小 {(G[k+'_dd'] > G['基准_dd']).sum()}" if k != "基准" else ""
        print(f"  {k:<8} 年化均值 {P(G[k].mean())} 中位 {P(G[k].median())} 前半均 {P(G[k+'_h1'].mean())} 后半均 {P(G[k+'_h2'].mean())} 回撤中位 {G[k+'_dd'].median()*100:.1f}% "
              f"买入中位 {G[k+'_n'].median():.0f} 假信号中位 {G[k+'_fake'].median():.0f} 胜率 {(x>0).mean():.1%} 每笔均 {x.mean()*100:+.2f}%{cmp}")
B = t[t["基准_B"].notna()]
print(f"\n[2023-01-03 起固定 {len(B)} 只，初始等额组合]")
for k in K:
    port = pd.DataFrame({cd: NAVB[(k, cd)] for cd in B.code}).ffill().mean(axis=1); ys = []
    for y in range(2023, 2027):
        prev = port[port.index.year < y].iloc[-1] if (port.index.year < y).any() else 1; ys.append(port[port.index.year == y].iloc[-1] / prev - 1)
    a, dd, _ = stats(port.values, port.index)
    print(f"  {k:<8} 年化均值 {P(B[k+'_B'].mean())} 组合年化 {P(a)} 组合回撤 {dd*100:.1f}% " + (f"胜基准 {(B[k+'_B'] > B['基准_B']).sum()}/{len(B)} " if k != "基准" else "") + "逐年 " + " ".join(f"{y*100:+.1f}" for y in ys))
G = L[L.good].set_index("code")
print("\n17 只（年化：基准 / R1 / R2 / R3 / R4 ｜ 假信号次数 R2）")
for cd, r in G.iterrows(): print(f"  {cd} {r['name'][:8]:<9}" + " ".join(f"{r[k]*100:+6.1f}" for k in K) + f"   {r['R2双向_fake']:.0f}/{r['R2双向_n']:.0f}")
