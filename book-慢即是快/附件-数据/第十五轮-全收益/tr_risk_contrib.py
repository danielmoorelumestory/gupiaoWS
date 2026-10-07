"""第十五轮：第9章五项等权的风险贡献（谁在承担组合的波动）。
方法：月度收益协方差（与 tr_ref_plan.py 同一区间、同一月末估值），RC_i = w_i·(Σw)_i / (wᵀΣw)。
只比较“风险由谁承担”，不比较收益：替换方案的收益受样本期内恒生科技下跌影响，属于事后结果，不作依据。"""
import tr_ref_plan as P  # 复用同一数据对齐与月末规则（导入时会打印 tr_ref_plan 的结果）
import csv, pathlib
def monthly_series(series): return P.monthly([series[d] for d in P.dates])
def risk_contrib(names, weights, series):
    R = [monthly_series(series[n]) for n in names]; T = len(R[0])
    mean = [sum(r) / T for r in R]
    cov = [[sum((R[i][t] - mean[i]) * (R[j][t] - mean[j]) for t in range(T)) / T for j in range(len(R))] for i in range(len(R))]
    sw = [sum(cov[i][j] * weights[j] for j in range(len(R))) for i in range(len(R))]
    var = sum(weights[i] * sw[i] for i in range(len(R)))
    return var ** 0.5 * 12 ** 0.5, [weights[i] * sw[i] / var for i in range(len(R))]
if __name__ == "__main__":
    print("\n=== 风险贡献（月度协方差，年化组合波动）===")
    S = dict(P.S)
    # 替换方案：恒生科技换成沪深300全收益（同样按并集日期、最后可用价格对齐）
    from bisect import bisect_right
    raw = P.load("H00300"); avail = sorted(raw)
    S["沪深300(全收益)"] = {d: raw[avail[bisect_right(avail, d) - 1]] for d in P.dates}
    for title, names in (("原五项（恒生科技）", [k for k in P.S]),
                         ("替换：恒生科技→沪深300", [k for k in P.S if not k.startswith("恒生科技")] + ["沪深300(全收益)"])):
        vol, rc = risk_contrib(names, [0.2] * 5, S)
        print(f"### {title}  组合年化波动 {vol*100:.1f}%")
        for n, c in zip(names, rc): print(f"| {n} | 20% | {c*100:.0f}% |")
