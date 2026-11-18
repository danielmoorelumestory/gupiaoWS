"""2026-11-18 与 Codex 商量后的第二轮（规则由 Codex 事前给出，跑之前写定，跑完不改）：
在 美股指数长历史择时.py 框架上（Yahoo 价格指数；信号当日收盘，仓位作用于下一交易日；0.1%×换手；空仓 0）增加：
  F50 / F75   固定 50% / 75% 仓位（判断择时是否优于单纯降仓位）
  A50VOLT     50% 底仓 + 50% 按 VOLT 进出（VOLT 开且指数>200日线 100%，否则 50%）
  B25_15      指数>200日线：min(1, 25%/σ20)；否则 0.5×min(1, 15%/σ20)；|Δw|<0.1 不调、回到 100% 立即调
另做敏感性：所有方案延迟一天执行（信号 t 日，仓位 t+2 日起）。
合格（新，按用户“减回撤、增收益”目标）：两指数 × 5 窗口都满足 回撤相对小 ≥25% 且 年化少 ≤2pp。旧标准（卡玛不降）一并报告。
历史统计，不构成投资建议。"""
import importlib.util, math, statistics
sp = importlib.util.spec_from_file_location("L", "美股指数长历史择时.py"); L = importlib.util.module_from_spec(sp); sp.loader.exec_module(L)
def extra(I, W):
    ds = sorted(I); iv = [I[t] for t in ds]; n = len(ds)
    r = [0] + [iv[i] / iv[i-1] - 1 for i in range(1, n)]
    VOL = [statistics.pstdev(r[i-19:i+1]) * math.sqrt(252) if i >= 20 else None for i in range(n)]
    M = [None] * n; s = 0
    for i in range(n):
        s += iv[i]
        if i >= 200: s -= iv[i-200]
        if i >= 199: M[i] = s / 200
    W["F50"] = [.5] * n; W["F75"] = [.75] * n
    W["A50VOLT"] = [1.0 if x else .5 for x in W["VOLT"]]
    cur = 1.0; out = []
    for i in range(n):
        v = VOL[i]; up = M[i] is None or iv[i] > M[i]
        w = 1.0 if not v else (min(1, .25 / v) if up else .5 * min(1, .15 / v))
        if abs(w - cur) >= .1 or (w == 1.0 and cur != 1.0): cur = w
        out.append(cur)
    W["B25_15"] = out
    return W
if __name__ == "__main__":
    ORDER = ["一直持有", "F75", "F50", "VOLT", "V15iT", "A50VOLT", "B25_15"]; res = {}
    WN = ["全历史", "1990起", "2000起", "2010起", "2020起"]
    for lag in (0, 1):
        for nm in ("NDX", "SPX"):
            I = L.load(nm); ds, iv, W = L.states(I); W = extra(I, W); start = ds[260]
            WINS = {"全历史": (start, "2026-11-10"), "1990起": ("1990-01-01", "2026-11-10"), "2000起": ("2000-01-01", "2026-11-10"), "2010起": ("2010-01-01", "2026-11-10"), "2020起": ("2020-01-01", "2026-11-10"),
                    "1990s": ("1990-01-01", "1999-12-31"), "2000s": ("2000-01-01", "2009-12-31"), "2010s": ("2010-01-01", "2019-12-31")}
            print(f"\n######## {nm} {'延迟一天' if lag else '正常'}")
            for k in ORDER:
                w = W[k] if not lag else [W[k][0]] + W[k][:-1]
                nav = L.run(ds, iv, w); line = []
                for wn, (a, b) in WINS.items():
                    m = L.metrics(nav, max(a, start), b); res[(lag, nm, wn, k)] = m
                    line.append(f"{wn}:{m['cagr']*100:5.1f}/{m['mdd']*100:5.1f}")
                print(f"  {k:8s} " + " ".join(line))
    for lag in (0, 1):
        print(f"\n######## 合格检查（{'延迟一天' if lag else '正常'}；新=回撤小≥25%且年化少≤2pp ｜ 旧=回撤小≥25%且卡玛不降；格内 回撤缩小/年化差pp）")
        for k in ORDER[1:]:
            new = old = True; cells = []
            for nm in ("NDX", "SPX"):
                for wn in WN:
                    m, h = res[(lag, nm, wn, k)], res[(lag, nm, wn, "一直持有")]
                    cut = 1 - m["mdd"] / h["mdd"]; da = (m["cagr"] - h["cagr"]) * 100
                    g1 = cut >= .25 and da >= -2; g2 = cut >= .25 and m["cal"] >= h["cal"]; new &= g1; old &= g2
                    cells.append(f"{nm[0]}{wn[:4]}:{cut*100:.0f}%/{da:+.1f}{'✓' if g1 else '✗'}")
            print(f"  新{'✓' if new else '✗'} 旧{'✓' if old else '✗'} {k:8s} " + " ".join(cells))
