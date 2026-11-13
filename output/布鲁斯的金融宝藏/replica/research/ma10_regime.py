"""10 日线规则在什么行情里失效，能否事先区分出来。以下设计在运行前写定，跑完不改：

基础规则：收盘站上 10 日线次日开盘买，跌破次日开盘卖；空仓现金零收益；价格指数，不计分红；单边 10 个基点。
指数：沪深300、上证指数、上证50、中证500、中证1000、创业板指、科创50。交易从 2006-01-04 起（之前只做指标预热），
中证1000 从 2015-07-01，创业板指从 2011-06-01，科创50 从 2020-07-23。

一、诊断（事后描述，只用来理解，不当证据）
  按买入信号当天收盘时的行情把每笔交易归类，看各类的平均收益和胜率：
  60 日涨跌 > +10% 为上涨，< −10% 为下跌，其余为震荡；震荡再按 60 日区间宽度（最高收盘/最低收盘−1）是否低于训练集中位数分成窄幅、宽幅。

二、过滤（事前可知）：过滤条件只拦新的买入信号，已经持有的照常在跌破 10 日线时卖出。候选五个，阈值只用训练集定：
  F1 带方向效率比：(收盘−60 日前收盘)/60 日内每日涨跌绝对值之和 ≥ 训练集中位数
  F2 长期趋势：收盘 > 200 日均线，且 200 日均线高于 20 个交易日前
  F3 近期来回次数：过去 60 日 10 日线穿越次数 ≤ 训练集中位数
  F4 ADX：14 日 ADX ≥ 25 且 +DI > −DI（Wilder 原始定义，25 是通用惯例值，不调）
  F5 区间宽度：60 日区间宽度 ≥ 训练集中位数
训练集：沪深300、上证指数、中证500 的 2006–2015 年（只用来定 F1、F3、F5 的阈值和诊断里的宽度中位数）。
检验集：同三个指数的 2016-01-01 以后；以及没参与训练的上证50、中证1000、创业板指、科创50 各自的 2016-01-01 以后（科创50 从 2020-07-23）。
主指标：过滤后对比不过滤的年化收益差，以及对比一直持有。五个过滤 × 七个指数，多次比较，单个指数上的好结果不算数，
只有在检验集多数指数上同方向改善才算有迹象；即使如此，也只是历史迹象。"""
import numpy as np, pandas as pd
COST = 0.001
NAMES = {"sh000300": "沪深300", "sh000001": "上证指数", "sh000905": "中证500", "sh000016": "上证50", "sh000852": "中证1000", "sz399006": "创业板指", "sh000688": "科创50"}
START = {"sh000852": "2015-07-01", "sz399006": "2011-06-01", "sh000688": "2020-07-23"}
TRAIN = ("sh000300", "sh000001", "sh000905")
D = {c: pd.read_csv(f"data/index_{c}_ohlc.csv", parse_dates=["date"]).set_index("date") for c in NAMES}

def features(d):
    c, h, l = d.close, d.high, d.low
    f = pd.DataFrame(index=d.index)
    f["above"] = c > c.rolling(10).mean()
    path = c.diff().abs().rolling(60).sum()
    f["ser"] = (c - c.shift(60)) / path
    ma200 = c.rolling(200).mean(); f["trend200"] = (c > ma200) & (ma200 > ma200.shift(20))
    cross = f.above.astype(int).diff().abs(); f["cross60"] = cross.rolling(60).sum()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0); ndm = dn.where((dn > up) & (dn > 0), 0.0)
    w = lambda s: s.ewm(alpha=1/14, adjust=False).mean()
    atr = w(tr); pdi = 100 * w(pdm) / atr; ndi = 100 * w(ndm) / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi); f["adx"] = w(dx); f["pdi"] = pdi; f["ndi"] = ndi
    f["ret60"] = c / c.shift(60) - 1
    f["width60"] = c.rolling(60).max() / c.rolling(60).min() - 1
    return f
F = {c: features(D[c]) for c in NAMES}

