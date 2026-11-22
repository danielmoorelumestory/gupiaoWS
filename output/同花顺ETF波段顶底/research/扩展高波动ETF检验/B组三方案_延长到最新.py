"""用户问（2026-11-20）：回测时间放到今天会不会好一些。事前写定：
全部改用腾讯后复权日线现取（11 只 ETF + 择时用的 159915、510880 后复权与 sh000300 指数），同一份数据分别截到 2026-11-10 与最新完整交易日，
跑 现行 / 双牛买·死叉卖 / 双牛买·双熊破线卖 / 双熊破线卖 四种（规则同前两个脚本），只看“多出来的几天”带来的差别。历史统计，不构成投资建议。"""
import importlib.util, json, urllib.request, datetime, statistics, time
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
C, W, X, RM = Z.C, Z.W, Z.X, Z.X.RM
TODAY = datetime.date.today().isoformat()
def fetch(sym, fq="hfq"):
    rows, z = {}, TODAY
    for _ in range(12):
        for host in ("https://web.ifzq.gtimg.cn/", "https://proxy.finance.qq.com/ifzqgtimg/"):
            try:
                d = json.load(urllib.request.urlopen(f"{host}appstock/app/fqkline/get?param={sym},day,2005-01-01,{z},640,{fq}", timeout=30))["data"][sym]; break
            except Exception: time.sleep(1)
        b = d.get(f"{fq}day") or d.get("day") or []
        new = [x for x in b if x[0] not in rows]
        for x in b: rows[x[0]] = x
        if len(b) < 640 or not new: break
        z = (datetime.date.fromisoformat(b[0][0]) - datetime.timedelta(days=1)).isoformat()
    return [rows[k] for k in sorted(rows)]
def mk(sym): return ("sh" if sym[0] in "5" else "sz") + sym
if __name__ == "__main__":
    C.init()
    raw = {c: fetch(mk(c)) for c in Z.CODES}
    leg = {c: {x[0]: float(x[2]) for x in fetch(mk(c))} for c in ("159915", "510880")}
    hs = {x[0]: float(x[2]) for x in fetch("sh000300", "qfq")}
    last = min(max(r[-1][0] for r in raw.values()), max(hs))
    if last == TODAY and datetime.datetime.now().hour < 15: last = sorted(hs)[-2]  # 盘中不用今天未完成的 K 线
    print(f"最新完整交易日 {last}")
    out = {}
    for END in ("2026-11-10", last):
        cut = lambda m: {k: v for k, v in m.items() if k <= END}
        r2 = RM.ma_state(RM.ratio(cut(leg["159915"]), cut(leg["510880"])), 20); h1 = RM.ma_state(RM.ratio(cut(hs), cut(leg["510880"])), 20)
        FULL = ("1900-01-01", END)
        for code in Z.CODES:
            rows = [{"date": x[0], "open": x[1], "high": x[3], "low": x[4], "close": x[2], "adjusted_close": x[2], "share_factor": "1", "cumulative_cash": "0"} for x in raw[code] if x[0] <= END]
            d = X.entry(code, rows, r2, h1)
            d["reg"]["BOTH"] = [not (h is False and r is False) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
            d["reg"]["BULL2"] = [bool(h) and bool(r) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
            runs = {"现行": C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, FULL, 20, retain=True),
                    "双熊破线卖": Z.simx(d, {**Z.BASE, "anyx": True, "XN": "BOTH"}, FULL, 20, retain=True),
                    "双牛买·死叉卖": C.K.simulate_kd(d, {**C.T.BASE, "N": "BULL2"}, FULL, 20, retain=True),
                    "双牛买·双熊破线卖": Z.simx(d, {**Z.BASE, "N": "BULL2", "anyx": True, "XN": "BOTH"}, FULL, 20, retain=True)}
            for k, r in runs.items():
                m = C.window_metrics({x["date"]: x["nav"] for x in r["nav"]}, FULL); ys = list(m["years"].values())
                out[(END, code, k)] = dict(cagr=m["cagr"], mdd=m["mdd"], cal=m["cal"], avg=statistics.mean(ys), worst=min(ys), y26=m["years"].get("2026", float("nan")))
    for END in ("2026-11-10", last):
        print(f"\n## 截至 {END}（11 只平均）")
        for k in ("现行", "双熊破线卖", "双牛买·死叉卖", "双牛买·双熊破线卖"):
            f = lambda key: statistics.mean(out[(END, c, k)][key] for c in Z.CODES)
            print(f"  {k:10s} 年化 {f('cagr')*100:5.1f}% 回撤 {f('mdd')*100:6.1f}% 卡玛 {f('cal'):4.2f} 逐年均 {f('avg')*100:5.1f}% 最差年均 {f('worst')*100:5.1f}% 2026年 {f('y26')*100:5.1f}%")
    print(f"\n## 单只 2026 年收益：11-10 → {last}")
    for code in Z.CODES:
        print(f"  {code} {Z.NAMES[code]:8s} " + " ｜ ".join(f"{k} {out[('2026-11-10', code, k)]['y26']*100:+.0f}→{out[(last, code, k)]['y26']*100:+.0f}" for k in ("现行", "双牛买·死叉卖")))
