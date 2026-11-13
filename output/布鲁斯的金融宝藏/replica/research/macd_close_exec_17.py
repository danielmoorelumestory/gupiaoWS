"""17 只 MACD优秀 逐只：尾盘买/尾盘卖（读 macd_close_exec_results.csv，另逐只算每次信号尾盘相对次日开盘的差）。"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "research")
from codex_macd_common import load, ema
t = pd.read_csv("research/macd_close_exec_results.csv", dtype={"code": str}); G = t[t.good & (t.years >= 3)].set_index("code")
ORDER = ["588200","512480","562500","159667","159851","515790","513090","512880","512070","159869","516160","512200","513130","159852","159792","159865","159883"]
G = G.loc[ORDER]; P = lambda v: f"{v*100:+.1f}"
print("A. MACD 年化% 与回撤%：次开 / 尾盘买 / 尾盘卖 / 尾盘买卖 ｜ 回撤 次开 / 尾盘卖 ｜ 尾盘卖 前半差 后半差")
for cd, r in G.iterrows():
    print(f"{cd} {r['name'][:6]:<7} " + " ".join(P(r[f'MACD|{e}']) for e in ("基准","尾盘买","尾盘卖","尾盘买卖")) +
          f" ｜ {P(r['MACD|基准_dd'])} {P(r['MACD|尾盘卖_dd'])} ｜ {P(r['MACD|尾盘卖_h1']-r['MACD|基准_h1'])} {P(r['MACD|尾盘卖_h2']-r['MACD|基准_h2'])}")
print("\nB. A20 / A20K 年化%：次开 / 尾盘卖")
for cd, r in G.iterrows():
    print(f"{cd} {r['name'][:6]:<7} A20 {P(r['A20|基准'])} {P(r['A20|尾盘卖'])} ｜ A20K {P(r['A20K|基准'])} {P(r['A20K|尾盘卖'])} ｜ 回撤 A20K {P(r['A20K|基准_dd'])} {P(r['A20K|尾盘卖_dd'])}")
print("\nC. 每次信号（2016 起）：尾盘买 平均/占便宜比例 ｜ 尾盘卖 平均/占便宜比例 ｜ 次数")
for cd in ORDER:
    d, dv, mm, c = load(cd); o = d.open.values * c / d.close.values; dif = ema(c, 2/13) - ema(c, 2/27); m = dif > ema(dif, .2)
    i0 = max(70, d.index.searchsorted(pd.Timestamp("2016-01-04"))); b = []; s = []
    for k in range(i0, len(c) - 1):
        if m[k] and not m[k-1]: b.append(o[k+1]/c[k]-1)
        if m[k-1] and not m[k]: s.append(c[k]/o[k+1]-1)
    b, s = np.array(b), np.array(s)
    print(f"{cd} {G.loc[cd,'name'][:6]:<7} 买 {b.mean()*100:+.3f}% {(b>0).mean():.0%} ｜ 卖 {s.mean()*100:+.3f}% {(s>0).mean():.0%} ｜ {len(b)}/{len(s)}")
