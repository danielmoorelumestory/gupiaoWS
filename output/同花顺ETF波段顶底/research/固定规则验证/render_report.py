"""完整展示预先指定的结果，不按收益挑选周期或标的。"""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parent


def read_csv(name):
    with (ROOT / "results" / name).open() as f:
        return list(csv.DictReader(f))


def percentage(value, digits=2):
    return "—" if value is None or value == "" else f"{float(value)*100:+.{digits}f}%"


def main():
    summary = json.loads((ROOT / "results/summary.json").read_text())
    audit = json.loads((ROOT / "data_audit.json").read_text())
    aggregate = read_csv("aggregate_common_all3.csv")
    primary = summary["primary_comparisons"]
    ci = summary["bootstrap"]
    interpretation = ("历史留出段满足本次预先指定的支持条件，但尚无真正未见的前向验证，不能确认优化有效。"
                      if summary["historical_support_under_prespecified_criterion"] else
                      "历史留出段未满足本次预先指定的支持条件，不能把B+宣布为有效优化或默认替换规则。")
    if summary["eligible_etfs"] < 8:
        interpretation = "计划面板未达到预先要求的至少8只，当前仅为不完整探索，不能据此判定优化有效。"
    lines = ["# ETF波段顶底：固定三规则事件研究", "",
             "研究结果，不是真实交易记录，也不是完整仓位策略的收益回测。原13周期公式未改。", "",
             "## 主结果", "", interpretation, "",
             f"预定10日持有、往返10基点成本的B+减B，按共同ETF等权：**{percentage(summary['primary_equal_weight_delta'], 3)}**（单次事件收益差，百分比数字之差为百分点）。",
             f"日期块自助法区间：**{percentage(ci['ci_low'], 3)} 至 {percentage(ci['ci_high'], 3)}**；改善方向的ETF **{summary['primary_positive_etfs']}/{summary['primary_common_etfs']}**。",
             "该区间描述历史抽样不确定性，不是未来收益或真实样本外有效性的保证。", "",
             "## 先固定的方案与输入", "",
             "- 方案在计算策略结果前写入protocol.json并提交Git：81faf38；周期13和阈值30不寻优。",
             "- A：首次跌破30；B：重返30；B+：重返30且当天连续调整价上涨。",
             "- 信号收盘确认，下一交易日开盘进，持有第5/10/20个交易日收盘出。每种规则每个持有期分别去掉持仓重叠的事件。",
             "- 2010年起按可得历史取样，2021年前为开发段，2021年起为历史留出段，统一截至2026-11-10。近期市场和588060样本已被观察过，所以不声称留出段是真正未见样本。",
             "- 往返0/10/30基点是成本情景，包含佣金、价差及滑点的假设，不是实际券商报价。净收益按初始资金扣固定往返成本。",
             "- 对照是同ETF、同分段、同持有期的无条件次日开盘至持有期末收盘毛收益均值；它是市场漂移参照，不是可直接交易的组合。净超额=事件扣费收益减该毛收益参照。",
             "- 份额和现金权益按累计因子处理，分红以除息经济权益记为现金/应收，不强制再投，不模拟实际到账日期。MAE是相对入场权益的毛最大不利波动，非峰值回撤。", "",
             f"计划面板{summary['planned_etfs']}只；通过价格/因子审查{summary['eligible_etfs']}只，以下排除记录不替换标的：", "",
             "|代码|状态|原因|", "|---|---|---|"]
    for row in summary["excluded"]:
        reason = row.get("error") or f"连续调整价与另一报价源不一致{row.get('factor_mismatch_count')}根"
        lines.append(f"|{row['code']}|{row['status']}|{reason}|")
    lines += ["", "审查规则、两个事前修正和第一次失败记录均保留。份额因子允许合法缩份下降；不按价格缺口寻找最佳事件日期。后续只改变传输源，未放宽原价格一致性阈值。", "",
              "|代码|类别|首日|末日|根数|调整价不一致根数|", "|---|---|---|---|---:|---:|"]
    for row in audit["symbols"]:
        if row["status"] == "eligible":
            lines.append(f"|{row['code']}|{row['group']}|{row['first']}|{row['last']}|{row['rows']}|{row['factor_mismatch_count']}|")
    lines += ["", "## 主口径：历史留出段、10日、往返10基点", "",
              "三规则表只用各规则都有事件的共同ETF，先在每只ETF内取均值，再对ETF等权。事件笔数不当作独立样本数。", "",
              "|规则|共同ETF|事件数|单次净收益均值|净超额均值|净胜率均值|MAE均值|", "|---|---:|---:|---:|---:|---:|---:|"]
    for r in aggregate:
        if r["segment"] == "historical_holdout" and r["horizon"] == "10" and r["cost_bps"] == "10":
            lines.append(f"|{r['rule']}|{r['common_etfs']}|{r['events']}|{percentage(r['equal_weight_mean_net'])}|{percentage(r['equal_weight_mean_net_excess'])}|{percentage(r['equal_weight_win_rate'])}|{percentage(r['equal_weight_mean_mae'])}|")
    lines += ["", "|ETF|B事件|B+事件|B净均值|B+净均值|差额|", "|---|---:|---:|---:|---:|---:|"]
    for r in primary:
        lines.append(f"|{r['code']} {r['label']}|{r['B_events']}|{r['B_plus_events']}|{percentage(r['B_mean_net'])}|{percentage(r['B_plus_mean_net'])}|{percentage(r['delta_mean_net'])}|")
    lines += ["", "## 同一批B事件中，上涨条件实际剔除了什么", "",
              "该表在已经去重的B事件中分组，避免把B+独立去重引入的新事件混入过滤解释；仅为描述性检查。", "",
              "|ETF|B事件|保留|剔除|保留毛收益均值|剔除毛收益均值|", "|---|---:|---:|---:|---:|---:|"]
    for r in read_csv("paired_filter_diagnostic.csv"):
        if r["segment"] == "historical_holdout":
            lines.append(f"|{r['code']}|{r['B_events']}|{r['kept_price_up']}|{r['excluded_nonup']}|{percentage(r['kept_mean_gross'])}|{percentage(r['excluded_mean_gross'])}|")
    lines += ["", "## 全部预定次级口径", "",
              "下表完整列出各持有期、成本和两个时间段的净超额均值，未挑选最佳参数。", "",
              "|分段|持有日|往返基点|共同ETF|A净超额|B净超额|B+净超额|", "|---|---:|---:|---:|---:|---:|---:|"]
    groups = {}
    for r in aggregate:
        groups.setdefault((r["segment"], r["horizon"], r["cost_bps"]), {})[r["rule"]] = r
    for key, rr in groups.items():
        part, horizon, cost = key
        lines.append(f"|{part}|{horizon}|{cost}|{rr['A']['common_etfs']}|{percentage(rr['A']['equal_weight_mean_net_excess'])}|{percentage(rr['B']['equal_weight_mean_net_excess'])}|{percentage(rr['B_plus']['equal_weight_mean_net_excess'])}|")
    lines += ["", "## 结论边界", "",
              "这是当前仍上市ETF的固定样本，存在存活者偏差；行业、宽基和跨境之间也可能相关。日期块重采样保留同期关联，但不保证涵盖更长市场周期的全部不确定性。",
              "只有三个规则的事件收益；没有资金分配、空仓收益、重复入场复利或年化组合绩效。每日开收盘是理论成交价，没有盘口、限价排队和最小手数模型。",
              "研究信号用现金/份额累计单位连续价，尚未逐一确认各ETF每次分红时与同花顺前复权一致。数据和口径限制不能靠更漂亮的统计值消除。",
              "不依据这批结果再调13/30或加入其他过滤。真正的新数据前向验证尚未发生。", "",
              "## 复现", "", "```sh", "python3 -m unittest -v test_study.py",
              "python3 run_study.py", "python3 render_report.py", "```", "",
              "在本目录运行，上述步骤只读取已存输入，不联网；重新取数才运行prepare_panel.py。",
              "协议、数据审查、全部结果、事件表及原始压缩响应均在本目录保存。"]
    (ROOT / "结果报告.md").write_text("\n".join(lines) + "\n")
    print(ROOT / "结果报告.md")


if __name__ == "__main__":
    main()