# 训练集阈值
tr_days = pd.concat([F[c].loc["2006-01-01":"2015-12-31"] for c in TRAIN])
TH = {"ser": tr_days.ser.median(), "cross60": tr_days.cross60.median(), "width60": tr_days.width60.median()}
print("训练集阈值：带方向效率比中位数 %.3f，60 日穿越次数中位数 %.0f，60 日区间宽度中位数 %.1f%%" % (TH["ser"], TH["cross60"], TH["width60"] * 100))
FILTERS = {
    "不过滤": lambda f: pd.Series(True, index=f.index),
    "F1 效率比": lambda f: f.ser >= TH["ser"],
    "F2 长期趋势": lambda f: f.trend200,
    "F3 来回次数少": lambda f: f.cross60 <= TH["cross60"],
    "F4 ADX": lambda f: (f.adx >= 25) & (f.pdi > f.ndi),
    "F5 区间宽": lambda f: f.width60 >= TH["width60"],
}

def state(f, gate):
    """收盘后的目标仓位：空仓时要 线上且过滤通过 才买；持仓时跌破才卖。"""
    a, g = f.above.values, gate.fillna(False).values; s = np.zeros(len(a), bool)
    for i in range(1, len(a)): s[i] = a[i] if s[i - 1] else (a[i] and g[i])
    return pd.Series(s, index=f.index)

def backtest(d, st, start, end=None):
    """沿用经审计的逐日撮合：t 日收盘决定，t+1 开盘成交；从起点现金开始。"""
    idx = d.loc[start:end].index; pos = d.index.get_indexer(idx); o, c = d.open.values, d.close.values; s = st.values
    nav = 1.0; hold = False; navs = []; trades = []; entry = None; buy_i = None
    for k in pos:
        want = bool(s[k - 1])
        if hold: nav *= o[k] / c[k - 1]
        if want != hold:
            if want: entry = nav; buy_i = k
            else: trades.append((buy_i, nav * (1 - COST) / entry - 1))
            nav *= 1 - COST; hold = want
        if hold: nav *= c[k] / o[k]
        navs.append(nav)
    return pd.Series(navs, index=idx), trades

def ann(nav):
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    return nav.iloc[-1] ** (1 / yrs) - 1
def mdd(nav): return (nav / np.maximum(nav.cummax(), 1) - 1).min()
def hold_nav(d, start, end=None):
    x = d.loc[start:end]; return x.close / x.open.iloc[0]

# ---------------------------------------------------------------- 一、诊断
print("\n一、诊断（事后描述）：按买入信号当天的行情给每笔交易归类（基础规则，单边 10 基点）")
def regime(f, i):
    r, w = f.ret60.iloc[i], f.width60.iloc[i]
    if r > 0.10: return "上涨"
    if r < -0.10: return "下跌"
    return "窄幅震荡" if w < TH["width60"] else "宽幅震荡"
for group, codes, a, b in (("训练三指数 2006–2015", TRAIN, "2006-01-01", "2015-12-31"), ("全部七指数 2016 以后", list(NAMES), "2016-01-01", None)):
    rows = []
    for c in codes:
        f = F[c]; st = state(f, FILTERS["不过滤"](f)); s0 = max(pd.Timestamp(a), pd.Timestamp(START.get(c, a)))
        _, trades = backtest(D[c], st, s0, b)
        for bi, r in trades: rows.append((regime(f, bi - 1), r))
    t = pd.DataFrame(rows, columns=["regime", "ret"])
    g = t.groupby("regime").ret.agg(["count", "mean", "median", lambda x: (x > 0).mean(), "sum"])
    g.columns = ["笔数", "平均", "中位数", "胜率", "合计"]
    print(f" {group}：共 {len(t)} 笔")
    for k, r in g.reindex(["上涨", "宽幅震荡", "窄幅震荡", "下跌"]).iterrows():
        print(f"   {k:<6} {int(r['笔数']):4d} 笔（{r['笔数']/len(t)*100:4.1f}%）  平均 {r['平均']*100:+.2f}%  中位数 {r['中位数']*100:+.2f}%  胜率 {r['胜率']*100:4.1f}%  合计贡献 {r['合计']*100:+6.1f}%")

