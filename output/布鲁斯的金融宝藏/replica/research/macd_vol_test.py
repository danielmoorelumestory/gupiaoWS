"""假设检验：MACD 金叉死叉相对一直持有的优势，是否在高波动品种上更明显。运行前写定，跑完不改：

假设来源：7 个 A 股宽基指数 2016 年以后，波动越高，MACD 减持有越大（相关 0.91）。这 7 个是提出假设的样本，不参与正式检验。
新样本（21 个，全部纳入，不挑选）：中证全指 10 个一级行业（能源、材料、工业、可选、消费、医药、金融地产、信息、通信、公用，
  中证官方日线）；海外 11 个：标普500、纳斯达克综指、道琼斯、恒生、恒生科技、国企指数、日经225、德国DAX、英国富时100、印度SENSEX、韩国KOSPI。
规则：MACD 12/26/9（收盘，EMA 从首日递推），DIF > DEA 时持有；金叉次日开盘买，死叉次日开盘卖；空仓现金零收益；
  单边 10 个基点（另报 0）。一直持有：起点开盘买入，不扣费。全部为价格指数，不含分红。数据截至 2026-11-10，之后的行全部删掉。
主检验期：2016-01-04 至 2026-11-10；恒生科技数据 2020-08 才开始，从 2021-03-01 起（留足 MACD 预热）。
分段：2016–2018、2019–2021、2022–2024、2025–2026-11-10 四个不重叠窗口，每段从现金开始。
波动：主口径用“事前波动”= 窗口开始前 250 个交易日的日收益标准差 × √250（窗口开始时就能知道）；另报窗口内的同期波动。
统计：每个窗口在 21 个品种上算
  (1) 事前波动与“MACD 减持有”的 Spearman 相关；
  (2) 回归 MACD减持有 = a + b·事前波动 + c·持有收益，看 b（控制住“这段时间本身涨跌”之后，波动还剩多少作用）；
  (3) 事前波动与持有收益的 Spearman 相关（看两者混在一起的程度）。
判定（事前写定）：四个窗口里 (2) 的 b 至少三个为正，且整段 b 为正，才算“支持”；b 为正但窗口不一致算“不一致”；整段 b ≤ 0 算“不支持”。
  21 个品种之间并不独立（同一市场、同涨同跌），所以只报方向和一致性，不报 p 值。"""
import numpy as np, pandas as pd
END = "2026-11-10"
CAL = pd.read_csv("data/index_sh000001_ohlc.csv", parse_dates=["date"]).set_index("date").index
SECT = {"sh000986": "全指能源", "sh000987": "全指材料", "sh000988": "全指工业", "sh000989": "全指可选", "sh000990": "全指消费",
        "sh000991": "全指医药", "sh000992": "金融地产", "sh000993": "全指信息", "sh000994": "全指通信", "sh000995": "全指公用"}
OVER = {"spx": "标普500", "ixic": "纳斯达克", "dji": "道琼斯", "hsi": "恒生", "hstech": "恒生科技", "hscei": "国企指数",
        "n225": "日经225", "dax": "德国DAX", "ftse": "富时100", "sensex": "印度SENSEX", "kospi": "韩国KOSPI"}
BROAD = {"sh000300": "沪深300", "sh000001": "上证指数", "sh000016": "上证50", "sh000905": "中证500", "sh000852": "中证1000", "sz399006": "创业板指", "sh000688": "科创50"}

def load(key):
    f = f"data/x_{key}.csv" if key in SECT or key in OVER else f"data/index_{key}_ohlc.csv"
    d = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
    d = d[~d.index.duplicated()].dropna(subset=["open", "close"]).loc[:END]
    d = d[(d.open > 0) & (d.close > 0)]
    if key in SECT: d = d[d.index.isin(CAL)]                      # 去掉非交易日的占位行（如 2010-01-01、2018-06-18）
    return d

