"""第十五轮：同一区间、同一算法下，价格指数与全收益指数的单项对照（第3章3.2、附录F用）。
算法沿用原脚本：交易日对齐、年化按A股243日、日收益波动×√243、收盘价最大回撤。"""
import csv, math, statistics as st, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
def load(p): return dict((a, float(b)) for a, b in list(csv.reader(open(ROOT / p)))[1:])
TRADING = set(load("../sh000300.csv"))  # 用腾讯价格序列的交易日，剔除中证数据中的节假日行
def stats(series, start, end):
    d = [x for x in sorted(series) if start <= x <= end and x in TRADING]
    v = [series[x] / series[d[0]] for x in d]
    r = [v[i] / v[i - 1] - 1 for i in range(1, len(v))]
    pk, m = v[0], 0
    for x in v: pk = max(pk, x); m = max(m, 1 - x / pk)
    return d[0], d[-1], v[-1] ** (243 / len(r)) - 1, st.pstdev(r) * math.sqrt(243), m, v[-1]
PAIRS = [("沪深300", "../sh000300.csv", "H00300.csv"), ("中证红利", "../sh000922.csv", "H00922.csv"),
         ("中证500", "../sh000905.csv", "H00905.csv"), ("创业板指", "../sz399006.csv", "sz399606.csv")]
if __name__ == "__main__":
    start, end = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2009-06-01", "2026-09-30")
    print(f"| 指数 | 口径 | 起 | 止 | 年化 | 年化波动 | 最大回撤 | 期末(1起) |\n|---|---|---|---|---|---|---|---|")
    for name, price, tr in PAIRS:
        for label, f in (("价格", price), ("全收益", tr)):
            a, b, ann, vol, mdd, end_v = stats(load(f), start, end)
            print(f"| {name} | {label} | {a} | {b} | {ann*100:.2f}% | {vol*100:.1f}% | {mdd*100:.0f}% | {end_v:.3f} |")
