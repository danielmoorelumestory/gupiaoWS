"""Render the complete fixed-rule results, including unfavorable sensitivities."""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
NAMES = {"COMBO_WAIT": "底部回升＋MA10（主规则）", "MA10_ONLY": "仅MA10",
         "BUY_HOLD": "买入持有", "COMBO_SAME": "同日回升且站上MA10（敏感性）"}
ORDER = list(NAMES)


def read(name):
    return list(csv.DictReader((OUT / name).open()))


def percent(value, digits=2):
    return f"{float(value)*100:.{digits}f}%" if value not in (None, "") else "—"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |"]
                      + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def main():
    meta = json.loads((OUT / "summary.json").read_text())
    verification = json.loads((OUT / "independent_verification.json").read_text())
    metrics, aggregate, yearly = read("metrics.csv"), read("aggregate_metrics.csv"), read("yearly_cost10.csv")
    def agg(strategy, cost=10):
        return next(m for m in aggregate if m["strategy"] == strategy and int(m["cost_bps_round_trip"]) == cost)
    primary = [m for m in metrics if m["segment"] == "historical_holdout" and m["cost_bps_round_trip"] == "10"]
    def cell(code, strategy):
        return next(m for m in primary if m["code"] == code and m["strategy"] == strategy)
    codes = sorted({m["code"] for m in primary})
    boot = meta["bootstrap"]
    sections = ["# ETF波段顶底结合10日线：固定规则完整资金回测",
        "\n2026-11-13 归档。规则先固定，随后才计算本轮收益；没有按结果调参。主规则协议提交 `b343cdd`，执行和独立验证代码提交 `123ebc9`。",
        "\n## 结论",
        "\n在这9只ETF、2021-01-04至2026-11-10、每次往返费用10bp的固定口径下，**加入底部回升条件没有显示收益增强优势，但减少了交易和资金暴露，历史回撤也更小**。这一风险变化不能单独证明底部指标的选时更好，因为大量时间持有现金。",
        "\n" + table(["规则", "累计净收益", "净年化", "最大回撤", "平均持仓时间占比", "买入次数（9账户合计）"],
            [[NAMES[s], percent(agg(s)["total_return"]), percent(agg(s)["cagr"]), percent(agg(s)["max_drawdown"]),
              percent(agg(s)["time_exposure"]), agg(s)["entries"]] for s in ORDER]),
        f"\n主规则相对仅MA10的组合年化差为 **{float(meta['primary_cagr_difference'])*100:+.2f}个百分点**；仅{meta['positive_etfs_combo_minus_ma']}/9只ETF的该差值为正。20交易日日期块、2000次配对重采样的95%区间为 **[{boot['cagr_difference_ci_low']*100:+.2f}, {boot['cagr_difference_ci_high']*100:+.2f}]个百分点**，跨过0。预先设定的历史收益支持条件未满足，也不能据此断言真实长期收益必然更差。",
        "\n组合净值是9个独立子账户各投入相同初始资金后相加，账户之间不再平衡。最大回撤根据收盘净值计算，表中是分散组合回撤，并非单只ETF最坏回撤。买入持有是本轮实际的全期持仓对照，和上一轮‘任意10日窗口平均收益’是不同口径。",
        "\n## 固定交易规则",
        "\n- 指标保持原公式：`V=100*SUM(MAX(C-REF(C,1),0),13)/SUM(ABS(C-REF(C,1)),13)`。本轮不修改13、30或10。",
        "- 主规则：空仓时出现V<30，记录一次底部条件；随后V回到≥30且收盘价>10日简单均线，发出买入信号。允许先回升、后站上均线，不另加等待期限；若再次低于30，须再次回到≥30。",
        "- 买入实际成交后消耗这次底部条件。持仓中忽略新的买入条件；持仓收盘价<MA10就卖，不要求指标到70。退出后的新空仓周期需要重新观察低位条件；卖出信号日若V<30，可供下一周期使用。",
        "- 信号由收盘确认，下一可用行情行开盘成交；不使用信号当天收盘成交价。收盘等于均线时不产生买卖。无加仓、无做空。",
        "- 仅MA10：空仓且收盘>MA10买入，持仓且收盘<MA10卖出。买入持有：第一天收盘后发出买单，下一行开盘买入后一直持有。所有规则从现金开始。",
        "- 同日版本：仅在`前日V<30≤当日V`且当日收盘>MA10时买入；卖出相同。该版本事先声明为敏感性，不能根据结果替换主规则。",
        "- 每次往返10bp对应买、卖各5bp（各0.05%），另外列出0和30bp。买入份额=`交易现金/[开盘价*(1+单边费率)]`；卖出扣单边费率。理论上可交易零碎份额，不含最低佣金/整手约束。",
        "- 分红按除权日经济权益计入独立现金/应收储备，之后不投入交易；持有份额在开盘前按拆分比例调整。新买入者不拿买入当日除息前的分红。闲置现金不计息。",
        "- 期末剩余仓位按末日收盘价估值退出并扣单边费用，单独标为`forced_end`，不计入规则自然完成交易的胜率。它是统一估值假设，不表示当时出现了卖出信号。",
        "\n## 各ETF主结果（往返10bp）",
        "\n" + table(["代码/类别", "组合净年化", "仅MA10净年化", "持有净年化", "组合最大回撤", "组合买入次数"],
            [[f"{c} {cell(c, 'COMBO_WAIT')['label']}", percent(cell(c, "COMBO_WAIT")["cagr"]),
              percent(cell(c, "MA10_ONLY")["cagr"]), percent(cell(c, "BUY_HOLD")["cagr"]),
              percent(cell(c, "COMBO_WAIT")["max_drawdown"]), cell(c, "COMBO_WAIT")["entries"]] for c in codes]),
        "\n主规则胜过仅MA10的ETF是沪深300、上证红利、军工，其余6只没有胜过；不能把这3只事后选出作为已验证的适用范围。组合对半导体、纳指100、黄金的参与较少，完整净值和逐笔记录可检查具体错失或亏损区间。",
        "\n" + table(["规则", "自然卖出次数", "期末估值退出次数", "自然完成交易净胜率", "平均持有行情行数", "平均资金暴露"],
            [[NAMES[s], agg(s)["natural_exits"], agg(s)["forced_exits"], percent(agg(s)["natural_win_rate"]),
              f"{float(agg(s)['mean_holding_sessions']):.2f}", percent(agg(s)["capital_exposure"])] for s in ORDER]),
        "\n买入次数和胜率是9账户逐笔统计；平均持仓时间是每日持有状态的平均，平均资金暴露是每日持仓市值/总权益的平均。自然卖出在开盘发生，其当日收盘视为现金状态；期末估值退出日仍计为持仓日。持有期包含入场至出场之间的持仓行情区间，开盘自然退出日不加一天。",
        "\n## 费用敏感性（同一主时段，净年化）",
        "\n" + table(["往返费用", *[NAMES[s] for s in ORDER]],
            [[f"{cost}bp", *[percent(agg(s, cost)["cagr"]) for s in ORDER]] for cost in (0, 10, 30)]),
        "\n零费用时主规则仍低于仅MA10，说明主口径的收益差距并非仅由佣金造成。30bp时仅MA10被高换手费用明显拖累，主规则年化略高于仅MA10，但仍低于持有；不能选这个费用场景替代预先声明的10bp主口径。现金等待和低换手是本规则的主要特征。",
        "\n## 各年组合净收益（往返10bp）",
        "\n" + table(["年份", *[NAMES[s] for s in ORDER]],
            [[year+('（截至11-10）' if year == '2026' else ''),
              *[percent(next(r for r in yearly if r['year'] == year and r['strategy'] == s)['net_return'])
                for s in ORDER]] for year in sorted({r["year"] for r in yearly})]),
        "\n## 数据、统计和复验范围",
        "\n数据复用上一轮审查通过的9只ETF原始OHLC、拆分/分红因子，截止2026-11-10，不接入11月13日盘中截图值。510500因604处复权核对不符继续排除，未事后换样本。信号使用连续复权收盘`raw_close*s+u`，成交与持仓估值使用未复权价格并单独处理权益。该输入与独立行情后复权价格通过既定容差审查，但未逐次核实与同花顺App各次除权后的前复权口径一致。",
        "\n2021年起9只ETF共有同期数据。159915缺2021-02-08、512480缺2021-03-26、513100缺2022-01-13；不臆造成交价，执行使用该ETF下一个有行情的开盘。组合仅为净值汇总前填最近估值。全样本期均为正成交量；引擎遇零量行会取消待执行单并在收盘重新判断，本轮没有这种执行案例。",
        "\n主组合从2021-01-04现金起步，到2026-11-10，共1417个汇总行情日、2136自然日。完整历史/2021年前的每只ETF可用起点不同，只作逐ETF补充，不混成等历史长度的组合；不足365自然日的开发期不年化。",
        "\n重采样将已实现的组合每日对数收益按共同日期分成20日块，两策略配对抽取，2000次，种子20261113；最后一块可短于20日。抽取的是既有收益块，不是重新拼接价格生成交易，也不表示未来预测区间。‘historical_holdout’只是此前固定的历史分段名称：当前ETF存续、市场经历及此前指标研究已知，不是真正未看过的样本外验证。样本小且含存续选择，日线开盘理论成交没有模拟盘口、整手、最低佣金或排队限制。",
        f"\n独立复核结果：**{verification['status']}**。本轮由本地另一路计算程序使用Fraction精确分数重算信号，以区间搜索和闭式份额/分红账本核对{verification['metrics_checked']}组指标、{verification['trades_checked']}条交易记录、{verification['daily_account_nav_checked']}条账户日净值、{verification['aggregate_nav_checked']}条组合日净值，最大数值误差{verification['max_absolute_numeric_error']:.3g}。记录包含费用和历史分段的重复案例，不能视为这么多独立样本。另有10项合成边界测试通过。",
        "\n## 文件与重跑",
        "\n- [固定协议](protocol.json)，[实现](strategy.py)，[边界测试](test_strategy.py)，[独立验证](verify_backtest.py)。",
        "- [全部逐ETF/分段/费用指标](results/metrics.csv)，[主时段组合指标](results/aggregate_metrics.csv)，[年度收益](results/yearly_cost10.csv)。",
        "- [逐笔交易gzip CSV](results/trades.csv.gz)，[账户日净值（10bp）](results/daily_nav_cost10.csv.gz)，[组合日净值（所有费用）](results/aggregate_nav.csv.gz)。",
        "- [结果摘要与协议哈希](results/summary.json)，[独立复核记录](results/independent_verification.json)，[完整性清单](bundle-manifest.json)。",
        "\n在本目录运行：\n\n```sh\npython3 -m unittest -v test_strategy.py\npython3 run_backtest.py\npython3 verify_backtest.py\npython3 render_report.py\npython3 verify_bundle.py\n```",
        "\n全部使用Python标准库，重跑不联网、不更新输入数据、不改指标参数。旧指标公式和上一轮固定10日窗口研究保留原样。"]
    for segment, title in (("development", "2021年前补充"), ("all_history", "各ETF完整历史补充")):
        selected = [m for m in metrics if m["segment"] == segment and m["cost_bps_round_trip"] == "10"]
        rows = []
        for c in codes:
            base = next(m for m in selected if m["code"] == c)
            values = [next(m for m in selected if m["code"] == c and m["strategy"] == s) for s in ORDER]
            rows.append([c, f"{base['first']}～{base['last']}", *[percent(v["cagr"]) for v in values]])
        sections.extend([f"\n## {title}（10bp，逐ETF净年化）", "\n"+table(["代码", "有效时段", *[NAMES[s] for s in ORDER]], rows)])
    (ROOT / "结果报告.md").write_text("\n".join(sections)+"\n")
    print("saved 结果报告.md")


if __name__ == "__main__":
    main()
