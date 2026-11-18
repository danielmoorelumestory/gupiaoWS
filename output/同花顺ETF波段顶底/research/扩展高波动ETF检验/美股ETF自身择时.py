"""用户要求（2026-11-18）：用美股自己的择时，看能否在美股 ETF 上增加利润。事前写定（跑之前，跑完不改）：
标的（场内、成交额较大、历史较长）：513100 纳指国泰、159941 纳指广发、513500 标普500博时。
美股数据：腾讯 us.NDX 纳指100、us.INX 标普500、us.DJI 道指日线。时间对齐：A 股日 D 只用美股日期 < D 的收盘（前一晚收盘，次日场内操作）。
择时（牛=True）：
  T200  对应指数（纳指 ETF 用 NDX，标普 ETF 用 INX）收盘 > 200 日均线
  T100  同上 100 日均线（约 20 周线）
  SND   纳指100 ÷ 道指 > 20 日均线（美股成长/价值风格，对应 A 股 创业板÷红利 思路）
  SNS   纳指100 ÷ 标普500 > 20 日均线
  T200&SND  两者都牛
买卖规则：B=只认金叉（熊市不开新仓、死叉卖），A=Y1（含熊市破10日线卖），P=纯择时（牛市持有，状态翻转次日开盘进出，单边 0.1%）。
对照：一直持有（同一起点）、现行 A 股沪深300择时 + 只认金叉（B·H1）、不择时 + 只认金叉/Y1。
窗口：2015-01-01 起、2020-01-01 起（均到 2026-11-10）。指标：年化、最大回撤、卡玛。
合格：同一方案在 3 只 ETF、两个窗口都满足 卡玛比一直持有高 ≥0.2 且年化比一直持有少不超过 2 个百分点。
注意：场内价格含 QDII 溢价波动。历史统计，不构成投资建议。"""
import importlib.util, json, gzip, datetime
sp = importlib.util.spec_from_file_location("W", "行业观察池导出网页.py"); W = importlib.util.module_from_spec(sp); sp.loader.exec_module(W)
C, X, RM = W.C, W.X, W.X.RM
import tencent_hfq as T
ETFS = {"513100": ("纳指国泰", "us.NDX"), "159941": ("纳指广发", "us.NDX"), "513500": ("标普500博时", "us.INX")}
WINS = {"2015起": ("2015-01-01", X.END), "2020起": ("2020-01-01", X.END)}
def us(sym):
    s = T.load(sym)
    return s
def shift(sig):  # 美股日期 t 的收盘，A 股 t+1 日起才可用
    return {(datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat(): v for d, v in sig.items()}
def pure(d, key, cost=0.001):
    a = [float(r["adjusted_close"]) for r in d["rows"]]; o = [float(r["open"]) * a[i] / float(r["close"]) for i, r in enumerate(d["rows"])]
    st = d["reg"][key]; nav = []; v = 1.0; held = False
    for i, dt in enumerate(d["dates"]):
        if i == 0: nav.append({"date": dt, "nav": v}); continue
        want = st[i]  # 当日开盘前已知的状态
        if held and want:  v *= a[i] / a[i-1]
        elif held and not want: v *= o[i] / a[i-1] * (1 - cost); held = False
        elif not held and want: v *= a[i] / o[i] * (1 - cost); held = True
        nav.append({"date": dt, "nav": v})
    return nav
if __name__ == "__main__":
    C.init()
    NDX, INX, DJI = us("us.NDX"), us("us.INX"), us("us.DJI")
    for k, s in (("NDX", NDX), ("INX", INX), ("DJI", DJI)): print(k, len(s), min(s), max(s))
    sig = {"SND": shift(RM.ma_state(RM.ratio(NDX, DJI), 20)), "SNS": shift(RM.ma_state(RM.ratio(NDX, INX), 20))}
    for nm, s in (("NDX", NDX), ("INX", INX)):
        for n in (200, 100): sig[f"T{n}{nm}"] = shift(RM.ma_state(s, n))
    res = {}
    for code, (name, idx) in ETFS.items():
        d = W.data_of(code); tag = "NDX" if idx == "us.NDX" else "INX"
        for k in ("SND", "SNS"): d["reg"][k] = RM.last_known(sig[k], d["dates"])
        for n in (200, 100): d["reg"][f"T{n}"] = RM.last_known(sig[f"T{n}{tag}"], d["dates"])
        d["reg"]["T200&SND"] = [x and y for x, y in zip(d["reg"]["T200"], d["reg"]["SND"])]
        runs = {}
        b0 = C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True); first = b0["metric"]["first"]
        a = {r["date"]: float(r["adjusted_close"]) for r in d["rows"] if r["date"] >= first}; base = a[min(a)]
        runs["一直持有"] = {t: v / base for t, v in a.items()}
        runs["B·H1(现行A股沪深300择时)"] = {x["date"]: x["nav"] for x in b0["nav"]}
        runs["B·不择时"] = {x["date"]: x["nav"] for x in C.K.simulate_kd(d, {**C.T.BASE, "N": "ALL"}, C.FULL, 20, retain=True)["nav"]}
        runs["A·不择时"] = {x["date"]: x["nav"] for x in C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": "ALL"}, C.FULL, 20, retain=True)["nav"]}
        for k in ("T200", "T100", "SND", "SNS", "T200&SND"):
            runs[f"B·{k}"] = {x["date"]: x["nav"] for x in C.K.simulate_kd(d, {**C.T.BASE, "N": k}, C.FULL, 20, retain=True)["nav"]}
            runs[f"A·{k}"] = {x["date"]: x["nav"] for x in C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": k}, C.FULL, 20, retain=True)["nav"]}
            runs[f"P·{k}"] = {x["date"]: x["nav"] for x in pure(d, k) if x["date"] >= first}
        print(f"\n######## {code} {name} 上市 {d['dates'][0]} 回测起 {first}")
        for wn, w in WINS.items():
            print(f"## {wn}")
            for k, nav in runs.items():
                m = C.window_metrics(nav, w); res[(code, wn, k)] = m
                print(f"  {k:26s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n######## 合格检查（卡玛比一直持有高 ≥0.2 且 年化少 ≤2pp，3 只 × 2 窗口全满足）")
    keys = sorted({k for (_, _, k) in res if k != "一直持有"})
    for k in keys:
        cells = []; ok = True
        for code in ETFS:
            for wn in WINS:
                m, h = res[(code, wn, k)], res[(code, wn, "一直持有")]
                dc, da = m["cal"] - h["cal"], (m["cagr"] - h["cagr"]) * 100; good = dc >= 0.2 and da >= -2; ok &= good
                cells.append(f"{code[-3:]}{wn[2:4]}:{dc:+.2f}/{da:+.1f}{'✓' if good else '✗'}")
        print(f"  {'合格' if ok else '  - '} {k:26s} " + " ".join(cells))
