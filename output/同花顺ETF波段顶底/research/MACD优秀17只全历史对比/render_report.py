"""Print the requested17-row lifetime comparison, with warmup stated explicitly."""
import csv
import json
import math
import statistics
from datetime import date

from compare import ROOT,SPEC,engine


def pct(x):return f"{float(x)*100:.2f}%" if x not in (None,"") else "—"


def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join("---" for _ in headers)+" |"]
                     +["| "+" | ".join(map(str,r))+" |" for r in rows])


def main():
    rows=list(csv.DictReader((ROOT/"results/lifetime_17_comparison.csv").open()))
    summary=json.loads((ROOT/"results/summary.json").read_text())
    checked=json.loads((ROOT/"results/verification.json").read_text())
    secondary=list(csv.DictReader((ROOT/"results/hold_after_warmup_secondary.csv").open()))
    print_table=table(["ETF代码 / 名称","行情首日","纯MACD年化","上市起持有年化","优化B年化","MACD / B自然胜率"],
        [[f"{r['code']} {r['name']}",r["first"],pct(r["MACD_cagr"]),pct(r["HOLD_cagr"]),pct(r["B_cagr"]),
          f"{pct(r['MACD_wr'])} / {pct(r['B_wr'])}"] for r in rows])
    (ROOT/"results/17只逐行打印.md").write_text(print_table+"\n")
    same_start=[]
    for r in rows:
        hold=next(x for x in secondary if x["code"]==r["code"])
        years=(date.fromisoformat(hold["last"])-date.fromisoformat(hold["first"])).days/365.25
        same_start.append({"code":r["code"],"name":r["name"],"common_start":hold["first"],"end":hold["last"],
            "HOLD_cagr":hold["cagr"],"MACD_cagr":math.expm1(math.log(1+float(r["MACD_total_return"]))/years),
            "B_cagr":math.expm1(math.log(1+float(r["B_total_return"]))/years)})
    engine.save_csv(ROOT/"results/common_after_warmup_comparison.csv",same_start)
    lines=["# MACD优秀17只：从行情首日至2026-11-13的三方案最终对比",
        "\n**本17只全历史回看中，纯MACD的ETF年化中位数最高；优化B提高了平均胜率，但没有整体超过纯MACD的年化。** 参数沿用原锁定方案，未依据本次全历史结果再选参。",
        "\n## 口径",
        "\n- 截至2026-11-13完整收盘；每只各从缓存中首个可得交易日开始计资本、计年化，日期逐只列出。该首日通常对应上市首个报价，但没有另查交易所上市公告来确认；不是统一起点组合收益。",
        "- 往返费用0.2%，买卖各0.1%。现金无利息，分红进独立储备、不再投入交易，拆分调整份额；期末收盘估值退出扣费用。",
        "- 买入持有：行情首日开盘买入。纯MACD与优化B：保留原训练定义，前120行预热，资金保持现金；第121行起可收盘发信号、下一真实报价行开盘成交。年化分母包含上市起全部预热及空仓时间。三者资金都从行情首日开始计算。",
        "- 纯MACD=12/26/9新金叉买、新死叉卖。优化B=MA10、波段9周期、低位30/高位70、MACD16/35/9；V当天上穿30且收盘>MA10买；新死叉且[收盘<MA10，或本次持仓曾V≥70且当前V<70]卖。已有空头不等于新死叉，持仓高位不继承买入前记录。",
        "- 胜率只计自然退出，排除期末估值退出；每只自然退出至少3笔才显示，完整笔数与回撤见CSV。",
        "\n## 17只逐只年化与胜率",
        "\n"+print_table,
        "\n## 汇总",
        "\n"+table(["方案","ETF年化中位数","ETF年化均值","累计收益中位数","ETF等权自然胜率","自然退出笔数"],
            [[name,pct(summary[s]["cagr_median"]),pct(summary[s]["cagr_mean"]),pct(summary[s]["total_return_median"]),
              pct(summary[s]["wr_equal"]),summary[s]["natural_trades"]] for s,name in (("MACD","纯MACD"),("HOLD","上市起买入持有"),("B","优化候选B"))]),
        f"\nB的年化胜过纯MACD为{summary['B_beats_MACD_annual_etfs']}/17只，胜过上市起买入持有为{summary['B_beats_HOLD_annual_etfs']}/17只。不同ETF历史长度不同，均值和中位数均不是实际组合年化；胜率提高也不等于年化提高。",
        "\n## 累计收益与交易笔数",
        "\n"+table(["代码 / 名称","MACD累计","持有累计","B累计","MACD自然退出","B自然退出","MACD回撤","B回撤"],
            [[f"{r['code']} {r['name']}",pct(r["MACD_total_return"]),pct(r["HOLD_total_return"]),pct(r["B_total_return"]),
              r["MACD_natural"],r["B_natural"],pct(r["MACD_mdd"]),pct(r["B_mdd"])] for r in rows]),
        "\n## 预热后同起点的敏感性对照",
        "\n用户要求的主表从上市可得首日计资本，持有首日即买入，策略先预热。为了显示起点差异的影响，下面额外把三者都从第121行开始计年化，持有在该日收盘发单、下一开盘买入；它是附加口径，不替换主结果。",
        "\n"+table(["方案","同预热后起点的ETF年化中位数"],
            [[name,pct(statistics.median(float(r[field]) for r in same_start))] for field,name in (("MACD_cagr","纯MACD"),("HOLD_cagr","持有"),("B_cagr","优化B"))]),
        "\n## 数据与验证",
        "\n每只均补齐11月11、12、13日三根日线；新旧重叠报价OHLC精确一致。重新读取Sina份额/现金因子，转换K=ΣΔu×事件时份额s，用raw_close×s+K形成指标价格；旧历史因子和调整价逐行数值一致。最近日线与Tencent hfq按原容差逐根核对，17只均通过。原冻结训练、原测试结果与61只复测目录均未被改写。",
        f"\n本次34组策略账本通过独立Fraction/Decimal60的区间搜索和闭式现金份额账本复核，核对{checked['daily_nav_checked']}条日净值，最大误差{checked['max_absolute_error']:.3g}；买入持有另由闭式与逐日份额/现金两条计算路径核对。",
        "\n此前Claude已另写程序，对61只×6套方案的最后测试期366组、5583笔交易、202032条日净值复测，20bp主口径0差异。该Claude复测截止2026-11-10；本表是随后另算的全历史、更新至11月13日，不能说Claude已经复测了新增这三天。本表由本地独立账本复核。Claude额外0bp敏感性有3个字段差异，原因是同价交易浮点2.2e-16被算作盈利，主口径不受影响，原差异报告保留。",
        "\n这是全历史回看，包含用于选参的训练、验证数据；17只名单也按MACD历史表现预先筛出，存在选择偏差。本结果不构成额外独立前向证据。理论开盘成交未模拟盘口、零量、整手与最低佣金；历史前段缓存没有volume。",
        "\n## 文件",
        "\n- [完整17行CSV](results/lifetime_17_comparison.csv)，[聊天用逐行表](results/17只逐行打印.md)，[51组长表](results/lifetime_long.csv)，[策略逐笔](results/lifetime_trades.csv.gz)。",
        "- [同预热后起点对照](results/common_after_warmup_comparison.csv)，[数据审查与请求URL](data_audit.json)，[独立验证](results/verification.json)，[固定口径](protocol.json)。",
        "- compare.py复算，render_report.py生成表格，verify_bundle.py检查归档完整性。raw/保存本次实际响应，data/保存更新后的完整17只输入。"]
    (ROOT/"结果报告.md").write_text("\n".join(lines)+"\n")
    print("saved lifetime17 report and tables")


if __name__=="__main__":main()
