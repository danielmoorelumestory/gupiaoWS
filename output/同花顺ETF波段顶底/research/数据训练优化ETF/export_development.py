"""Export controls and a pre-test review packet. Never reads test returns."""
import json

from engine import ROOT,P,load_panel,save_csv
from search import run_config,members,summarize
from grid import controls


def main():
    out=ROOT/"results";panel=load_panel();lock=json.loads((ROOT/"selection_lock.json").read_text())
    configs={s["id"]:s["config"] for s in lock["selections"]};configs.update(controls())
    metrics,stats=[],[]
    for phase in ("train","validation"):
        for key,c in configs.items():
            rows,_,_,_=run_config(panel,c,P["windows"][phase])
            metrics.extend({"phase":phase,"config":key,**r} for r in rows)
            stats.extend({"phase":phase,"config":key,"group":g,**summarize(members(rows,g))} for g in ("full","good","non_good"))
    save_csv(out/"development_locked_per_etf.csv",metrics)
    save_csv(out/"development_locked_summary.csv",stats)
    lines=["# 训练/验证完成，待Claude审查（最后历史测试尚未运行）",
           "\n协议、306组枚举、输入审查与实现均已提交。候选由训练/验证选择锁定在selection_lock.json，不能根据测试结果修改。",
           "\n61只审查通过ETF，17优秀组全部通过；酒512690、煤炭515220因hfq与因子不符，预先排除。511880货币ETF结构性排除；7只场外债基非ETF排除。",
           "\n306组按训练交易序列去重后264组。全池训练230组通过门槛；优秀组专用方案全部因交易过于集中未通过，只留描述候选，qualified=false。",
           "\n| 目标/角色 | 配置 | 验证ETF等权胜率 | 验证ETF年化中位数 | 通过门槛 |",
           "| --- | --- | --- | --- | --- |"]
    for s in lock["selections"]:
        m=s["validation_stats"]
        lines.append(f"| {s['target']}/{s['label']} | {s['id']} | {m['wr_eq']:.2%} | {m['cagr_med']:.2%} | {s['qualified']} |")
    lines.extend(["\nqualified仅表示预设样本/稳定性门槛，不表示收益为正、胜过对照或可推荐。全池折中候选在验证期年化中位数为负，最终必须如实呈现，不包装成保证盈利的方案。",
                  "\n已通过12项单元/因果/权益测试；独立Fraction/Decimal60路径核对开发段8069条交易、356688条日净值、648组账本，最大误差约3.46e-14。详见results/verification_development.json。",
                  "\n请Claude只审查协议、数据审查、实现、train/validation产物和selection_lock，复核门槛/去重/Pareto/秩选择及潜在遗漏。不要运行search.py test，不修改代码或锁定参数；最后历史测试尚不存在。审查报告需明确测试期结果未审查，由manager在修复完成后一次性执行。",
                  "\n最终任务未完成；manager下一步：处理Claude问题，必要修复不调参，随后锁定单次历史测试与独立算术复验，再出最终报告。"])
    (ROOT/"训练验证摘要_待审查.md").write_text("\n".join(lines)+"\n")
    print("pre-test review packet saved")


if __name__=="__main__":main()
