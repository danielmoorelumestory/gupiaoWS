"""Final report: locked roles remain fixed; no selection from test results."""
import csv
import gzip
import io
import json
import statistics

from engine import ROOT,P,save_csv

OUT=ROOT/"results"
LABELS={"e6ecc034065e":"A：预锁定折中候选","825cd1230879":"B：预锁定年化优先候选",
        "d94a863f367d":"优秀组描述项（门槛未过）","b744c5f64edc":"优秀组年化描述项（门槛未过）",
        "HOLD":"买入持有","MA10":"仅MA10","MACD":"纯MACD12/26/9","USER":"原混合规则（未加45过滤）"}
MAIN=("e6ecc034065e","825cd1230879","USER","MACD","MA10","HOLD")


def read(name):
    path=OUT/name;body=gzip.decompress(path.read_bytes()).decode() if path.suffix==".gz" else path.read_text()
    return list(csv.DictReader(io.StringIO(body)))


def pct(x):return f"{float(x)*100:.2f}%" if x not in (None,"") else "—"


def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join("---" for _ in headers)+" |"]
                     +["| "+" | ".join(map(str,r))+" |" for r in rows])


def main():
    summary=read("test_summary.csv");per=read("test_per_etf.csv.gz");dev=read("development_locked_summary.csv");devper=read("development_locked_per_etf.csv")
    lock=json.loads((ROOT/"selection_lock.json").read_text());checks=json.loads((OUT/"verification_test.json").read_text())
    comparisons=json.loads((OUT/"test_comparisons.json").read_text())
    def cell(key,group="full",cost=20,phase="test"):
        return next(r for r in summary if r["config"]==key and r["group"]==group and r["cost"]==str(cost) and r["phase"]==phase)
    def sample(key,group="full",phase="test",cost=20):
        return [r for r in per if r["config"]==key and r["phase"]==phase and r["cost"]==str(cost) and (group=="full" or r["good"]=="True")]
    holding=[]
    for phase in ("validation","test"):
        source=devper if phase=="validation" else per
        for group in ("full","good"):
            rows=[r for r in source if r["config"]=="HOLD" and r["phase"]==phase and (phase!="test" or r["cost"]=="20") and (group=="full" or r["good"]=="True")]
            anns=[float(r["cagr"]) for r in rows if r["cagr"]]
            holding.append({"phase":phase,"group":group,"etfs":len(rows),"annual_etfs":len(anns),
                            "total_return_median":statistics.median(float(r["total_return"]) for r in rows),"cagr_median":statistics.median(anns)})
    save_csv(OUT/"holding_comparison.csv",holding)
    subrows=[]
    for phase in ("test_part1","test_part2"):
        for group in ("full","good"):
            for key in MAIN:
                rows=sample(key,group,phase)
                if rows:subrows.append({"phase":phase,"group":group,"config":key,"etfs":len(rows),
                                       "median_total_return":statistics.median(float(r["total_return"]) for r in rows)})
    save_csv(OUT/"subperiod_total_returns.csv",subrows)
    codes=sorted({r["code"] for r in sample("HOLD")})
    group_lookup={r["code"]:r["good"] for r in sample("HOLD")}
    per_rows=[]
    for code in codes:
        row={"code":code,"MACD优秀":group_lookup[code]}
        for key in MAIN:
            m=next(r for r in sample(key) if r["code"]==code)
            for field in ("cagr","wr","total_return","mdd","natural"):
                row[f"{key}_{field}"]=m[field]
        per_rows.append(row)
    save_csv(OUT/"final_per_etf_comparison.csv",per_rows)
    outcome={"status":"no_joint_win_rate_and_annual_advantage_over_MACD_supported",
             "primary_compromise":next(s for s in lock["selections"] if s["target"]=="full" and s["label"]=="compromise"),
             "prelocked_annual_candidate":next(s for s in lock["selections"] if s["target"]=="full" and s["label"]=="annual_leader"),
             "roles_not_changed_using_test":True,"good_specialist_promoted":False,
             "headline":"B raises observed win rate and median annual return slightly versus USER, but annual CI crosses0; A/B annual returns below pureMACD and HOLD",
             "parameters_are_research_candidates_not_official_indicator_changes":True}
    (ROOT/"策略交付.json").write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+"\n")
    lines=["# MA10 / MACD / 波段顶底：多ETF训练与最终历史测试",
        "\n**训练、验证、Claude审查、测试前修复、最后历史测试与独立复算已完成。没有找到同时可靠提高胜率和年化、且跑赢纯MACD的通用方案。** 原公式和旧研究保持独立，未修改网站或云端记录。",
        "\n## 先回答买入持有收益",
        "\n下表是各ETF收益的中位数，非单只512100、非等额组合净值收益。费用均为往返0.2%（单边0.1%），分红权益另计且不再投入，期末估值退出扣费。",
        "\n"+table(["阶段","样本","ETF数 / 年化支持数","累计收益中位数","年化收益中位数"],
            [["验证2022-07～2024-06" if r["phase"]=="validation" else "最后测试2024-07～2026-11-10",
              "全池" if r["group"]=="full" else "MACD优秀组",f"{r['etfs']} / {r['annual_etfs']}",pct(r["total_return_median"]),pct(r["cagr_median"])] for r in holding]),
        "\n之前给出的−14.18%是验证期年化中位数；最后测试期是+13.93%，两者没有矛盾。上市较晚ETF的起点不同，累计收益样本与年化支持样本也略有不同，不能把累计中位数直接代入统一年数反推年化。",
        "\n## 最后历史测试：全池主结果",
        "\n窗口2024-07-01至2026-11-10，初始冻结61只主样本，参数在看测试收益前已锁定。自然退出≥3笔才进入ETF等权胜率；年化要求≥244行情行且≥365自然日。",
        "\n"+table(["规则","ETF等权净胜率","ETF年化中位数","ETF累计收益中位数","胜率支持ETF数","自然退出笔数"],
            [[LABELS[k],pct(cell(k)["wr_eq"]),pct(cell(k)["cagr_med"]),pct(statistics.median(float(r["total_return"]) for r in sample(k))),
              f"{cell(k)['wr_supported_etfs']}/{cell(k)['etfs']}",cell(k)["natural"]] for k in MAIN]),
        "\nA相对纯MACD，观察胜率提高约7.19个百分点，年化中位数下降约6.79个百分点。B相对纯MACD，胜率提高约13.67个百分点，年化中位数下降约5.74个百分点。提高胜率伴随持仓参与和收益的取舍，不能把胜率提高等同于收益提高。",
        "\nB相对原混合规则，观察胜率提高约4.18个百分点，年化中位数提高约0.24个百分点；但年化差的ETF聚类bootstrap95%区间为[-2.65,+3.26]个百分点，胜率配对差区间也跨0，尚不能认定稳定改善。B是验证期预先锁定的年化优先候选，测试后没有把它替换为原折中A。",
        "\n## 可复现的两套参数",
        "\n**A，预锁定折中候选**：MA10；波段周期9、低位20；V从20下方回到20及以上后5个交易行内，首次满足价格>MA10且V仍≥20时买入，跌回20下方则取消等待；MACD12/26/9当天新死叉卖出。买卖均收盘确认、下一个真实报价行开盘成交。该候选不设置70卖出分支。",
        "\n**B，预锁定年化优先候选**：MA10；波段周期9、低位30；当天V上穿30且价格>MA10买入；MACD16/35/9当天新死叉，并且[价格<MA10，或本次持仓曾V≥70且当前V<70]时卖出。V下穿70与MACD死叉可以不在同日，但死叉当日仍须满足对应状态。",
        "\n价格等于MA10时不触发买入或价格分支退出；波段上穿按前值<阈值≤当前值，MACD新死叉按前日DIF≥DEA、当日DIF<DEA。已有空头状态不算当天新死叉。不同参数是实验候选，不把原来核验的同花顺13周期公式改称9周期官方公式。",
        "\n## MACD优秀17只条件分组",
        "\n"+table(["规则","ETF等权净胜率","ETF年化中位数","胜率支持ETF数","自然退出笔数"],
            [[LABELS[k],pct(cell(k,"good")["wr_eq"]),pct(cell(k,"good")["cagr_med"]),
              f"{cell(k,'good')['wr_supported_etfs']}/17",cell(k,"good")["natural"]] for k in MAIN]),
        "\nB相对USER，观察胜率约+10.73个百分点、年化中位数约+0.78个百分点；年化差95%区间[-3.72,+14.70]个百分点跨0。它仍低于纯MACD的组内12.96%年化中位数。当前优秀组来自截至2026-11-10的全历史筛选，包含测试期信息，以上只是条件性分组结果，不能包装成真正独立前向验证。",
        "\n优秀组专用搜索未产出可晋级方案，主要原因是原15%交易集中度门槛不适合组内历史长度差异：训练期264组最小集中度15.8%，结构上都过不了。此次保留门槛并披露设计限制，没有事后放宽。描述项中62.5%胜率只由4只ETF支持，不能代表17只通用，也不作为推荐方案。下一轮若修正集中度定义，须另建协议和未使用的未来数据。",
        "\n## 年化差与胜率差的不确定性",
        "\n按ETF聚类重抽样1000次，种子20261113；同一ETF候选与对照配对。年化区间对应两组ETF年化中位数的差；胜率区间对应两者均有≥3笔自然退出的ETF上的平均配对差，支持集合可能与各自WR_eq不同。",
        "\n"+table(["候选","对照","组","年化差95%区间/百分点","配对胜率差95%区间/百分点","胜率配对ETF数"],
            [[LABELS[r["config"]],LABELS[r["baseline"]],r["group"],
              f"[{r['cagr_med_difference_ci'][0]*100:+.2f},{r['cagr_med_difference_ci'][1]*100:+.2f}]",
              f"[{r['paired_wr_mean_difference_ci'][0]*100:+.2f},{r['paired_wr_mean_difference_ci'][1]*100:+.2f}]",r["paired_wr_etfs"]]
             for r in comparisons if r["config"] in MAIN[:2] and r["baseline"] in ("MACD","USER") and r["group"] in ("full","good")]),
        "\n## 成本与子期稳定性",
        "\n下表为全池ETF净年化中位数，20bp为预设主口径，其余仅作敏感性，未按结果选成本。",
        "\n"+table(["往返费用",*[LABELS[k] for k in MAIN]],[[f"{cost}bp",*[pct(cell(k,cost=cost)["cagr_med"]) for k in MAIN]] for cost in (0,10,20,40)]),
        "\n子期1只有364个首末日历日。按Claude测试前审查修订，子期统一报告**累计收益中位数**，不强行年化；两子期都独立从现金开始，不是整段净值的机械拆分。",
        "\n"+table(["子期/组",*[LABELS[k] for k in MAIN]],
            [[f"{'2024-07～2025-06' if phase=='test_part1' else '2025-07～2026-11-10'} / {group}",
              *[pct(next(r for r in subrows if r['phase']==phase and r['group']==group and r['config']==k)['median_total_return']) for k in MAIN]]
             for phase in ("test_part1","test_part2") for group in ("full","good")]),
        "\n## 训练与选择过程",
        "\n训练2013-07～2022-06；验证2022-07～2024-06；最后历史测试2024-07～2026-11-10。每只ETF先排除上市后120行预热，每窗口至少120行情行。新上市、没有训练窗口的标的只检验冻结参数迁移，不为其单独拟合。",
        "\n只在MA10固定、MACD8/17/9、12/26/9、16/35/9，以及波段9/13/21、低位20/30/40、高位70/80和三类入场/四类退出逻辑内搜索。参数仅在被逻辑使用时出现，规范网格306组，训练交易序列去重剩264。训练先做样本量、覆盖、自然退出比例、集中度、回撤门槛，然后胜率与年化Pareto及等权秩筛选；验证期只比较预先入围项。全池锁定A和B，最高合格胜率角色与A相同；优秀组2个不同描述项没有晋级。",
        "\n"+table(["阶段/方案","全池ETF等权胜率","全池ETF年化中位数"],
            [[f"{phase} / {LABELS[k]}",pct(next(r for r in dev if r['phase']==phase and r['group']=='full' and r['config']==k)['wr_eq']),
              pct(next(r for r in dev if r['phase']==phase and r['group']=='full' and r['config']==k)['cagr_med'])]
             for phase in ("train","validation") for k in ("e6ecc034065e","825cd1230879","MACD","USER","HOLD")]),
        "\n这些是回顾性的历史隔离测试。市场经历和当前存续ETF名单已知，优秀组标签还直接使用全历史；不声称样本外前向证明，也不声称306组之外的全局最优。",
        "\n## 数据与Claude发现的修复",
        "\n名单来自[用户指定ETF复盘页](https://businessweb-c0u.pages.dev/note/lab/etf-review/)：64只ETF；511880货币ETF结构性排除；页面7只场外债基不套ETF开盘撮合。63只非货币ETF最初61通过。Claude查出本方误把Sina现金因子u当作原始单位累计现金：正确转换为K=ΣΔu×当时份额因子s，再用raw_close×s+K作为信号价格。",
        "\n修正后酒512690、煤炭515220都通过hfq核对；61只主池86261行数值完全不变。为保护已锁定的选择，它们没有被重新加入训练或主测试，只用冻结参数作补充迁移，结果见supplemental_corrected_etfs.csv。不能再称其原隔离是行情源有误。prepare_data.py已补齐原始快照生成和防覆盖保护，原审查档案保持原字节。",
        "\n19只缓存有hfq可对照，61只主池内实际17只有；并非最初文档所称22。vendor hfq与Sina可能同源，分红公告第二来源未独立核验。因子小数舍入约2.5e-5；没有volume，只把已有OHLC行视作可执行报价，无法识别零成交、涨跌停排队和实际滑点。",
        "\n账本以原始开盘/收盘成交估值，拆分开盘前调整份额；除息现金权益进入不再投资的储备，现金零利息。价格等号按精确计算，EMA用递推初始化；末日统一估值退出扣费并标forced_end，不计自然交易胜率。回撤为收盘净值回撤。没有盘口、最小整手和最低佣金模型。",
        f"\n验证证据：14项单元/因果/权益测试通过。Claude独立重写选参流程与6个角色锁定项一致，独立状态机648组合、8069笔交易0差异。另一路Fraction/Decimal60闭式账本的最终复算 **{checks['status']}**：{checks['metrics']}组指标、{checks['trades']}笔交易、{checks['daily_nav']}条日净值，最大误差{checks['max_numeric_error']:.3g}。两个补充ETF亦逐日核对通过。Claude没有审查测试收益，测试期由本地独立程序复算；模型角色和参数未根据测试结果更换。",
        "\n## 交付与复算",
        "\n- [策略参数交付JSON](策略交付.json)、[测试前参数锁定](selection_lock.json)、[原协议](protocol.json)、[实施细则](implementation_choices.json)、[测试前修复记录](pretest_corrections.json)。",
        "- [逐ETF最终对照](results/final_per_etf_comparison.csv)、[买入持有两阶段收益](results/holding_comparison.csv)、[最终组别统计](results/test_summary.csv)、[差值区间](results/test_comparisons.json)、[子期累计收益](results/subperiod_total_returns.csv)。",
        "- [原始最终逐笔交易](results/test_trades.csv.gz)、[日净值](results/test_nav.csv.gz)、[全部训练统计](results/train_summary.csv)、[验证统计](results/validation_summary.csv)、[补充ETF](results/supplemental_corrected_etfs.csv)。",
        "- [Claude协议审查](review/claude/协议审查.md)、[Claude实现审查](review/claude/最终审查.md)、[数据修复验证](results/correction_verification.json)、[最终独立复验](results/verification_test.json)、[完整性检查](verify_bundle.py)。",
        "\n离线复核：\n\n```sh\npython3 -m unittest -v test_engine.py\npython3 verify.py inputs\npython3 verify.py development\npython3 verify.py test\npython3 verify_bundle.py\n```",
        "\n不要重跑已经完成的search.py test来重新挑参数，程序会拒绝。独立verify.py test只核对已经冻结的结果，不选择参数。训练、验证和测试产物、原始数据、修复前后输入及依赖哈希已保存。"]
    (ROOT/"结果报告.md").write_text("\n".join(lines)+"\n")
    print("final report, delivery parameters, holding and per-ETF comparisons saved")


if __name__=="__main__":main()