def macd_state(c):
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return dif > dif.ewm(span=9, adjust=False).mean()

def backtest(d, st, a, b, cost):
    """与经审计的撮合相同：t 日收盘定仓位，t+1 开盘成交；从 a 当天开盘以现金开始。"""
    idx = d.loc[a:b].index; pos = d.index.get_indexer(idx); o, c, s = d.open.values, d.close.values, st.values
    nav = 1.0; hold = False; out = []; n = 0
    for k in pos:
        if k == 0: out.append(nav); continue
        want = bool(s[k - 1])
        if hold: nav *= o[k] / c[k - 1]
        if want != hold: nav *= 1 - cost; hold = want; n += 1
        if hold: nav *= c[k] / o[k]
        out.append(nav)
    return pd.Series(out, index=idx), n

def ann(nav):
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    return nav.iloc[-1] ** (1 / yrs) - 1

def evaluate(keys, names, a0, b0, cost):
    rows = []
    for k in keys:
        d = load(k); a = a0
        if k == "hstech": a = max(pd.Timestamp(a0), pd.Timestamp("2021-03-01")).strftime("%Y-%m-%d")
        if k == "sh000688": a = max(pd.Timestamp(a0), pd.Timestamp("2020-07-23")).strftime("%Y-%m-%d")
        if pd.Timestamp(a) >= pd.Timestamp(b0) or len(d.loc[a:b0]) < 120: continue
        i0 = d.index.get_indexer([d.loc[a:].index[0]])[0]
        if i0 < 250: continue                                           # 事前波动和 MACD 预热都不够
        r = d.close.pct_change()
        vol_pre = r.iloc[i0 - 250:i0].std() * np.sqrt(250); vol_in = r.loc[a:b0].std() * np.sqrt(250)
        nav, n = backtest(d, macd_state(d.close), a, b0, cost)
        x = d.loc[a:b0]; hold = ann(x.close / x.open.iloc[0])
        rows.append(dict(key=k, name=names[k], start=x.index[0].date(), vol_pre=vol_pre, vol_in=vol_in, hold=hold, macd=ann(nav), trades=n // 2))
    t = pd.DataFrame(rows); t["excess"] = t.macd - t.hold
    return t

def stats(t, vol="vol_pre"):
    X = np.c_[np.ones(len(t)), t[vol], t.hold]; beta = np.linalg.lstsq(X, t.excess, rcond=None)[0]
    sp = lambda a, b: pd.Series(a).rank().corr(pd.Series(b).rank())
    return dict(n=len(t), rho_vol_ex=sp(t[vol].values, t.excess.values), b=beta[1], c=beta[2], rho_vol_hold=sp(t[vol].values, t.hold.values))

NEW = {**SECT, **OVER}
WINDOWS = [("2016-01-01", "2018-12-31"), ("2019-01-01", "2021-12-31"), ("2022-01-01", "2024-12-31"), ("2025-01-01", END)]
for cost in (0.001, 0.0):
    print(f"\n######## 单边费用 {cost*1e4:.0f} 个基点")
    full = evaluate(list(NEW), NEW, "2016-01-01", END, cost)
    print(f"\n== 整段（2016-01 至 2026-11-10），新样本 {len(full)} 个，按事前波动排序（年化 %）")
    for _, r in full.sort_values("vol_pre").iterrows():
        print(f"   {r['name']:<10} 起 {r['start']}  事前波动 {r.vol_pre*100:5.1f}  同期波动 {r.vol_in*100:5.1f}  持有 {r.hold*100:+6.2f}  MACD {r.macd*100:+6.2f}  差 {r.excess*100:+6.2f}  （{r.trades} 笔）")
    for vol in ("vol_pre", "vol_in"):
        s = stats(full, vol); print(f"   [{'事前波动' if vol == 'vol_pre' else '同期波动'}] 波动~差 相关 {s['rho_vol_ex']:+.2f}；回归 差 = a + b·波动 + c·持有：b {s['b']:+.3f}，c {s['c']:+.3f}；波动~持有 相关 {s['rho_vol_hold']:+.2f}")
    hi = full[full.vol_pre >= full.vol_pre.median()]; lo = full[full.vol_pre < full.vol_pre.median()]
    print(f"   高波动一半 MACD 跑赢持有 {(hi.excess > 0).sum()}/{len(hi)}，平均差 {hi.excess.mean()*100:+.2f}；低波动一半 {(lo.excess > 0).sum()}/{len(lo)}，平均差 {lo.excess.mean()*100:+.2f}")
    up = full[full.hold > 0]
    if len(up) >= 6:
        s = stats(up); print(f"   只看持有为正的 {len(up)} 个：波动~差 相关 {s['rho_vol_ex']:+.2f}，b {s['b']:+.3f}")
    print("\n== 分段（每段从现金开始；主口径事前波动）")
    pos_b = 0
    for a, b in WINDOWS:
        t = evaluate(list(NEW), NEW, a, b, cost); s = stats(t); pos_b += s["b"] > 0
        print(f"   {a[:4]}–{b[:4]}  品种 {s['n']:2d}  波动~差 {s['rho_vol_ex']:+.2f}  b {s['b']:+.3f}  c {s['c']:+.3f}  波动~持有 {s['rho_vol_hold']:+.2f}  "
              f"MACD 跑赢持有 {(t.excess > 0).sum()}/{len(t)}")
    sf = stats(full)
    verdict = "支持" if (sf["b"] > 0 and pos_b >= 3) else ("不支持" if sf["b"] <= 0 else "不一致")
    print(f"   b 为正的窗口 {pos_b}/4，整段 b {sf['b']:+.3f} → 判定：{verdict}")

print("\n######## 参考：提出假设的 7 个 A 股宽基（不参与判定），单边 10 个基点")
br = evaluate(list(BROAD), BROAD, "2016-01-01", END, 0.001); s = stats(br)
print(f"   事前波动~差 相关 {s['rho_vol_ex']:+.2f}，b {s['b']:+.3f}，波动~持有 相关 {s['rho_vol_hold']:+.2f}")

# ---------------------------------------------------------------- 补充诊断（看完上面结果后加的，不改判定）
# 2016 年初的事前波动包含 2015 年 A 股暴跌，A 股行业全部在 38%–50%，海外全部在 13%–27%，事前波动几乎等于“是不是 A 股”。
# 所以分组各自看一遍：如果只是 A 股与海外的差别，组内关系应当消失。
print("\n######## 补充诊断：分组看（单边 10 个基点，整段）")
full = evaluate(list(NEW), NEW, "2016-01-01", END, 0.001)
for nm, keys in (("A 股 10 个行业", SECT), ("海外 10 个（恒生科技样本不够）", OVER)):
    t = full[full.key.isin(keys)]
    for vol in ("vol_pre", "vol_in"):
        s = stats(t, vol); print(f"   {nm} [{'事前' if vol == 'vol_pre' else '同期'}波动] 波动~差 {s['rho_vol_ex']:+.2f}，b {s['b']:+.3f}，波动~持有 {s['rho_vol_hold']:+.2f}，MACD 跑赢持有 {(t.excess > 0).sum()}/{len(t)}，平均差 {t.excess.mean()*100:+.2f}")
for a, b in WINDOWS:
    t = evaluate(list(NEW), NEW, a, b, 0.001); line = []
    for nm, keys in (("A股行业", SECT), ("海外", OVER)):
        g = t[t.key.isin(keys)]; s = stats(g)
        line.append(f"{nm} 波动~差 {s['rho_vol_ex']:+.2f} 跑赢 {(g.excess > 0).sum()}/{len(g)}")
    print(f"   {a[:4]}–{b[:4]}：" + "；".join(line))
