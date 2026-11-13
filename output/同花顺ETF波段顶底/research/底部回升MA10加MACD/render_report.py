"""Archive the confirmed rule and all fixed comparisons, without selecting ETFs."""
import csv
import json

from rules import ROOT, PROTOCOL, STRATEGIES

OUT = ROOT / "results"
NAMES = {"MACD_STATE": "新版：MACD状态确认卖出", "OLD_SAME": "相同买入，直接跌破MA10卖",
         "OLD_WAIT": "上一轮主规则（可延后站上MA10买）", "MA10_ONLY": "仅MA10", "BUY_HOLD": "买入持有"}


def read(name):
    return list(csv.DictReader((OUT / name).open()))


def pct(value, digits=2):
    return f"{float(value)*100:.{digits}f}%" if value not in (None, "") else "—"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
                     + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def main():
    meta = json.loads((OUT / "summary.json").read_text())
    verified = json.loads((OUT / "independent_verification.json").read_text())
    metrics, aggregate, yearly, diagnostic = map(read, ("metrics.csv", "aggregate_metrics.csv", "yearly_cost10.csv", "holding_diagnostics.csv"))
    def agg(s, cost=10):
        return next(r for r in aggregate if r["strategy"] == s and r["cost_bps_round_trip"] == str(cost))
    primary = [m for m in metrics if m["segment"] == "historical_holdout" and m["cost_bps_round_trip"] == "10"]
    def cell(c, s):
        return next(m for m in primary if m["code"] == c and m["strategy"] == s)
    codes = sorted({r["code"] for r in primary})
    comparison = next(r for r in meta["comparisons"] if r["primary"])
    boot = comparison["bootstrap"]
    d = [r for r in diagnostic if r["segment"] == "historical_holdout"]
    price = sum(int(r["natural_price_only_exits"]) for r in d)
    top = sum(int(r["natural_top_only_exits"]) for r in d)
    both = sum(int(r["natural_both_exits"]) for r in d)
    lines = ["# 底部回升＋MA10买入，MACD状态确认卖出：完整资金复盘",
        "\n2026-11-13归档。规则协议在计算本轮收益前提交为`070a95d`；实现及独立验证代码提交为`8e0eb0b`。不调整13、30/70、MA10或MACD参数。",
        "\n## 结果与判断",
        "\n**相比相同买入条件、跌破10日线直接卖出的旧版，新版历史收益提高，但回撤也扩大；尚未显示可靠的超额收益优势。**",
        "\n主时段2021-01-04至2026-11-10，9只ETF各投入相同初始资金、账户间不再平衡，每次往返费用10bp（0.1%，买卖各0.05%）：",
        "\n" + table(["规则", "累计净收益", "净年化", "最大回撤", "平均持仓时间占比", "买入次数（9账户合计）"],
            [[NAMES[s], pct(agg(s)["total_return"]), pct(agg(s)["cagr"]), pct(agg(s)["max_drawdown"]),
              pct(agg(s)["time_exposure"]), agg(s)["entries"]] for s in STRATEGIES]),
        f"\n直接对照的年化差为 **{comparison['cagr_difference']*100:+.2f}个百分点**，{comparison['positive_etfs']}/9只ETF改善。但预先固定的20日日期块配对重采样95%区间为 **[{boot['cagr_difference_ci_low']*100:+.2f}, {boot['cagr_difference_ci_high']*100:+.2f}]个百分点**，仍跨过0，未满足‘正年化差、区间下界>0、超过半数ETF改善’的联合标准。新版年化仍低于仅MA10和实际全期买入持有的同期对照。",
        "\n新规则平均持有约21.12个行情日，旧版约6.74日。延后卖出允许部分反弹继续持有，也允许下跌继续暴露；持仓时间和回撤同时上升。整套策略的退出不同，会改变后续是否仍持仓，因此即使买入条件相同，全部入场日期也不一定一一对应。",
        "\n## 用户确认的具体口径",
        "\n用户原规则：\n\n> 1. 10日线之下不买入。\n> 2. 从30以下到30以上并且站上10日线是买入。\n> 3. 跌破10线＋MACD死叉，或者从70以上跌到70以下＋MACD死叉卖出。\n\n随后确认：**状态确认：价格已在10日线下或指标已下穿70，此后MACD死叉时卖出。**",
        "\n本轮量化为：",
        "\n```text\n买入 = 空仓\n       且 前日V < 30 ≤ 当日V\n       且 当日复权收盘价 > 当日MA10\n\n卖出 = 持仓\n       且 当天MACD新发生死叉\n       且 [当日复权收盘价 < 当日MA10\n           或（本轮持仓曾有V ≥ 70，且当日V < 70）]\n```",
        "\n- 买入所需的指标上穿30必须在信号当天发生；价格当天已在MA10之上即可，不额外要求价格也恰好当天上穿均线。不等待后来的MA10确认；MACD不作为买入过滤。",
        "- ‘状态确认’表示破线或下穿70可以早于MACD死叉。死叉当天仍须满足相应价格/指标状态；如果价格已回到MA10上方，价格分支不触发；如果指标又回到70及以上，高位分支暂不触发。",
        "- 高位标记只统计本次买入成交后的持仓收盘（包括买入日），买卖成交时重置。买入前曾在70以上，不会被借来满足本次卖出条件。",
        "- MACD(12,26,9)：`DIF=EMA12(C)-EMA26(C)`；`DEA=EMA9(DIF)`。EMA采用递推`alpha=2/(N+1)`，从每只ETF第一条可用收盘初始化；DEA从首个DIF=0初始化，利用分段前全部历史预热。",
        "- 死叉定义为`前日DIF≥DEA，且当日DIF<DEA`。等于不算当天死叉；已经处于DIF<DEA的空头状态，也不算新死叉。若持仓在空头状态中跌破均线，仍须等后续新的死叉事件，规则没有另设止损。",
        "- 收盘等于MA10时不买入、不触发价格卖出分支；V等于30算回升，V等于70算高位，卖出高位分支要求当前严格低于70。",
        "- 均用收盘确认，下一可用ETF行情行开盘执行。‘线下不买’约束信号日收盘状态；本轮没有增加次日开盘跳空时撤单的额外规则。无加仓、无做空。",
        "\n## 各ETF主时段结果（10bp）",
        "\n" + table(["代码/类别", "新版净年化", "相同买入旧版净年化", "年化变化/百分点", "新版最大回撤", "旧版最大回撤", "新版买入次数"],
            [[f"{c} {cell(c, 'MACD_STATE')['label']}", pct(cell(c, "MACD_STATE")["cagr"]), pct(cell(c, "OLD_SAME")["cagr"]),
              f"{(float(cell(c, 'MACD_STATE')['cagr'])-float(cell(c, 'OLD_SAME')['cagr']))*100:+.3f}",
              pct(cell(c, "MACD_STATE")["max_drawdown"]), pct(cell(c, "OLD_SAME")["max_drawdown"]),
              cell(c, "MACD_STATE")["entries"]] for c in codes]),
        "\n收益改善最多的历史样本是科创50、纳指100；创业板和沪深300相对同买入旧版没有改善。黄金的改善很小，四舍五入到两位百分数时两版年化都显示为-0.44%。不能据此事后挑选ETF并称为独立验证。组合回撤不是单只ETF风险，例如新版半导体ETF的最大收盘净值回撤约42.59%。",
        "\n" + table(["规则", "自然卖出", "期末估值退出", "自然完成净胜率", "平均持有行情日", "平均资金暴露"],
            [[NAMES[s], agg(s)["natural_exits"], agg(s)["forced_exits"], pct(agg(s)["natural_win_rate"]),
              f"{float(agg(s)['mean_holding_sessions']):.2f}", pct(agg(s)["capital_exposure"])] for s in STRATEGIES]),
        f"\n新版{price+top+both}次自然退出全部有当天MACD死叉：仅价格分支{price}次，仅高位分支{top}次，两个分支同时成立{both}次。高位分支单独触发次数较少，所以不能把整体收益变化都归因于‘70止盈’；本轮也没有再试删分支来挑更好的结果。",
        "\n## 对照差值与费用敏感性",
        "\n" + table(["新版相对", "净年化差/百分点", "改善ETF数", "配对块重采样95%区间/百分点", "口径"],
            [[NAMES[c["comparator"]], f"{c['cagr_difference']*100:+.2f}", f"{c['positive_etfs']}/9",
              f"[{c['bootstrap']['cagr_difference_ci_low']*100:+.2f}, {c['bootstrap']['cagr_difference_ci_high']*100:+.2f}]",
              "预设主要比较" if c["primary"] else "次要描述"] for c in meta["comparisons"]]),
        "\n" + table(["往返费用", *[NAMES[s] for s in STRATEGIES]],
            [[f"{cost}bp", *[pct(agg(s, cost)["cagr"]) for s in STRATEGIES]] for cost in (0, 10, 30)]),
        "\n表内均为净年化。即使0费用，新版在本段的年化仍低于仅MA10和持有；30bp高费用场景下，新版超过仅MA10，因为后者交易次数多。所有费用情形均保留，不能用其中表现最好的口径替换10bp主结果。",
        "\n## 各年组合净收益（10bp）",
        "\n" + table(["年份", *[NAMES[s] for s in STRATEGIES]],
            [[year+("（截至11-10）" if year == "2026" else ""),
              *[pct(next(r for r in yearly if r["year"] == year and r["strategy"] == s)["net_return"]) for s in STRATEGIES]]
             for year in sorted({r["year"] for r in yearly})]),
        "\n## 账本、数据与限制",
        "\n复用原已审查的9只ETF与冻结输入，截止2026-11-10；不使用11月13日盘中快照。510500原有604处复权核对不符，继续排除，没有更换样本。主组合9账户等初始资金、之后不跨账户再平衡；都是第一天收盘开始判断、下一行情行开盘可买，从现金起步。实际买入持有对照覆盖完整时段，与之前固定10日窗口均值不同。",
        "\n信号价格是连续复权收盘`raw_close*s+u`。价格、MA10、指标和MACD用同一输入；成交和每日估值用原始OHLC，份额在拆分日前开盘调整。分红按除息日经济权益进入独立现金/应收储备，不再投入交易；买入当日不取得原持有者的除息前权益，现金不计息。费用每边取往返值的一半，买入从现金中同时扣费用、卖出从价款扣费用。",
        "\n期末剩余仓位按末日收盘估值退出并扣单边费，标记`forced_end`，不计入规则自然卖出胜率。持仓时间使用收盘持仓状态统计，期末估值退出日仍算持仓；自然开盘卖出日按现金状态。最大回撤是收盘组合净值回撤，忽略盘中更大波动；理论成交没有模拟整手、最低佣金、盘口和限价排队。",
        "\n主时段1417个汇总行情日。缺失报价159915/2021-02-08、512480/2021-03-26、513100/2022-01-13只按下一有报价的开盘成交；汇总组合净值时才前填最近估值，不合成成交价。冻结输入所有行成交量均正，本轮新规则计划器仅接受这个已验证条件。",
        "\nMACD从可用历史首行递推，588000在2021年前历史不足130行，最初MACD状态可能受初始化影响；未为该ETF事后调整起点。复权输入与独立后复权行情通过既定数据审查，但未逐次验证与同花顺App各次前复权口径完全一致。",
        "\n本轮沿用2021年作为主历史分段。此前市场经历、指标研究和现存ETF样本均已知，因此这仍是回顾验证，不能把`historical_holdout`名称理解为真正未见过的数据。重采样是把已经实现的两条组合每日对数收益按共同日期分成20日块，配对抽2000次、种子20261113，年化按原样本日历长度换算；它没有重新拼接价格生成策略，也不代表未来收益区间。次要比较未作多重比较校正；不因某个次要结果好就改变主要结论。",
        f"\n复验 **{verified['status']}**：13项边界测试通过；另一路使用Fraction重算V和均线、60位Decimal重算MACD，以独立区间搜索和闭式份额/分红账本核对{verified['metrics_checked']}组指标、{verified['trades_checked']}条交易记录、{verified['daily_account_nav_checked']}条账户日净值和{verified['aggregate_nav_checked']}条组合日净值；{verified['macd_feature_rows_checked']}行指标/MACD已核对，最大数值误差{verified['max_absolute_numeric_error']:.3g}。四个旧策略的{verified['unchanged_control_metrics_checked']}组指标与上轮归档逐字段完全一致。交易记录含费用/分段重复案例，不能当作同等数量独立样本。本轮复核由本地不同计算程序完成。",
        "\n## 文件与重跑",
        "\n- [确认规则与冻结协议](protocol.json)，[规则实现](rules.py)，[边界测试](test_rules.py)，[独立复验](verify_study.py)。",
        "- [全部逐ETF/分段/费用指标](results/metrics.csv)，[主时段组合指标](results/aggregate_metrics.csv)，[年度收益](results/yearly_cost10.csv)，[卖出分支统计](results/holding_diagnostics.csv)。",
        "- [逐笔交易](results/trades.csv.gz)，[逐日指标与MACD](results/features.csv.gz)，[账户日净值（10bp）](results/daily_nav_cost10.csv.gz)，[组合日净值（所有费用）](results/aggregate_nav.csv.gz)。",
        "- [结果与不确定性](results/summary.json)，[独立验证记录](results/independent_verification.json)，[完整性清单](bundle-manifest.json)。",
        "\n在本目录依次运行：\n\n```sh\npython3 -m unittest -v test_rules.py\npython3 run_study.py\npython3 verify_study.py\npython3 render_report.py\npython3 verify_bundle.py\n```\n\n全部使用Python标准库，离线读取冻结文件；旧公式、前两轮回测和输入数据保持可复验。"]
    for segment, label in (("development", "2021年前补充"), ("all_history", "各ETF完整历史补充")):
        selected = [m for m in metrics if m["segment"] == segment and m["cost_bps_round_trip"] == "10"]
        items = []
        for c in codes:
            values = [next(m for m in selected if m["code"] == c and m["strategy"] == s) for s in STRATEGIES]
            items.append([c, f"{values[0]['first']}～{values[0]['last']}", *[pct(m["cagr"]) for m in values]])
        lines.extend([f"\n## {label}（逐ETF净年化，10bp）", "\n" + table(["代码", "有效时段", *[NAMES[s] for s in STRATEGIES]], items),
                      "\n各ETF起点不同，不混合为同长度的组合检验；不足365自然日不年化，显示为—。"])
    (ROOT / "结果报告.md").write_text("\n".join(lines)+"\n")
    print("saved 结果报告.md")


if __name__ == "__main__":
    main()
