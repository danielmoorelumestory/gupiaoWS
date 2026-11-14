import sys, json, csv, math, statistics, random
from pathlib import Path
D = str(Path(__file__).resolve().parent)
import cs_common as ann
R = str(ann.R)
from cs_common import P, load_panel, summarize
from multiprocessing import Pool
if __name__ == "__main__":
    panel = load_panel()
    def vol_before(d, cut):
        c = [float(r["adjusted_close"]) for r, dt in zip(d["rows"], d["dates"]) if dt < cut]
        if len(c) < 120: return None
        lr = [math.log(c[i]/c[i-1]) for i in range(1, len(c))]
        return statistics.pstdev(lr) * math.sqrt(244)
    def label(cut):
        v = {k: vol_before(d, cut) for k, d in panel.items()}; v = {k: x for k, x in v.items() if x is not None}
        med = statistics.median(v.values()); return {k for k, x in v.items() if x >= med}, {k for k, x in v.items() if x < med}, v, med
    H1, L1, V1, m1 = label("2022-07-01"); H2, L2, V2, m2 = label("2024-07-01")
    good = {r["code"] for r in csv.DictReader(open(f"{R}/results/final_per_etf_comparison.csv")) if r["MACD优秀"] == "True"}
    names = {k: d["item"]["name"] for k, d in panel.items()}
    print(f"L1 已分组 {len(V1)} 只，波动中位 {m1*100:.1f}%，高波动 {len(H1)} 只；与 MACD优秀17 重叠 {len(H1 & good)}")
    print(f"L2 已分组 {len(V2)} 只，波动中位 {m2*100:.1f}%，高波动 {len(H2)} 只；与 MACD优秀17 重叠 {len(H2 & good)}")
    print("L1 高波动：", "、".join(f"{names[k]}{V1[k]*100:.0f}%" for k in sorted(H1, key=lambda k: -V1[k])))
    jobs = [(k, c, cs, w) for k, c in ann.grid.items() for cs in (False, True) for w in ("train", "validation")]
    with Pool(8, initializer=ann.init) as pool: res = pool.map(ann.run, jobs, chunksize=4)
    S = {}
    for key, cs, win, per in res: S.setdefault((key, cs), {})[win] = per
    def summ(per, grp): return summarize([m for k, m in per.items() if k in grp])
    rows = []
    for (key, cs), v in S.items():
        st, sv = summ(v["train"], H1), summ(v["validation"], H1)
        ok = st["annual_etfs"] >= 8 and st["natural"] >= 60 and st["cagr_med"] is not None and sv["cagr_med"] is not None
        rows.append({"key":key, "cs":cs, "cfg":ann.grid[key], "ok":ok, "tr":st["cagr_med"], "va":sv["cagr_med"], "tr_mdd":st["mdd_med"], "va_mdd":sv["mdd_med"], "n":st["natural"], "tr_etf":st["annual_etfs"]})
    ok = [r for r in rows if r["ok"]]
    for ph in ("tr", "va"):
        for i, r in enumerate(sorted(ok, key=lambda r: -r[ph]), 1): r[ph+"_rank"] = i
    ranked = sorted(ok, key=lambda r: ((r["tr_rank"]+r["va_rank"])/2, -r["tr"]))
    pick, top_train = ranked[0], max(ok, key=lambda r: r["tr"])
    def nm(r): c = r["cfg"]; return f'{c["entry"]}/{c["exit"]} n={c["n"]} lo={c["lo"]} hi={c["hi"]} cap={c["cap"]} macd={c["macd"]} {"尾盘卖" if r["cs"] else "次开卖"}'
    base = {cs: next(r for r in rows if r["key"]==ann.MACD_KEY and r["cs"]==cs) for cs in (False, True)}
    # 买入持有
    ann.init(); hold = {w: ann.run(("HOLD", ann.HOLD, False, w))[3] for w in ("train", "validation")}
    print(f"\n合格 {len(ok)}/{len(rows)}，高波动组训练/验证名次 Spearman {statistics.correlation([r['tr_rank'] for r in ok],[r['va_rank'] for r in ok]):.3f}")
    print(f"高波动组训练期有年化统计的 ETF：纯MACD {base[True]['tr_etf']} 只")
    for cs, r in base.items(): print(f"纯MACD {'尾盘卖' if cs else '次开卖'}：训练 {r['tr']*100:.2f}%(#{r['tr_rank']}) 验证 {r['va']*100:.2f}%(#{r['va_rank']}) 回撤 {r['tr_mdd']*100:.1f}%/{r['va_mdd']*100:.1f}%")
    for w in ("train", "validation"):
        s = summ(hold[w], H1); print(f"买入持有 {w}: 年化 {s['cagr_med']*100:.2f}% 回撤 {s['mdd_med']*100:.1f}%")
    print("\n名次均值前 12：")
    for r in ranked[:12]: print(f"  训练 {r['tr']*100:6.2f}%(#{r['tr_rank']}) 验证 {r['va']*100:6.2f}%(#{r['va_rank']}) 回撤 {r['tr_mdd']*100:.1f}%/{r['va_mdd']*100:.1f}%  {nm(r)}")
    print("仅训练第一：", nm(top_train), f"训练 {top_train['tr']*100:.2f}% 验证 {top_train['va']*100:.2f}%(#{top_train['va_rank']})")
    b = base[True]; strict = [r for r in ok if r["tr"] > b["tr"]+1e-9 and r["va"] > b["va"]+1e-9]
    print("两期都严格胜过纯MACD尾盘卖：", len(strict))
    for r in sorted(strict, key=lambda r: -(r["tr"]+r["va"]))[:8]: print(f"   训练 {r['tr']*100:.2f}% 验证 {r['va']*100:.2f}%  {nm(r)}")
    hs = summ(hold["train"], H1)["cagr_med"], summ(hold["validation"], H1)["cagr_med"]
    succ = pick["tr"] >= b["tr"] and pick["va"] >= b["va"] and pick["tr"] >= hs[0] and pick["va"] >= hs[1]
    print("选定：", nm(pick), " 预设成功标准：", "达到" if succ else "未达到")
    # 纯 MACD 尾盘卖 高 vs 低波动
    print("\n纯MACD尾盘卖 高/低波动组（L1）年化中位：")
    for w in ("train", "validation"):
        per = S[(b["key"], True)][w]; print(f"  {w}: 高 {summ(per,H1)['cagr_med']*100:.2f}%  低 {summ(per,L1)['cagr_med']*100:.2f}%  | 买入持有 高 {summ(hold[w],H1)['cagr_med']*100:.2f}% 低 {summ(hold[w],L1)['cagr_med']*100:.2f}%")
    # 测试复核（L2 高波动组）
    cands = {"选定": (pick["cfg"], pick["cs"]), "仅训练第一": (top_train["cfg"], top_train["cs"]), "纯MACD·尾盘卖": (b["cfg"], True), "买入持有": (ann.HOLD, False)}
    for w in [P["windows"]["test"]] + P["test_subperiods"]:
        print(f"\n## {w[0]}～{w[1]}（已见数据复核，L2 分组）")
        out = {k: ann.run((k, c, cs, tuple(w)))[3] for k, (c, cs) in cands.items()}
        for gname, grp in (("高波动", H2), ("低波动", L2)):
            for k, per in out.items():
                rs = [m for c_, m in per.items() if c_ in grp]; s = summarize(rs)
                cg = "—" if s["cagr_med"] is None else f"{s['cagr_med']*100:.2f}%"
                print(f"  {gname} {k}: 年化中位 {cg} 累计中位 {statistics.median(m['total_return'] for m in rs)*100:.2f}% 回撤中位 {s['mdd_med']*100:.1f}%")
        a_, b_ = out["选定"], out["纯MACD·尾盘卖"]; codes = [c for c in a_ if c in H2 and a_[c]["cagr"] is not None and b_[c]["cagr"] is not None]
        if codes:
            rnd = random.Random(20261113); diffs = sorted(statistics.median(a_[c]["cagr"] for c in s_) - statistics.median(b_[c]["cagr"] for c in s_) for s_ in ([rnd.choice(codes) for _ in codes] for _ in range(1000)))
            print(f"  高波动 选定−纯MACD尾盘卖 年化中位差 95%[{diffs[25]*100:+.2f},{diffs[974]*100:+.2f}]pt，逐只胜过 {sum(a_[c]['cagr']>b_[c]['cagr'] for c in codes)}/{len(codes)}")
    json.dump({"H1":sorted(H1),"H2":sorted(H2),"pick":pick,"rows":rows}, open(f"{D}/高波动_selection.json","w"), ensure_ascii=False, indent=1, default=str)
