"""逐次评估“提前卖出”事件（MACD 仍为金叉、被 10 日线规则卖出）。
提前卖出后要等死叉再金叉才重新买入，所以与纯 MACD 的唯一区别是“提前卖出日开盘 → 死叉次日开盘”这段持有。
事件效果 = 提前卖出价 / 死叉卖出价 − 1（复权开盘价；>0 表示提前卖对了）。两边买卖次数相同，成本抵消。
规则：W5（5日背离后破MA10）、W1（红柱缩短后破MA10）、B（直接破MA10，作为不加背离条件的基准）。样本：页面清单+半导体，上市后第60个交易日起。"""
import json, numpy as np, pandas as pd
exec(open("research/macd_exit_divergence.py").read().split("rows = []")[0])
good = set(pd.read_csv("research/macd_page_etfs_plus_results.csv", dtype={"code": str}).query("good").code)
ev = []
for code, name, grp in json.load(open("data/page_etfs_plus.json")):
    d, dv, mult, adj, _ = load(code)
    if len(d) < 120: continue
    ao = (d.open * adj / d.close).values   # 复权开盘价
    s = adj; dif = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()); dea = dif.ewm(span=9, adjust=False).mean(); m = (dif > dea).values
    for rule in ("W5", "W1", "B"):
        st = positions(adj, rule).values
        for i in range(61, len(d) - 1):
            if st[i - 1] and not st[i] and m[i]:            # 第 i 日收盘触发，i+1 开盘卖；MACD 仍金叉
                j = i
                while j < len(d) - 1 and m[j]: j += 1        # j：死叉信号日；纯 MACD 在 j+1 开盘卖
                if j >= len(d) - 1: continue                 # 死叉尚未出现（样本末尾），不计
                ev.append(dict(rule=rule, code=code, name=name, good=code in good, date=d.index[i].date(), days=j - i, gain=ao[i + 1] / ao[j + 1] - 1))
e = pd.DataFrame(ev); e.to_csv("research/macd_exit_events.csv", index=False)
names = {"W5": "5日背离后破MA10", "W1": "红柱缩短后破MA10", "B": "直接破MA10（基准）"}
for label, g0 in (("全部 63 只", e), ("MACD优秀 17 只", e[e.good])):
    print(f"\n==== {label}：提前卖出事件（效果 = 提前卖出价/死叉卖出价 − 1，%）")
    print(f"   {'规则':<16}{'事件数':>6}{'卖对比例':>8}{'平均':>8}{'中位':>8}{'卖对时平均':>10}{'卖错时平均':>10}{'距死叉天数中位':>12}")
    for k in ("W5", "W1", "B"):
        g = e.loc[e.rule == k].loc[lambda x: x.index.isin(g0.index)]
        print(f"   {names[k]:<14}{len(g):>6}{(g.gain>0).mean()*100:7.0f}%{g.gain.mean()*100:+8.2f}{g.gain.median()*100:+8.2f}{g[g.gain>0].gain.mean()*100:+10.2f}{g[g.gain<=0].gain.mean()*100:+10.2f}{g.days.median():10.0f}")
# 自助法：W5 事件的平均效果与“从 B 事件里随机抽同样多个”的平均相比
rng = np.random.default_rng(0); b = e[e.rule == "B"].gain.values; w = e[e.rule == "W5"].gain.values
sims = np.array([rng.choice(b, len(w), replace=False).mean() for _ in range(20000)])
print(f"\n从“直接破MA10”的 {len(b)} 个事件里随机抽 {len(w)} 个，平均效果 ≥ W5 实际平均 {w.mean()*100:+.2f}% 的概率：{(sims >= w.mean()).mean():.2%}")
w5 = e[e.rule == "W5"].sort_values("gain")
print("\nW5 事件中效果最好的 8 次："); print(w5.tail(8)[["code", "name", "date", "days", "gain"]].assign(gain=lambda x: (x.gain*100).round(1)).to_string(index=False))
print("\nW5 事件中效果最差的 8 次："); print(w5.head(8)[["code", "name", "date", "days", "gain"]].assign(gain=lambda x: (x.gain*100).round(1)).to_string(index=False))
print(f"\nW5 去掉效果最好的 3 次后平均：{w5.gain.iloc[:-3].mean()*100:+.2f}%（原 {w5.gain.mean()*100:+.2f}%）")
