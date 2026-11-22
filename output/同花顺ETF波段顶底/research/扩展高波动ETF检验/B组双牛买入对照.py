"""用户要求（2026-11-20）：B 组改成「沪深300÷红利 与 创业板÷红利 两个择时都是牛市」时金叉才买，卖出不变。事前写定：
  现行        H1 牛 金叉次日开盘买；死叉当日收盘卖
  双牛买·死叉卖     H1 与 R2-20 都牛 金叉买；死叉卖（“卖出不变”= 现行卖法）
  双牛买·双熊破线卖  同上买入；死叉，或 H1、R2 都熊且收盘<10日线 当日卖（“卖出不变”= 上一轮的卖法）
标的、数据、口径、自检同 B组双熊破线卖对照.py（线上 11 只，截至 2026-11-10）。历史统计，不构成投资建议。"""
import importlib.util, statistics, sys
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
C, W = Z.C, Z.W
KS = ["现行", "双牛买·死叉卖", "双牛买·双熊破线卖"]
if __name__ == "__main__":
    C.init(); rows = {}
    for code in Z.CODES:
        d = W.data_of(code)
        d["reg"]["BOTH"] = [not (h is False and r is False) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
        d["reg"]["BULL2"] = [bool(h) and bool(r) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
        runs = {"现行": C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True),
                "双牛买·死叉卖": C.K.simulate_kd(d, {**C.T.BASE, "N": "BULL2"}, C.FULL, 20, retain=True),
                "双牛买·双熊破线卖": Z.simx(d, {**Z.BASE, "N": "BULL2", "anyx": True, "XN": "BOTH"}, C.FULL, 20, retain=True)}
        rows[code] = {k: {**Z.stats({x["date"]: x["nav"] for x in r["nav"]}), "trades": sum(1 for t in r["trades"] if not t.get("forced_end"))} for k, r in runs.items()}
    for code in Z.CODES:
        print(f"{code} {Z.NAMES[code]}")
        for k in KS:
            m = rows[code][k]
            print(f"   {k:10s} 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} 逐年均 {m['avg']*100:5.1f}% 赚钱 {m['pos']}/{m['n']} 最差 {m['worst']*100:5.1f}% 交易 {m['trades']:3d} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
    print("\n## 11 只平均")
    for k in KS:
        f = lambda key: statistics.mean(rows[c][k][key] for c in Z.CODES)
        up = sum(rows[c][k]["cal"] > rows[c]["现行"]["cal"] for c in Z.CODES); dn = sum(rows[c][k]["mdd"] > rows[c]["现行"]["mdd"] for c in Z.CODES)
        print(f"  {k:10s} 年化 {f('cagr')*100:5.1f}% 回撤 {f('mdd')*100:6.1f}% 卡玛 {f('cal'):4.2f} 逐年均 {f('avg')*100:5.1f}% 最差年均 {f('worst')*100:5.1f}% 交易 {f('trades'):5.1f} ｜ 卡玛变好 {up}/11 回撤变小 {dn}/11")
