"""A20 / K−D 入场过滤（定义取自 布鲁斯的金融宝藏/replica/research/codex_macd_filter17.py、16-codex-MACD低质量金叉研究.md）：
- MACD12/26/9 新金叉当天满足过滤才买入；新死叉尾盘卖（T+1 时次日开盘）；过滤只看金叉当天。
- K−D：KDJ(9,3,3)，用复权高低收，金叉当天 K−D ≥ 5.3（Codex 冻结阈值 5.3115，页面用 5.3）。
- A20：金叉当天 (DIF−DEA)/ATR14(Wilder) ≥ 当年阈值；阈值 = 之前 3 个自然年内、本主池全部已完成 MACD 周期的金叉值 20% 分位（周期须在当年 1 月 1 日前结束；不足 50 个时不过滤）。
  与原研究差异：原研究阈值来自它自己的 63 只池子，且不足 50 个时等于全拒；这里用本主池，并改为不过滤，说明在报告中。"""
import inspect, math
from datetime import date
import cs_common as C
engine = C.engine
src = inspect.getsource(engine.simulate).replace("def simulate(data,config,window,cost=20,retain=False,liquidate_end=True):",
      "def simulate_f(data,config,window,cost=20,retain=False,liquidate_end=True):")
src = src.replace("    def close_trade(", "    flt=data['flt'][config['flt']]\n    def close_trade(", 1)
src = src.replace("        value=cash+reserve+q*cl[i]\n", """        sold_at_close=False
        if q and i!=end and active["entry_index"]!=i and dead[i]:
            close_trade(i,cl[i],i,False);sold_at_close=True
        value=cash+reserve+q*cl[i]
""", 1).replace("        if i==end:\n            continue\n", "        if i==end or sold_at_close:\n            continue\n", 1)
a = src.index("        action=None\n"); b = src.index("        if action:\n")
src = src[:a] + """        action=None
        if q:
            if dead[i]: action="sell"
        elif gold[i] and flt[i]:
            action="buy"
""" + src[b:]
_ns = dict(vars(engine)); exec(src, _ns); simulate_f = _ns["simulate_f"]

def _wilder(v, n=14):
    z = [math.nan]*len(v); k = None
    for i in range(n-1, len(v)):
        w = v[i-n+1:i+1]
        if all(math.isfinite(x) for x in w): z[i] = sum(w)/n; k = i; break
    if k is None: return z
    for i in range(k+1, len(v)): z[i] = (z[i-1]*(n-1)+v[i])/n if math.isfinite(v[i]) else z[i-1]
    return z

def add_filters(panel, th=None):
    events = []  # (gold_date, end_date, hist_atr)
    for code, d in panel.items():
        rows = d["rows"]; c = [float(r["adjusted_close"]) for r in rows]
        f = [c[i]/float(r["close"]) for i, r in enumerate(rows)]
        hi = [float(r["high"])*f[i] for i, r in enumerate(rows)]; lo = [float(r["low"])*f[i] for i, r in enumerate(rows)]
        # MACD12/26/9 浮点版（只用于过滤数值，信号本身仍用引擎的 Decimal 金叉/死叉）
        e12 = e26 = c[0]; dea = 0.0; dif_l = []; dea_l = []
        for x in c:
            e12 = (2*x+11*e12)/13; e26 = (2*x+25*e26)/27; dif = e12-e26; dea = (2*dif+8*dea)/10; dif_l.append(dif); dea_l.append(dea)
        tr = [math.nan] + [max(hi[i]-lo[i], abs(hi[i]-c[i-1]), abs(lo[i]-c[i-1])) for i in range(1, len(c))]
        atr = _wilder(tr)
        ha = [(dif_l[i]-dea_l[i])/atr[i] if math.isfinite(atr[i]) and atr[i] > 0 else math.nan for i in range(len(c))]
        k = dd = 50.0; kd = []
        for i in range(len(c)):
            h9, l9 = max(hi[max(0,i-8):i+1]), min(lo[max(0,i-8):i+1])
            rsv = 100*(c[i]-l9)/(h9-l9) if h9 > l9 else 50.0
            k = (2*k+rsv)/3; dd = (2*dd+k)/3; kd.append(k-dd)
        gold, dead = d["macds"][(12,26,9)]
        d["_ha"], d["_kd"] = ha, kd
        i = 0; n = len(c)
        while i < n:
            if gold[i]:
                b = i; j = i+1
                while j < n and not dead[j]: j += 1
                if b >= 60 and j < n and math.isfinite(ha[b]): events.append((d["dates"][b], d["dates"][j], ha[b]))
                i = j
            else: i += 1
    if th is not None: events = []
    th = th if th is not None else {}
    for y in ([] if th else range(2010, 2028)):
        cut, begin = f"{y}-01-01", f"{y-3}-01-01"
        v = sorted(h for g, e, h in events if g >= begin and e < cut)
        th[y] = v[int(0.2*(len(v)-1))] if len(v) >= 50 else None  # 下分位近似
    for d in panel.values():
        ha, kd = d["_ha"], d["_kd"]
        d["flt"] = {"KD": [x >= 5.3 for x in kd],
                    "A20": [(th[int(t[:4])] is None) or (math.isfinite(ha[i]) and ha[i] >= th[int(t[:4])]) for i, t in enumerate(d["dates"])],
                    "NONE": [True]*len(kd)}
    return panel, th
