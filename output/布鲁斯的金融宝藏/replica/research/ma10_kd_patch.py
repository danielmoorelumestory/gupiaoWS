"""给“十日线过滤时段图”页面补一个 K−D 过滤（bit6 = 当天日线 KDJ(9,3,3) 的 K−D ≥ 5.3）。
阈值 5.3 直接沿用 ETF MACD 低质量金叉研究的训练期 20% 分位，没有在指数 10 日线规则上重新挑选；
原页面数据（日期、开盘、收盘、bit0–5）不改，只在 flag 上加 64。用法：python ma10_kd_patch.py 原页面.html 新页面.html"""
import json, sys, re, numpy as np, pandas as pd
TH = 5.3
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"const DATA = (\{.*?\});\n", html, re.S); data = json.loads(m.group(1))
def kd(d):
    c, h, l = d.close.values, np.maximum(d.high.values, d.close.values), np.minimum(d.low.values, d.close.values)
    k = dd = 50.0; out = np.empty(len(d))
    for i in range(len(d)):
        hh, ll = h[max(0, i - 8):i + 1].max(), l[max(0, i - 8):i + 1].min()
        rsv = (c[i] - ll) / (hh - ll) * 100 if hh > ll else 50
        k = k * 2 / 3 + rsv / 3; dd = dd * 2 / 3 + k / 3; out[i] = k - dd
    return pd.Series(out, index=d.index)
def sim(ix, bit, i0):
    n = len(ix["date"]); st = [0] * n
    for i in range(1, n):
        above = ix["flag"][i] & 32 > 0; gate = bit < 0 or (ix["flag"][i] >> bit) & 1
        st[i] = (1 if above else 0) if st[i - 1] else (1 if above and gate else 0)
    o, c = ix["open"], ix["close"]; v = 1.0; hold = False; nav = []; held = 0
    for k in range(i0, n):
        want = st[k - 1] == 1
        if hold: v *= o[k] / c[k - 1]
        if want != hold: v *= 0.999; hold = want
        if hold: v *= c[k] / o[k]; held += 1
        nav.append(v)
    nav = np.array(nav); yrs = (pd.Timestamp(ix["date"][-1]) - pd.Timestamp(ix["date"][i0])).days / 365.25
    return nav[-1] ** (1 / yrs) - 1, (nav / np.maximum.accumulate(np.maximum(nav, 1)) - 1).min(), held / len(nav)
rows = []
for ix in data["indices"]:
    d = pd.read_csv(f"data/index_{ix['code']}_ohlc.csv", parse_dates=["date"]).set_index("date").sort_index()
    s = kd(d); dates = pd.to_datetime(ix["date"])
    assert dates.isin(d.index).all(), ix["code"]
    sub = d.loc[dates]
    assert np.allclose(sub.close.values, ix["close"], rtol=0, atol=0.011) and np.allclose(sub.open.values, ix["open"], rtol=0, atol=0.011), ix["code"]
    ok = (s.loc[dates].values >= TH)
    ix["flag"] = [int(f & 63) | (64 if p else 0) for f, p in zip(ix["flag"], ok)]
    i0 = max(1, next(i for i, t in enumerate(ix["date"]) if t >= ix["testStart"].replace("-", "")))
    r = {k: sim(ix, b, i0) for k, b in (("不过滤", -1), ("F3", 2), ("K−D", 6))}
    rows.append((ix["name"], r, ok[i0:].mean()))
print(f"{'检验期':<8}{'不过滤':>16}{'F3':>16}{'K−D≥5.3':>16}{'K−D通过日':>10}")
for nm, r, p in rows:
    print(f"{nm:<8}" + "".join(f"{a*100:+8.2f}/{dd*100:6.1f}" for a, dd, _ in r.values()) + f"{p*100:9.0f}%")
print("K−D 胜不过滤：", sum(r["K−D"][0] > r["不过滤"][0] for _, r, _ in rows), "/", len(rows), "；胜 F3：", sum(r["K−D"][0] > r["F3"][0] for _, r, _ in rows))
new = html[:m.start(1)] + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + html[m.end(1):]
open(sys.argv[2], "w", encoding="utf-8").write(new)
