"""用户问（2026-11-18）：VOLT 用在 QQQ 上可以吗。事前写定：信号仍用纳指100 指数（Yahoo ^NDX，与 美股指数长历史择时.py 的 VOLT 完全相同），
收益用 QQQ 复权收盘（含分红、扣管理费），1999-03 上市；仓位：信号日收盘决定（lag0=当日收盘成交，lag1=次日收盘成交）；0.1%×换手；空仓 0 与 4% 两档（美元货币基金约 4~5%，近年）。
窗口：上市后 260 日起全历史、2010 起、2020 起，及 2000s/2010s。历史统计，不构成投资建议。"""
import importlib.util, json, gzip
sp = importlib.util.spec_from_file_location("L", "美股指数长历史择时.py"); L = importlib.util.module_from_spec(sp); sp.loader.exec_module(L)
Q = dict(json.loads(gzip.decompress((L.RAW / "yahoo-QQQ-adj.json.gz").read_bytes())))
ds, iv, W = L.states(L.load("NDX")); pos = {t: i for i, t in enumerate(ds)}
qd = [t for t in sorted(Q) if t in pos]; qv = [Q[t] for t in qd]; start = qd[260]
for cash in (0.0, 0.04):
    for lag in (0, 1):
        print(f"\n## 空仓年化 {cash*100:.0f}% ｜ {'当日收盘成交' if lag == 0 else '次日收盘成交'}")
        for k in ("一直持有", "VOLT", "V15iT"):
            w = [W[k][pos[t]] for t in qd]
            if lag: w = [w[0]] + w[:-1]
            nav = L.run(qd, qv, w, cash)
            out = []
            for wn, (a, b) in {"全历史": (start, "2026-11-10"), "2010起": ("2010-01-01", "2026-11-10"), "2020起": ("2020-01-01", "2026-11-10"), "2000s": (start, "2009-12-31"), "2010s": ("2010-01-01", "2019-12-31")}.items():
                m = L.metrics(nav, a, b); out.append(f"{wn} {m['cagr']*100:5.1f}%/{m['mdd']*100:6.1f}%")
            print(f"  {k:6s} " + " ｜ ".join(out))
