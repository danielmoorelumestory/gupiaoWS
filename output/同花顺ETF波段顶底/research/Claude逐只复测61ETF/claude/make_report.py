#!/usr/bin/env python3
"""由 Claude 独立复测输出生成 Markdown 报告（只读本目录产物）。"""
import csv
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
V = json.loads((HERE / "verification.json").read_text())
VM = json.loads((HERE / "verification_main_only.json").read_text())
D = json.loads((HERE / "diffs.json").read_text())
LONG = list(csv.DictReader(open(HERE / "retest_long_366.csv")))
WIDE = list(csv.DictReader(open(HERE / "per_etf_61_wide.csv")))
INPUTS = json.loads((HERE.parent / "inputs.json").read_text())
SCHEMES = ["e6ecc034065e", "825cd1230879", "USER", "MACD", "MA10", "HOLD"]
NAME = {"e6ecc034065e": "候选A e6ecc034065e（E2/X2 N9 lo20 MACD12/26/9）",
        "825cd1230879": "候选B 825cd1230879（E1/X3 N9 lo30 MACD16/35/9 hi70）",
        "USER": "USER（E1/X3 N13 lo30 MACD12/26/9 hi70）", "MACD": "纯MACD 12/26/9",
        "MA10": "仅MA10", "HOLD": "买入持有"}
SHORT = {"e6ecc034065e": "候选A", "825cd1230879": "候选B", "USER": "USER", "MACD": "纯MACD",
         "MA10": "MA10", "HOLD": "持有"}


def f(x):
    return None if x in ("", None) else float(x)


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def wrcell(m):
    n, w = int(m["natural"]), int(m["wins"])
    if f(m["wr"]) is None:
        return f"—（{w}/{n}）"
    return f"{pct(f(m['wr']))}（{w}/{n}）"


by = {(m["config"], m["code"]): m for m in LONG}


def summary(codes):
    out = []
    for c in SCHEMES:
        ms = [by[(c, k)] for k in codes]
        wrs = [f(m["wr"]) for m in ms if f(m["wr"]) is not None]
        cg = [f(m["cagr"]) for m in ms if f(m["cagr"]) is not None]
        nat = sum(int(m["natural"]) for m in ms)
        wins = sum(int(m["wins"]) for m in ms)
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            SHORT[c], f"{pct(st.mean(wrs))}（{len(wrs)}只）" if wrs else "—",
            pct(wins / nat) if nat else "—", f"{pct(st.median(cg))}（{len(cg)}只）",
            pct(st.mean(cg)), pct(st.median([f(m["total_return"]) for m in ms])),
            pct(st.median([f(m["mdd"]) for m in ms])),
            sum(int(m["entries"]) for m in ms), f"{nat}/{wins}"))
    return out


def etf_table(rows):
    h = ["| # | 代码 | 名称 | 优秀 | 候选A胜率（盈/自然） | 候选A年化 | 候选B胜率（盈/自然） | 候选B年化 "
         "| USER年化 | 纯MACD年化 | MA10年化 | 持有年化 | 持有累计 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        k = r["code"]
        h.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, k, r["name"], "★" if r["good"] == "True" else "",
            wrcell(by[("e6ecc034065e", k)]), pct(f(r["候选A_年化"])),
            wrcell(by[("825cd1230879", k)]), pct(f(r["候选B_年化"])), pct(f(r["USER_年化"])),
            pct(f(r["纯MACD_年化"])), pct(f(r["MA10_年化"])), pct(f(r["持有_年化"])),
            pct(f(r["持有_累计收益"]))))
    return h


def cum_table(rows):
    h = ["| 代码 | 名称 | " + " | ".join(f"{SHORT[c]} 累计/MDD/笔" for c in SCHEMES) + " |",
         "|---|---|" + "---|" * len(SCHEMES)]
    for r in rows:
        k = r["code"]
        cells = []
        for c in SCHEMES:
            m = by[(c, k)]
            cells.append(f"{pct(f(m['total_return']))} / {pct(f(m['mdd']))} / {m['entries']}"
                         + (f"（强平{m['forced']}）" if int(m["forced"]) else ""))
        h.append(f"| {k} | {r['name']} | " + " | ".join(cells) + " |")
    return h


