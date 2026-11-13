"""给“十日线过滤时段图”加 MACD 规则与金叉当天过滤（A20 金叉间距、K−D≥5.3）。运行前写定：
MACD 12/26/9（指数收盘价，全历史递推）；金叉=DIF 由 ≤DEA 变为 >DEA；只在金叉当天决定该轮是否入场，通过则次日开盘买，死叉次日开盘卖，不补买被跳过的轮次。
A20：金叉当天 (DIF−DEA)/ATR14（Wilder，最高/最低/收盘）≥ 当年阈值；阈值 = 前 3 个完整自然年内“金叉在交易起点后且已在年前卖出”的 7 指数 MACD 交易该特征的 20% 分位，
  每年 1 月定、全年冻结，样本 <50 笔则无阈值（视为不通过）。方法照 codex_macd_filter17.py，只是训练池换成本页 7 个指数。
K−D：金叉当天 KDJ(9,3,3) 的 K−D ≥ 5.3（沿用 ETF 研究的固定阈值）。
标志位：bit7 MACD 多头，bit8 本轮 A20 通过，bit9 本轮 K−D 通过，bit10 本轮无 A20 阈值。用法：python ma10_macd_patch.py 输入.html 输出.html"""
import json, sys, re, numpy as np, pandas as pd
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"const DATA = (\{.*?\});\n", html, re.S); data = json.loads(m.group(1))
def ema(v, a):
    z = np.empty(len(v)); z[0] = v[0]
    for i in range(1, len(v)): z[i] = z[i - 1] + a * (v[i] - z[i - 1])
    return z
def wilder(v, n=14):
    z = np.full(len(v), np.nan); k = next(k for k in range(n, len(v) + 1) if np.isfinite(v[k - n:k]).all()) - 1
    z[k] = v[k - n + 1:k + 1].mean()
    for i in range(k + 1, len(v)): z[i] = (z[i - 1] * (n - 1) + v[i]) / n
    return z
F, TRAIN = {}, []
for ix in data["indices"]:
    d = pd.read_csv(f"data/index_{ix['code']}_ohlc.csv", parse_dates=["date"]).set_index("date").sort_index()
    d = d[~d.index.duplicated()]
    c, h, l = d.close.values, np.maximum(d.high.values, d.close.values), np.minimum(d.low.values, d.close.values)
    dif = ema(c, 2 / 13) - ema(c, 2 / 27); dea = ema(dif, .2); bull = dif > dea
    prev = np.r_[np.nan, c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev))); tr[0] = h[0] - l[0]
    gap = (dif - dea) / wilder(tr)
    k = dd = 50.0; kd = np.empty(len(c))
    for i in range(len(c)):
        hh, ll = h[max(0, i - 8):i + 1].max(), l[max(0, i - 8):i + 1].min()
        k = k * 2 / 3 + ((c[i] - ll) / (hh - ll) * 100 if hh > ll else 50) / 3; dd = dd * 2 / 3 + k / 3; kd[i] = k - dd
    cycles = []; i = 1
    while i < len(c):
        if bull[i] and not bull[i - 1]:
            b = i
            while i < len(c) and bull[i]: i += 1
            cycles.append((b, i))
        else: i += 1
    st = pd.Timestamp(ix["start"])
    for b, e in cycles:
        if d.index[b] >= st and b >= 60 and e < len(c) - 1: TRAIN.append((d.index[b], d.index[e + 1], gap[b]))
    F[ix["code"]] = (d, bull, gap, kd, cycles)
T = pd.DataFrame(TRAIN, columns=["date", "sell", "gap"]); THR = {}
for y in range(2009, 2027):
    a = T[(T.date >= pd.Timestamp(y - 3, 1, 1)) & (T.sell < pd.Timestamp(y, 1, 1))]
    THR[y] = float(a.gap.quantile(.2)) if len(a) >= 50 else None
