"""用户问（2026-11-20）：沪深300择时（只认金叉）买入后，若 沪深300÷红利 与 创业板÷红利 两个择时都进入熊市，且收盘跌破 10 日线，当天收盘卖出——B 组会不会更好。
事前写定（跑之前，跑完不改）：
  现行  B：H1 牛市 MACD 金叉次日开盘买，熊市不开新仓；死叉当日收盘卖（K.simulate_kd）。
  新    B+双熊破线卖：买入同现行；卖出 = 死叉，或（H1 熊 且 R2-20 熊 且 收盘<10日线）当日收盘卖。
  对照  B+H1熊破线卖：只要 H1 熊 且 收盘<10日线 就卖（看“双熊”这个条件是否必要）。
标的：线上沪深300择时优选 11 只（asOf 2026-11-18）。数据：研究面板/腾讯后复权，截至 2026-11-10（11 月初）。成本同引擎。
指标：全历史年化、最大回撤、卡玛；逐年（连续回测按自然年切）平均、赚钱年数、最差年；11 只平均。
判断：新规则在 11 只平均上 逐年平均不降 ≥1pp、且 平均最大回撤变小，算“更好”。历史统计，不构成投资建议。"""
import importlib.util, statistics, math
sp = importlib.util.spec_from_file_location("W", "行业观察池导出网页.py"); W = importlib.util.module_from_spec(sp); sp.loader.exec_module(W)
C, X = W.C, W.X
B = importlib.util.module_from_spec(s := importlib.util.spec_from_file_location("BKD", "B加KD10择时破线卖对照.py")); s.loader.exec_module(B)
src = B.src
old = "if below[i] and ((config[\"anyx\"] and reg[i] is False)"
assert src.count(old) == 1
src = src.replace(old, "if below[i] and ((config[\"anyx\"] and data[\"reg\"][config.get(\"XN\") or config[\"N\"]][i] is False)")
ns = dict(vars(B.G.engine)); ns["math"] = math; exec(src, ns); simx = ns["simulate_y"]
CODES = ["512480", "588000", "513090", "159819", "516150", "159732", "515000", "159967", "515980", "159755", "515050"]
NAMES = dict(zip(CODES, "半导体 科创50 香港证券 人工智能易方达 稀土 消费电子 科技 创业板成长 人工智能华富 电池 5G通信".split()))
BASE = {**C.T.BASE, "N": "H1", "ma10in": False, "keep": False}
def stats(nav):
    m = C.window_metrics(nav, C.FULL); ys = [v for y, v in m["years"].items()]
    return dict(cagr=m["cagr"], mdd=m["mdd"], cal=m["cal"], avg=statistics.mean(ys), pos=sum(v > 0 for v in ys), n=len(ys), worst=min(ys), years=m["years"])
if __name__ == "__main__":
    C.init(); rows = {}; bad = 0
    for code in CODES:
        d = W.data_of(code)
        d["reg"]["BOTH"] = [not (h is False and r is False) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
        cur = C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
        chk = simx(d, {**BASE, "anyx": True, "XN": "ALL"}, C.FULL, 20, retain=True)  # 永不熊 → 应与现行一致
        bad += abs(cur["nav"][-1]["nav"] - chk["nav"][-1]["nav"]) > 1e-9
        new = simx(d, {**BASE, "anyx": True, "XN": "BOTH"}, C.FULL, 20, retain=True)
        h1x = simx(d, {**BASE, "anyx": True, "XN": "H1"}, C.FULL, 20, retain=True)
        rows[code] = {k: stats({x["date"]: x["nav"] for x in r["nav"]}) for k, r in (("现行", cur), ("双熊破线卖", new), ("H1熊破线卖", h1x))}
        rows[code]["name"] = NAMES[code]
    print(f"自检（新引擎关掉破线卖 = 现行）：{'通过' if bad == 0 else f'失败 {bad} 只'}\n")
    for code in CODES:
        print(f"{code} {rows[code]['name']}")
        for k in ("现行", "双熊破线卖", "H1熊破线卖"):
            m = rows[code][k]
            print(f"   {k:6s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} 逐年均 {m['avg']*100:5.1f}% 赚钱 {m['pos']}/{m['n']} 最差 {m['worst']*100:5.1f}% ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n## 11 只平均")
    for k in ("现行", "双熊破线卖", "H1熊破线卖"):
        f = lambda key: statistics.mean(rows[c][k][key] for c in CODES)
        print(f"  {k:6s} 年化 {f('cagr')*100:5.1f}% 回撤 {f('mdd')*100:6.1f}% 卡玛 {f('cal'):4.2f} 逐年均 {f('avg')*100:5.1f}% 最差年均 {f('worst')*100:5.1f}%")
    better = lambda k: sum(rows[c][k]["cal"] > rows[c]["现行"]["cal"] for c in CODES)
    print(f"  卡玛变好只数：双熊破线卖 {better('双熊破线卖')}/11，H1熊破线卖 {better('H1熊破线卖')}/11")