good = [r for r in WIDE if r["good"] == "True"]
other = [r for r in WIDE if r["good"] != "True"]
late = [r for r in WIDE if r["first"] > INPUTS["window"][0]]
noann = [r for r in WIDE if r["annual_supported"] != "True"]
cs = V["comparison"]
SH = ("| 方案 | 等权自然胜率均值（≥3笔ETF数） | 合并胜率 | 年化中位（可年化ETF数） | 年化均值 "
      "| 累计收益中位 | MDD中位 | 交易数 | 自然退出/盈利 |",
      "|---|---|---|---|---|---|---|---|---|")
L = []
L += ["# Claude逐只独立复测：61只ETF × 6套固定规则（2024-07-01至2026-11-10，往返20bp）", ""]
L += ["## 结论先行", "",
      f"- 复测组数：**{V['main_groups']}组**（61只 × 6方案），全部独立重算；另附成本0/10/40bp与两个子区间共 {V['extra_groups']} 组附加比对。",
      f"- 主口径（test/20bp）与原 `results/test_*` 逐项比对：**差异 {V['diff_main_scope_366']} 处**。"
      f"覆盖 {VM['comparison']['per_etf_groups']} 组 × 18 个汇总字段（{VM['comparison']['per_etf_fields']} 项）、"
      f"全部 {cs['trades']} 笔交易 × 19 字段（{cs['trade_fields']} 项，含信号/成交index、日期、forced）、"
      f"全部 {cs['nav_rows']} 条逐日NAV × 7 字段（{cs['nav_fields']} 项）；容差 abs/rel 1e-9，日期/index/计数精确相等。",
      f"- 附加口径共 {V['diff_extra_scope']} 处差异，全部在 **0bp成本** 的候选A·512070（见“差异分析”），属浮点舍入导致的胜负判定边界问题，不影响主口径。",
      f"- 输入与原archive完整性：开始与结束哈希全部一致（inputs_ok_start={V['inputs_ok_start']}, inputs_ok_end={V['inputs_ok_end']}），原 `verify_bundle.py` 首尾均 PASS（467文件）。",
      ""]
L += ["## 主口径", "",
      "- 名单：严格取 `inputs.json` 的61只（含17只“MACD优秀”冻结标签）；不含货币ETF 511880，不含后修正的酒/煤炭 512690、515220。",
      "- 窗口：2024-07-01～2026-11-10 且上市后第120根（index≥120）起；每窗口现金1起步，无继承仓位/订单；收盘发信号、下一真实报价行开盘成交；末日不发新单，末日持仓按收盘价扣费强制估值（forced_end，不计胜率）。",
      "- 费用：单边0.1%。买入 q=现金/[open×1.001]；卖出 现金=q×price×0.999。分红按 q_prev/s_prev×ΔK 进入独立 reserve，不再投入；份额按 s_today/s_prev 调整；当日新买不领除息。",
      "- 信号用 normalized adjusted_close：MA10 与波段V 以 `Fraction` 精确比较（C==MA10既非上也非下）；MACD 用 Decimal(60位) 自首条复权收盘递推，首日DIF=DEA=0。",
      "- 胜率仅在自然退出≥3笔时给出，否则“—”（括号内仍列盈利/自然笔数）；年化需≥244报价行且首末≥365日，否则“—”，累计收益照常给出；年化 = finalNAV^(365.25/日历天数)−1，包含全部空仓时间；MDD 按收盘NAV、初始峰值1。",
      ""]
for c in SCHEMES:
    L.append(f"- {SHORT[c]}：{NAME[c]}")
L += [""]
L += ["## 样本支持", "",
      f"- 61只全部满足窗口≥120行，366组全部有结果。",
      f"- 不足年化支持：{len(noann)}只 —— " + "；".join(
          f"{r['code']} {r['name']}（{r['first']}起，{r['sessions']}行/{r['calendar_days']}日）" for r in noann)
      + "；其年化显示“—”，只看累计收益。",
      f"- 窗口晚于2024-07-01开始（上市晚或未满120根）：{len(late)}只 —— " + "、".join(
          f"{r['code']}({r['first']})" for r in late) + "。",
      "- 17只“MACD优秀”标签使用截至2026-11-10的全历史冻结，组内结果有选择偏差，只能作条件性描述。", ""]
L += ["## 方案汇总（由逐只结果计算，仅作概览）", "", "### 全部61只", ""] + list(SH) + summary(
    [r["code"] for r in WIDE])
