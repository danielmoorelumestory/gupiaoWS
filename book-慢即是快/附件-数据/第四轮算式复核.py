"""本书第四轮教学算式复核；非真实交易回测。运行：python3 本文件路径。"""
from math import isclose

checks = []

def verify(name, actual, expected, tolerance=1e-9):
    assert isclose(actual, expected, rel_tol=0, abs_tol=tolerance), (name, actual, expected)
    checks.append((name, actual))

verify("EPS与PE共同下降后的价格", 1.5 * 16, 24)
verify("价格跌幅", 24 / 40 - 1, -0.4)
verify("调整后PE", 24 / (2 - 0.4), 15)
for eps, pe, expected in [(1.5, 12, 18), (2, 16, 32), (2.2, 18, 39.6)]:
    verify("回归条件价格", eps * pe, expected)
verify("回归条件买价", (32 + 0.6) / 1.10, 29.64, 0.005)
verify("回归失败的新价格", 1.2 * 12, 14.4)

fee = 0.001
for name, buy, sell, dividends, expected_profit, expected_pct in [
    ("回归成功", 24, 32, 0.6, 8544, 35.56),
    ("回归失败", 24, 14, 0, -10038, -41.78),
    ("增长成功", 20, 25, 0.5, 5455, 27.25),
    ("增长失败", 20, 7.2, 0, -12827.2, -64.07),
    ("反转成功", 4, 6, 0, 1990, 49.70),
    ("反转失败", 4, 0.8, 0, -3204.8, -80.04),
]:
    cost = buy * 1000 * (1 + fee)
    final = sell * 1000 * (1 - fee) + dividends * 1000
    verify(name + "净损益", final - cost, expected_profit)
    verify(name + "累计收益百分数", 100 * (final / cost - 1), expected_pct, 0.005)

for years, expected in [(3, 115.4), (5, 58.5), (10, 25.9)]:
    verify("十倍EPS年化百分数", 100 * (10 ** (1 / years) - 1), expected, 0.05)
verify("估值减半时十年EPS要求", 100 * (20 ** 0.1 - 1), 34.9, 0.05)
verify("成熟单店资本回报", 40 / 200, 0.2)
verify("旧店收入亿元", 100 * 400 / 10000, 4)
verify("新店收入亿元", 50 * 200 / 10000, 1)
verify("新店利润亿元", 1 * 0.04, 0.04)
verify("扩张总利润亿元", 0.4 + 0.04, 0.44)
verify("扩张利润增长", 0.44 / 0.4 - 1, 0.1)
verify("扩张初始投入亿元", 50 * 200 / 10000, 1)
verify("增发后EPS", 0.44 / 1.2, 0.3666666666666667)
verify("增发后EPS变化百分数", 100 * ((0.44 / 1.2) / 0.4 - 1), -8.33, 0.005)
verify("收入增长后的EPS练习", 100 * (1.3 * 0.08 / 0.10 / 1.1 - 1), -5.45, 0.005)
verify("估值减半抵消增长", 1.2 ** 3 * 0.5 - 1, -0.136)

for burns, expected in [([2, 2, 2, 2], [8.5, 4, 1.5, -3]), ([2, 1, 0.5, 0], [8.5, 5, 4, 1.5])]:
    cash = 12
    for burn, debt, result in zip(burns, [1, 2, 0, 2], expected):
        cash -= burn + 0.5 + debt
        verify("季度现金", cash, result)
verify("融资与利息后的年末现金", 1.5 + 2 - 0.2, 3.3)
verify("反转稀释EPS", 1 / 2, 0.5)
verify("经营资产减净债务", 20 - 15, 5)
verify("股权价值压力跌幅", (16 - 15) / (20 - 15) - 1, -0.8)
verify("原组合压力损失万元", 4 * 0.4 + 3 * 0.6 + 1 * 0.8, 4.2)
verify("调整后组合压力损失万元", 3 * 0.4 + 2 * 0.6 + 0.5 * 0.8, 2.8)
verify("调整后主动额度使用率", 5.5 / 20, 0.275)
verify("剩余主动额度万元", 20 - 5.5, 14.5)
verify("共同冲击拖累", 3 * 0.03 * 0.5, 0.045)

verify("宁德收入同比百分数", 100 * (362012554 / 400917045 - 1), -9.70, 0.005)
verify("宁德归母利润同比百分数", 100 * (50744682 / 44121248 - 1), 15.01, 0.005)
verify("宁德扣非同比百分数", 100 * (44992919 / 40091674 - 1), 12.23, 0.005)
verify("宁德2023归母利润收入比例", 100 * 44121248 / 400917045, 11.01, 0.005)
verify("宁德2024归母利润收入比例", 100 * 50744682 / 362012554, 14.02, 0.005)
verify("海底捞2021总损益亿元", -4161206 / 100000, -41.61, 0.005)
verify("海底捞2022总损益亿元", 1373216 / 100000, 13.73, 0.005)

print(f"{len(checks)}项算式核对通过。教学结果不构成历史策略验证。")
for name, number in checks:
    if "累计收益" in name or "年末现金" in name or "组合压力" in name:
        print(f"{name}: {number:.4f}")