etf = pd.read_csv("research/codex_filter17_thresholds.csv").set_index("year").amplitude20
print("年份  训练笔数  指数阈值   ETF阈值(Codex)")
for y in THR:
    a = T[(T.date >= pd.Timestamp(y - 3, 1, 1)) & (T.sell < pd.Timestamp(y, 1, 1))]
    print(f"{y}  {len(a):6d}  {THR[y] if THR[y] is not None else float('nan'):.4f}   {etf.get(y, float('nan')):.4f}")
for ix in data["indices"]:
    d, bull, gap, kd, cycles = F[ix["code"]]; dates = pd.to_datetime(ix["date"]); pos = d.index.get_indexer(dates); assert (pos >= 0).all()
    flag = np.array(ix["flag"]) & 127; pa = np.zeros(len(d), bool); pk = np.zeros(len(d), bool); unk = np.zeros(len(d), bool)
    for b, e in cycles:
        th = THR.get(d.index[b].year)
        pa[b:e] = th is not None and gap[b] >= th; unk[b:e] = th is None; pk[b:e] = kd[b] >= 5.3
    flag |= bull[pos] * 128 | pa[pos] * 256 | pk[pos] * 512 | unk[pos] * 1024
    ix["flag"] = [int(x) for x in flag]
    first = pos[0]
    ix["cross"] = {str(int(np.searchsorted(pos, b))): [round(float(gap[b]), 5), round(float(kd[b]), 2)] for b, e in cycles if b >= first}
data["macdThr"] = {str(y): (round(v, 6) if v is not None else None) for y, v in THR.items()}
data["etfThr2026"] = round(float(etf.get(2026)), 6)
def sim(ix, kind, bit, i0):
    fl = ix["flag"]; n = len(fl); st = [0] * n
    for i in range(1, n):
        if kind == "macd": st[i] = 1 if fl[i] & 128 and (bit < 0 or fl[i] >> bit & 1) else 0
        else:
            above = fl[i] & 32 > 0; gate = bit < 0 or fl[i] >> bit & 1
            st[i] = (1 if above else 0) if st[i - 1] else (1 if above and gate else 0)
    o, c = ix["open"], ix["close"]; v = 1.0; hold = False; nav = []; nb = 0
    for k in range(i0, n):
        want = st[k - 1] == 1
        if hold: v *= o[k] / c[k - 1]
        if want != hold: v *= 0.999; hold = want; nb += want
        if hold: v *= c[k] / o[k]
        nav.append(v)
    nav = np.array(nav); yrs = (pd.Timestamp(ix["date"][-1]) - pd.Timestamp(ix["date"][i0])).days / 365.25
    return nav[-1] ** (1 / yrs) - 1, (nav / np.maximum.accumulate(np.maximum(nav, 1)) - 1).min(), nb
print(f"\n检验期（年化/回撤/买入次数）{'持有':>10}{'MA10':>18}{'MACD':>20}{'MACD+A20':>20}{'MACD+K−D':>20}")
out = []
for ix in data["indices"]:
    i0 = max(1, next(i for i, t in enumerate(ix["date"]) if t >= ix["testStart"].replace("-", "")))
    hold = (ix["close"][-1] / ix["open"][i0]) ** (365.25 / (pd.Timestamp(ix["date"][-1]) - pd.Timestamp(ix["date"][i0])).days) - 1
    r = [sim(ix, "ma", -1, i0), sim(ix, "macd", -1, i0), sim(ix, "macd", 8, i0), sim(ix, "macd", 9, i0)]; out.append((hold, r))
    ix["check"]["MACD"] = round(r[1][0] * 100, 4); ix["check"]["MACD+A20"] = round(r[2][0] * 100, 4)
    print(f"{ix['name']:<12}{hold*100:+8.2f}" + "".join(f"{a*100:+8.2f}/{dd*100:5.1f}/{n:3d}" for a, dd, n in r))
print("A20 胜 MACD：", sum(r[2][0] > r[1][0] for _, r in out), "/7；K−D 胜 MACD：", sum(r[3][0] > r[1][0] for _, r in out), "/7；MACD 胜持有：", sum(r[1][0] > h for h, r in out), "/7")
new = html[:m.start(1)] + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + html[m.end(1):]
open(sys.argv[2], "w", encoding="utf-8").write(new)