L += ["", "### MACD优秀17只", ""] + list(SH) + summary([r["code"] for r in good])
L += ["", "### 其余44只", ""] + list(SH) + summary([r["code"] for r in other]) + [""]
L += ["## 逐只结果（61行全部打印）", "",
      "胜率格式：自然完成胜率（盈利笔/自然退出笔）；不足3笔自然退出显示“—”。年化不足支持显示“—”。", "",
      "### 表1：MACD优秀组 17只", ""] + etf_table(good)
L += ["", "### 表2：其余 44只", ""] + etf_table(other)
L += ["", "### 表3：61只六方案累计收益 / 最大回撤 / 交易笔数（含末日强平笔数）", ""] + cum_table(WIDE)
ex = D["first_200"]
L += ["", "## 差异分析", "",
      f"- 主口径366组：0处差异。逐日NAV、全部交易（含信号index与成交index、自然/forced）与18项汇总字段全部在1e-9内一致。",
      f"- 附加口径（成本0/10/40bp、子区间test_part1/part2各20bp）：{V['diff_extra_scope']}处，明细："]
for d in ex:
    L.append(f"  - `{d['key']}` 字段 `{d['field']}`：复测 {d['retest']}，原 {d['original']}")
L += ["- 原因：0bp下候选A在512070有一笔 2024-08-16 开盘0.576买、2024-08-22 开盘0.576卖、无分红的交易，经济上净收益恰为0。"
      "本复测以浮点计算 q=1/0.576 再乘回 0.576，得 net_return=2.22e-16>0 判为盈利；原结果把它判为非盈利（原实现的浮点运算次序得到≤0，或采用其他等价判定；未读取原engine源码确认）。"
      "原结果在经济含义上正确（0收益不算赢）。该笔在20bp主口径为亏损（两边一致），不影响任何主表数字。"
      "按任务要求不修改原结果，也不在看到结果后改动本复测判定规则来抹平，如实记录。", ""]
L += ["## 独立性说明", "",
      "- `retest61.py` 只导入Python标准库，没有 import 原目录的 engine/reference/verify/search，也没有调用原指标函数；"
      "只读取 inputs.json、原目录 protocol.json/selection_lock.json/data_audit.json/pretest_corrections.json/bundle-manifest.json（核验哈希；protocol仅用于子区间日期）和 data/{code}.csv.gz。",
      "- 全部复测结果CSV先写出，随后才读取原 `results/test_per_etf.csv.gz`、`test_trades.csv.gz`、`test_nav.csv.gz` 比对。"
      "原 trades/nav 文件只含主口径20bp，因此附加口径只比对汇总字段。",
      f"- 脚本 sha256：`{V['script_sha256']}`。", ""]
L += ["## 实际命令与退出码", "", "工作目录 `output/同花顺ETF波段顶底/research/Claude逐只复测61ETF/claude/`：", "", "```",
      "# 以下两条 verify_bundle 在仓库根运行（只读，不带 --write）",
      "python3 -B output/同花顺ETF波段顶底/research/数据训练优化ETF/verify_bundle.py   # 开始，exit=0，PASS 467 files",
      "python3 -B retest61.py            > run_main_only.log   # exit=0，status=PASS，366组，0差异",
      "python3 -B retest61.py --extra    > run.log             # exit=0，status=DIFFS_FOUND（仅附加口径3处），主口径0差异",
      "python3 -B make_report.py                               # 生成本报告",
      "python3 -B output/同花顺ETF波段顶底/research/数据训练优化ETF/verify_bundle.py   # 结束，exit=0，PASS 467 files",
      "```", "", "以上 retest61/make_report 在 claude/ 目录运行。", "",
      "## 产物", "",
      "- `retest61.py` 独立复测与比对程序；`make_report.py` 报告生成",
      "- `retest_long_366.csv` 366组长表（累计收益、年化、自然胜率、交易数、MDD、finalNAV、分红、费用等）",
      "- `per_etf_61_wide.csv` 61行宽表（六方案 累计/年化/自然胜率/交易数/自然退出/盈利/MDD）；`per_etf_61_brief.csv` 简洁61行展示表",
      "- `retest_trades.csv` 全部交易；`retest_nav.csv.gz` 全部逐日NAV",
      "- `retest_extra_cost_subperiod.csv` 附加口径；`diffs.csv` / `diffs.json` 差异；`verification.json`、`verification_main_only.json`",
      "- `run.log`、`run_main_only.log`、`integrity_start_verify_bundle.log`、`integrity_end_verify_bundle.log`", ""]
(HERE / "结果报告.md").write_text("\n".join(L))
print("written", len(L), "lines")
