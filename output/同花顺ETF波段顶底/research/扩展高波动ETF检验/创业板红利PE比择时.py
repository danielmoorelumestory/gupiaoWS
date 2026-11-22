"""用户问（2026-11-21）：文章说「创业板PE ÷ 中证红利PE < 3.5 投创业板，> 7 投红利」，能否据此优化择时：<3.5 才操作或重仓，>3.5 减仓，>7 不操作。事前写定：
数据：蛋卷基金 创业板指(SZ399006)、中证红利(SH000922) 周度市盈率（2016-11 起），比值 = 创业板PE/红利PE；
      每笔交易按「信号日之前（严格早于）最近一个周度比值」定仓位，持有期间仓位不变，空仓部分收益 0。
基础规则不变：A 组（线上 13 只）Y1·创业板择时；B 组（线上 11 只）金叉·沪深300择时。研究面板口径，截至 2026-11-10，单边 0.1%。
  现行          每笔满仓
  <7才买        比值 ≥7 的买点跳过（“>7 不操作”）
  <3.5才买      比值 ≥3.5 的买点跳过（“<3.5 才操作”）
  分档          <3.5 满仓，3.5–7 半仓，≥7 跳过（“<3.5 重仓、>3.5 减仓、>7 不操作”）
  分档·不跳过    <3.5 满仓，≥3.5 半仓
2016-11 之前的买点没有市盈率数据，按满仓。跳过的买点按“这一笔不做”处理（近似：不会因此提前出现下一次买入）。历史统计，不构成投资建议。"""
import importlib.util, json, datetime as dt, statistics, bisect
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
C, W = Z.C, Z.W
A = ['513310', '588200', '159869', '159851', '512760', '516520', '159667', '562500', '516510', '159939', '512670', '159998', '159852']
B = Z.CODES
def pe(s): return {dt.datetime.fromtimestamp(x["ts"] / 1000, dt.timezone(dt.timedelta(hours=8))).date().isoformat(): x["pe"] for x in json.load(open(f"data/raw/danjuan-pe-{s}.json"))["data"]["index_eva_pe_growths"]}
a, b = pe("SZ399006"), pe("SH000922"); KS = sorted(set(a) & set(b)); RV = [a[k] / b[k] for k in KS]
def ratio_before(day):
    i = bisect.bisect_left(KS, day) - 1
    return RV[i] if i >= 0 else None
def guard(f): return lambda r: 1.0 if r is None else f(r)  # 2016-11 之前没有市盈率数据：按现行满仓
RULES = {"现行": lambda r: 1.0, "<7才买": lambda r: 1.0 if r < 7 else 0.0, "<3.5才买": lambda r: 1.0 if r < 3.5 else 0.0,
         "分档": lambda r: 1.0 if r < 3.5 else (0.5 if r < 7 else 0.0), "分档·不跳过": lambda r: 1.0 if r < 3.5 else 0.5}
def reweight(res, f):
    nav = res["nav"]; idx = {p["row_index"]: k for k, p in enumerate(nav)}; out = [p["nav"] for p in nav]
    eq, last, ws = 1.0, 0, []
    scale = [None] * len(nav)  # 每天的 (起点权益, 起点基准净值, 权重)
    for t in res["trades"]:
        s, e = idx.get(t["entry_index"]), idx.get(t["exit_index"], len(nav) - 1)
        if s is None: continue
        ws.append((s, e, guard(f)(ratio_before(t["entry_signal_date"]))))
    new, E, k0 = [], 1.0, 0
    base_prev = 1.0; cur = None
    for k, p in enumerate(nav):
        while cur is None and ws and ws[0][0] <= k:
            s, e, w = ws.pop(0); cur = (s, e, w, E, nav[s - 1]["nav"] if s > 0 else 1.0)
        if cur:
            s, e, w, E0, N0 = cur; v = E0 * (1 - w + w * p["nav"] / N0)
            if k >= e: E = v; cur = None
            new.append(v)
        else: new.append(E)
    return {p["date"]: v for p, v in zip(nav, new)}, sum(1 for s in res["trades"] if guard(f)(ratio_before(s["entry_signal_date"])) > 0)
if __name__ == "__main__":
    C.init(); out = {}
    print("比值最新：", KS[-1], round(RV[-1], 2))
    for g, codes in (("A", A), ("B", B)):
        for c in codes:
            d = W.data_of(c); r = W.run(d, g)
            base = Z.stats({p["date"]: p["nav"] for p in r["nav"]}); chk, _ = reweight(r, RULES["现行"])
            assert abs(Z.stats(chk)["cagr"] - base["cagr"]) < 1e-9, c  # 自检：满仓重算与原净值一致
            for k, f in RULES.items():
                nav, n = reweight(r, f); m = Z.stats(nav); m["trades"] = n; out[(g, c, k)] = m
        print(f"\n## {g} 组（{len(codes)} 只平均，研究面板截至 2026-11-10）")
        for k in RULES:
            F = lambda key: statistics.mean(out[(g, c, k)][key] for c in codes)
            up = sum(out[(g, c, k)]["cal"] > out[(g, c, "现行")]["cal"] for c in codes)
            yrs = {y: statistics.mean(out[(g, c, k)]["years"][y] for c in codes if y in out[(g, c, k)]["years"]) for y in ("2020", "2021", "2022", "2023", "2024", "2025", "2026")}
            print(f"  {k:8s} 年化 {F('cagr')*100:5.1f}% 回撤 {F('mdd')*100:6.1f}% 卡玛 {F('cal'):4.2f} 逐年均 {F('avg')*100:5.1f}% 交易 {F('trades'):5.1f} 卡玛变好 {up}/{len(codes)} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in yrs.items()))
