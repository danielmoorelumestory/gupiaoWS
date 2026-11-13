"""Full report for the sole added V<=45 buy filter, including skipped trades."""
import csv
import gzip
import io
import json

from rules import ROOT, PROTOCOL, STRATEGIES, helpers

OUT = ROOT / "results"
NAMES = {"MACD_CAP45": "新增：买入波段值≤45", "MACD_STATE": "上版：不限制45",
         "MA10_ONLY": "仅MA10", "BUY_HOLD": "买入持有"}


def read(name):
    path = OUT / name
    data = gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz" else path.read_text()
    return list(csv.DictReader(io.StringIO(data)))


def pct(value, digits=2):
    return f"{float(value)*100:.{digits}f}%" if value not in (None, "") else "—"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
                     + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def main():
    meta = json.loads((OUT / "summary.json").read_text())
    verified = json.loads((OUT / "independent_verification.json").read_text())
    metrics, aggregate, yearly, candidates = map(read, ("metrics.csv", "aggregate_metrics.csv", "yearly_cost10.csv", "entry_candidates.csv"))
    def agg(s, cost=10):
        return next(r for r in aggregate if r["strategy"] == s and r["cost_bps_round_trip"] == str(cost))
    primary = [m for m in metrics if m["segment"] == "historical_holdout" and m["cost_bps_round_trip"] == "10"]
    def cell(c, s):
        return next(m for m in primary if m["code"] == c and m["strategy"] == s)
    codes = sorted({m["code"] for m in primary})
    compare = next(c for c in meta["comparisons"] if c["primary"])
    boot = compare["bootstrap"]
    cs = [r for r in candidates if r["segment"] == "historical_holdout"]
    skipped = [t for t in read("trades.csv.gz") if t["strategy"] == "MACD_STATE"
               and t["segment"] == "historical_holdout" and t["cost_bps_round_trip"] == "10"
               and float(t["entry_signal_value"]) >45]
    helpers.save_csv(OUT / "skipped_original_trades_cost10.csv", skipped)
    shared = sum(r["unfiltered_buy_here"] == r["filtered_buy_here"] == "True" for r in cs)
    new_only = sum(r["unfiltered_buy_here"] == "False" and r["filtered_buy_here"] == "True" for r in cs)
    positive, equal = compare["positive_etfs"], sum(cell(c, "MACD_CAP45")["cagr"] == cell(c, "MACD_STATE")["cagr"] for c in codes)
    lines = ["# 波段顶底≤45买入过滤：同口径复盘",
        "\n2026-11-13归档。用户新增‘波段顶底大于45的MACD不买’，本轮仅在此前确认的交易规则上增加信号日`V≤45`条件。阈值45由用户指定，未扫描其他阈值。协议在收益计算前提交`96447dd`，实现及独立验证提交`a9ddf0f`。",
        "\n## 结果",
        "\n**本轮加45过滤后收益下降，组合最大回撤也没有改善，未显示增加这条过滤的优势。新旧版本都已保留。**",
        "\n9只ETF等初始资金、账户之间不再平衡，2021-01-04至2026-11-10，每次往返费用10bp（0.1%，买卖各0.05%）：",
        "\n" + table(["规则", "累计净收益", "净年化", "最大回撤", "平均持仓时间占比", "买入次数（9账户合计）"],
            [[NAMES[s], pct(agg(s)["total_return"]), pct(agg(s)["cagr"]), pct(agg(s)["max_drawdown"]),
              pct(agg(s)["time_exposure"]), agg(s)["entries"]] for s in STRATEGIES]),
        f"\n相对未加45上限的上版，年化差为 **{compare['cagr_difference']*100:+.2f}个百分点**。{positive}/9只ETF改善、{equal}只完全相同、{9-positive-equal}只下降。预先固定20日日期块配对重采样的95%年化差区间为 **[{boot['cagr_difference_ci_low']*100:+.3f}, {boot['cagr_difference_ci_high']*100:+.3f}]个百分点**，仍跨过0；没有满足‘正差值、区间下界>0、超过半数ETF改善’的联合标准，也不据此宣称该过滤在所有未来市场中必然更差。",
        "\n## 新规则的准确含义",
        "\n```text\n买入 = 空仓\n       且 前日V < 30 ≤ 当日V ≤ 45\n       且 当日复权收盘价 > 当日MA10\n\n卖出 = 持仓\n       且 当天MACD新发生死叉\n       且 [当日复权收盘价 < 当日MA10\n           或（本轮持仓曾有V ≥ 70，且当日V < 70）]\n```",
        "\n- 45包含在允许范围内，大于45才跳过；过滤观察信号日收盘指标值。信号收盘确认，下一可用行情行开盘执行。收盘等于MA10不买入。",
        "- 原买入条件仍需当天上穿30。某次上穿30时V已>45，该信号直接跳过；后续仅回落到45以下不会补买，须重新出现上穿30且价格在MA10上方。MACD继续只用于既定卖出确认，买入没有新增金叉条件。",
        "- 该上限只限制新买入，持仓后V超过45不会迫使卖出，也不会屏蔽卖出判断。",
        "- 卖出维持用户确认的‘状态确认’：死叉当天价格仍在MA10下，或本次持仓曾到70及以上且当前仍<70。破线/回落可以早于死叉；反弹回MA10上方或70及以上时，相应状态分支暂不成立。持仓高位标记在买卖成交时重置，买入前的高位不沿用。",
        "- MACD用12、26、9，DIF为EMA12−EMA26，DEA为DIF的EMA9。死叉是`前日DIF≥DEA且当日DIF<DEA`的新事件，已经处于DIF<DEA状态不算新死叉。EMA从每只ETF第一条可用历史递推预热，无额外止损。",
        "\n## 过滤实际排除了什么",
        f"\n主时段共有{len(cs)}个‘指标上穿30且收盘在MA10上方’的候选收盘，其中{sum(r['cap_allowed']=='False' for r in cs)}个V>45；在加过滤版当时空仓的候选中，{sum(r['blocked_while_flat']=='True' for r in cs)}次被上限拦截。未过滤版实际有{len(skipped)}笔V>45入场，其中{sum(float(t['net_total_return']) > 0 for t in skipped)}笔净盈利、{sum(float(t['net_total_return']) <= 0 for t in skipped)}笔未盈利。",
        f"\n两版共有{shared}个相同买入信号；未过滤版另外买入{len(skipped)}笔，加过滤版因持仓路径变化另外买入{new_only}笔，因此合计买入次数从125变116，而不是简单删除固定收益序列。以下逐笔收益取未过滤版本原账本，含同口径费用和持仓分红；它们用于诊断，不能简单相加当成组合差额。",
        "\n" + table(["代码", "买入信号日", "信号波段值", "实际买入日", "卖出日", "原交易净收益"],
            [[t["code"], t["entry_signal_date"], f"{float(t['entry_signal_value']):.3f}", t["entry_date"], t["exit_date"], pct(t["net_total_return"])] for t in skipped]),
        "\n例如，过滤跳过了军工2025-11-25入场的原交易（净收益约23.55%），以及纳指2025-04-11和2026-04-02入场的两笔原交易（约14.83%、19.37%）。这说明V>45的信号中也包含较强的反弹，不能先验地把它们都视为应排除的交易。此处是看过结果后的解释，不作为继续挑阈值的验证依据。",
        "\n## 逐ETF结果（主时段，10bp）",
        "\n" + table(["代码/类别", "加过滤净年化", "未过滤净年化", "年化差/百分点", "加过滤最大回撤", "未过滤最大回撤", "买入次数 新/旧"],
            [[f"{c} {cell(c, 'MACD_CAP45')['label']}", pct(cell(c, "MACD_CAP45")["cagr"]), pct(cell(c, "MACD_STATE")["cagr"]),
              f"{(float(cell(c, 'MACD_CAP45')['cagr'])-float(cell(c, 'MACD_STATE')['cagr']))*100:+.3f}",
              pct(cell(c, "MACD_CAP45")["max_drawdown"]), pct(cell(c, "MACD_STATE")["max_drawdown"]),
              f"{cell(c, 'MACD_CAP45')['entries']}/{cell(c, 'MACD_STATE')['entries']}"] for c in codes]),
        "\n改善的历史样本是红利、国债、黄金；沪深300和科创50完全相同，其他4只下降。不按本轮表现事后选出适用ETF。表首的组合回撤反映9账户分散后的资金曲线，不能代表单只ETF最大风险。",
        "\n## 成本与年度表现",
        "\n" + table(["往返费用", *[NAMES[s] for s in STRATEGIES]],
            [[f"{cost}bp", *[pct(agg(s, cost)["cagr"]) for s in STRATEGIES]] for cost in (0, 10, 30)]),
        "\n上表为净年化。0、10、30bp下，加45过滤均低于未过滤版，减少交易带来的费用节省没有抵消本轮收益差距。没有按费用或ETF结果修改45。",
        "\n" + table(["年份", *[NAMES[s] for s in STRATEGIES]],
            [[year+("（截至11-10）" if year == "2026" else ""),
              *[pct(next(r for r in yearly if r["year"] == year and r["strategy"] == s)["net_return"]) for s in STRATEGIES]]
             for year in sorted({r["year"] for r in yearly})]),
        "\n## 输入、账本与检验限制",
        "\n继续使用同一9只ETF、同一审查通过的原始OHLC和分红/份额因子，截止2026-11-10。510500仍因604处复权核对不符被排除，未替换样本。指标原13周期滚动SUM公式不变；指标、MA10和MACD统一使用连续复权收盘`raw_close*s+u`，成交和估值使用原始价格并独立处理份额及分红。",
        "\n每个账户起始交易现金1，现金零利息，分红/应收进入独立储备且不再投入交易。拆分在开盘前调整原持有份额，新买入者不领取买入当日除息前权益。期末持仓按末日收盘统一估值退出、扣单边费并标为forced_end，不计入自然卖出胜率。最大回撤是收盘净值口径，理论日线成交不模拟盘口、整手、最低费用或排队限制。",
        "\n主时段缺失报价仍为159915/2021-02-08、512480/2021-03-26、513100/2022-01-13：用下一真实行情行开盘执行，组合汇总才前填估值，不合成成交价。冻结输入均为正成交量；MACD从可用历史首行递推，588000在2021年前历史较短，初始状态可能受预热长度影响；未为其调整开始日期。与同花顺App各次前复权设置并未逐次完全核实。",
        "\n45由用户在看过前几轮结果后提出，本轮再次使用相同历史，因此属于探索性规则修订，不是新的未见样本检验。所谓historical_holdout是沿用的日期分段名称，不能消除已知市场和当前存续ETF样本的选择影响。配对重采样仍为已实现日对数收益的20日共同日期块、2000次、种子20261113，不重新拼接价格生成信号，也不是未来收益预测。",
        f"\n独立复核 **{verified['status']}**：8项边界测试通过；Fraction重算V和MA10、60位Decimal重算MACD，独立区间搜索和闭式分红/份额账本核对{verified['metrics_checked']}组指标、{verified['trades_checked']}条交易记录、{verified['daily_account_nav_checked']}条账户日净值、{verified['aggregate_nav_checked']}条组合日净值及{verified['entry_candidates_checked']}条分段候选信号，最大误差{verified['max_absolute_numeric_error']:.3g}。三个未修改对照的{verified['unchanged_control_metrics_checked']}组指标逐字段与上一版完全一致。重复费用/分段记录不视为独立样本数。",
        "\n## 文件与离线重跑",
        "\n- [固定协议](protocol.json)，[唯一新增买入过滤](rules.py)，[边界测试](test_rules.py)，[独立验证](verify_study.py)。",
        "- [逐ETF/分段/费用指标](results/metrics.csv)，[组合指标](results/aggregate_metrics.csv)，[年度收益](results/yearly_cost10.csv)，[买入候选与过滤记录](results/entry_candidates.csv)，[被跳过的原交易](results/skipped_original_trades_cost10.csv)。",
        "- [逐笔交易](results/trades.csv.gz)，[账户日净值（10bp）](results/daily_nav_cost10.csv.gz)，[组合日净值](results/aggregate_nav.csv.gz)，[指标与MACD](results/features.csv.gz)。",
        "- [统计摘要](results/summary.json)，[复核记录](results/independent_verification.json)，[完整性清单](bundle-manifest.json)。",
        "\n在本目录依次执行：\n\n```sh\npython3 -m unittest -v test_rules.py\npython3 run_study.py\npython3 verify_study.py\npython3 render_report.py\npython3 verify_bundle.py\n```\n\n只使用Python标准库、冻结输入与前版代码，不联网、不修改历史研究。"]
    for segment, label in (("development", "2021年前补充"), ("all_history", "各ETF完整历史补充")):
        selected = [m for m in metrics if m["segment"] == segment and m["cost_bps_round_trip"] == "10"]
        rows = []
        for c in codes:
            values = [next(m for m in selected if m["code"] == c and m["strategy"] == s) for s in STRATEGIES]
            rows.append([c, f"{values[0]['first']}～{values[0]['last']}", *[pct(v["cagr"]) for v in values]])
        lines.extend([f"\n## {label}（逐ETF净年化，10bp）", "\n"+table(["代码", "有效时段", *[NAMES[s] for s in STRATEGIES]], rows),
                      "\n各ETF历史长度不同，不混合为共同长度组合；不足365自然日不年化，显示为—。"])
    (ROOT / "结果报告.md").write_text("\n".join(lines)+"\n")
    print("saved 结果报告.md and skipped_original_trades_cost10.csv")


if __name__ == "__main__":
    main()