# ---------------------------------------------------------------- 二、过滤检验
def table(title, cases):
    print(f"\n{title}\n   年化（单边 10 基点）     " + " ".join(f"{k:>9}" for k in FILTERS) + "   一直持有")
    better = {k: 0 for k in FILTERS}
    for c, a, b in cases:
        f = F[c]; out = []
        for k, fn in FILTERS.items():
            nav, tr = backtest(D[c], state(f, fn(f)), a, b); out.append((ann(nav), mdd(nav), len(tr)))
        h = hold_nav(D[c], a, b)
        for j, k in enumerate(FILTERS):
            if j and out[j][0] > out[0][0]: better[k] += 1
        print(f"   {NAMES[c]:<6}{a[:4]}–{(b or '2026')[:4]}  " + " ".join(f"{x[0]*100:+8.2f}%" for x in out) + f"   {ann(h)*100:+.2f}%")
        print(f"     最大回撤             " + " ".join(f"{x[1]*100:8.1f}%" for x in out) + f"   {mdd(h)*100:.1f}%")
        print(f"     完整交易笔数         " + " ".join(f"{x[2]:9d}" for x in out))
    print("   比不过滤年化更高的指数数：" + "，".join(f"{k} {v}/{len(cases)}" for k, v in better.items() if k != "不过滤"))
table("二、训练集（阈值在这里定，好看是应该的，不算证据）", [(c, "2006-01-04", "2015-12-31") for c in TRAIN])
table("三、检验集：训练用过的三个指数的 2016 年以后", [(c, "2016-01-01", None) for c in TRAIN])
table("四、检验集：没参与训练的四个指数", [("sh000016", "2016-01-01", None), ("sh000852", "2016-01-01", None), ("sz399006", "2016-01-01", None), ("sh000688", "2020-07-23", None)])

# ---------------------------------------------------------------- 五、对照：随机拦掉同样比例的买入信号
# 过滤能少亏，可能只是因为交易少了、费用少了、持仓少了。用同等通过率的随机过滤做对照（同样只拦买入），
# 每个指数每个过滤各 300 次，看真实过滤排在随机结果的第几百分位。全部用检验集（2016 以后；科创50 从 2020-07-23）。
print("\n五、对照：与“随机拦掉同样比例的买入信号”相比（检验集，单边 10 基点；数字为真实过滤年化在 300 次随机里的百分位）")
rng = np.random.default_rng(20261111)
TEST = [(c, "2016-01-01") for c in ("sh000300", "sh000001", "sh000905", "sh000016", "sh000852", "sz399006")] + [("sh000688", "2020-07-23")]
pct_all = {k: [] for k in list(FILTERS)[1:]}
for c, a in TEST:
    f = F[c]; line = []
    for k in list(FILTERS)[1:]:
        gate = FILTERS[k](f).fillna(False)
        sig = f.above & ~f.above.shift(1, fill_value=False)                  # 站上那天
        p = gate[sig & (f.index >= a)].mean()                                # 站上那天过滤通过的比例
        real = ann(backtest(D[c], state(f, gate), a)[0])
        sims = [ann(backtest(D[c], state(f, pd.Series(rng.random(len(f)) < p, index=f.index)), a)[0]) for _ in range(300)]
        q = (np.array(sims) < real).mean() * 100; pct_all[k].append(q)
        line.append(f"{k} {q:3.0f}（通过率 {p*100:.0f}%，随机中位 {np.median(sims)*100:+.2f}%）")
    print(f"   {NAMES[c]}：" + "；".join(line))
print("   七个指数的平均百分位：" + "，".join(f"{k} {np.mean(v):.0f}" for k, v in pct_all.items()) + "（50 = 和随机一样）")
