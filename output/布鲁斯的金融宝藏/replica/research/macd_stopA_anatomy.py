"""A 版止损为什么伤收益：17 只 MACD优秀，纯 MACD 每轮交易，看“涨到 +5% 前是否曾收盘 ≤ 成本”（A 会在此止损），
以及止损卖出价 vs 原死叉卖出价。口径：复权连续价，买金叉次日开盘、卖死叉次日开盘或止损次日开盘，扣双边 0.1%。2016 起。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, indicators
G = ["515790","159851","562500","512480","588200","513130","512200","159852","516160","512880","513090","159667","159792","159883","512070","159865","159869"]
R = []
for code in G:
    d, dv, mm, c = load(code); f, m, gold, dead = indicators(d, c)
    fac = c / d.close.values; oa = d.open.values * fac
    i = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04")))
    while i < len(d) - 1:
        if m[i] and not m[i - 1]:
            b = i
            while i < len(d) and m[i]: i += 1
            if i >= len(d) - 1: break
            e = i; cost = oa[b + 1]; stop = None; dip_day = None
            for k in range(b + 1, e):
                if c[k] >= cost * 1.05: break
                if c[k] <= cost: stop = k; break
            orig = oa[e + 1] / cost * 0.999 ** 2 - 1
            new = oa[stop + 1] / cost * 0.999 ** 2 - 1 if stop is not None else orig
            R.append(dict(code=code, date=d.index[b].date(), days=e - b, orig=orig, new=new, stopped=stop is not None, stop_day=(stop - b) if stop is not None else np.nan))
        else: i += 1
T = pd.DataFrame(R); T.to_csv("research/macd_stopA_anatomy_trades.csv", index=False)
print(f"17 只纯 MACD 共 {len(T)} 轮，A 止损触发 {T.stopped.mean():.0%}；其中买入后第 1 个收盘就触发 {(T.stop_day == 1).sum() / T.stopped.sum():.0%}，前 3 个收盘内 {(T.stop_day <= 3).sum() / T.stopped.sum():.0%}")
print(f"\n{'原交易最终收益':<12}{'笔数':>5}{'被A止损':>8}{'原平均':>9}{'止损后平均':>11}")
for lo, hi, nm in ((-1, 0, "亏损"), (0, 0.08, "0~8%"), (0.08, 0.15, "8~15%"), (0.15, 0.3, "15~30%"), (0.3, 10, "≥30%")):
    x = T[(T.orig > lo) & (T.orig <= hi)] if lo == -1 else T[(T.orig > lo) & (T.orig <= hi)]
    print(f"{nm:<12}{len(x):>5}{x.stopped.mean():>8.0%}{x.orig.mean()*100:>+8.2f}%{x.new.mean()*100:>+10.2f}%")
S = T[T.stopped]; d_ = S.new - S.orig
print(f"\n被止损的 {len(S)} 轮：原来最终亏的 {(S.orig <= 0).sum()} 轮共省下 {d_[S.orig <= 0].sum()*100:+.0f} 个百分点；原来最终赚的 {(S.orig > 0).sum()} 轮共少赚 {d_[S.orig > 0].sum()*100:+.0f} 个百分点"
      f"（其中原收益 ≥15% 的 {(S.orig >= 0.15).sum()} 轮少赚 {d_[S.orig >= 0.15].sum()*100:+.0f}）")
big = T[T.orig >= 0.15]
print(f"\n原收益 ≥15% 的大行情共 {len(big)} 轮，其中 {big.stopped.sum()} 轮（{big.stopped.mean():.0%}）在涨到 +5% 前曾收盘跌破成本、会被 A 止损：")
for _, r in big[big.stopped].sort_values("orig", ascending=False).iterrows():
    print(f"  {r.code} {r.date} 原 {r.orig*100:+.1f}% → 止损 {r.new*100:+.1f}%（买入后第 {int(r.stop_day)} 个收盘触发）")
