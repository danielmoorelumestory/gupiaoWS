"""Three separate commands: train, select (validation), test (locked configs).

The test command cannot change candidates. Full train grid and all selection
failures are retained; no test-period parameter search exists in this program.
"""
from collections import defaultdict
import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess

from engine import ROOT,P,bounds,digest,load_panel,save_csv,simulate,summarize
from grid import controls,enumerate_grid,identifier,neighbors

OUT=ROOT/"results"


def code_hashes():
    return {name:digest(ROOT/name) for name in ("engine.py","grid.py","search.py","protocol.json","implementation_choices.json")}


def members(records,group):
    if group=="full":return records
    if group=="good":return [r for r in records if r["good"]]
    if group=="non_good":return [r for r in records if not r["good"]]
    if group=="cross_commodity":return [r for r in records if r["cross_commodity"]]
    if group=="late":return [r for r in records if r["late"]]
    raise ValueError(group)


def run_config(panel,config,window,cost=20,retain=False):
    rows,trades,nav,signature=[],[],[],hashlib.sha256()
    for code,data in panel.items():
        result=simulate(data,config,window,cost,retain)
        if result is None:continue
        item=data["item"]
        meta={"code":code,"name":item["name"],"good":"MACD优秀" in item["groups"],
              "cross_commodity":code.startswith("513") or code=="518880" or any(x in item["name"] for x in ("港股","纳指","恒生","标普","中概","中韩")),
              "late":data["dates"][0]>=P["windows"]["test"][0]}
        rows.append({**meta,**result["metric"]})
        signature.update(json.dumps([code,result["intervals"]],separators=(",", ":")).encode())
        if retain:
            trades.extend({"code":code,**t} for t in result["trades"])
            nav.extend({"code":code,**n} for n in result["nav"])
    return rows,trades,nav,signature.hexdigest()


def hard_gates(stats,hold,good_stats,phase,target):
    h=P["hard_gates"];reasons=[]
    minimum=h[f"{phase}_min_natural_trades_{'full' if target=='full' else 'good'}"]
    if stats["natural"]<minimum:reasons.append("natural_count")
    if target=="full" and good_stats["natural"]<h[f"{phase}_min_natural_trades_good"]:reasons.append("good_count")
    for key,threshold in (("trades_per_year",h["natural_trades_per_etf_year"]),("one_trade_coverage",h["one_trade_coverage"]),
                          ("wr_coverage",h["three_trade_WR_coverage"]),("natural_fraction",h["natural_exit_fraction"])):
        if stats[key]<threshold:reasons.append(key)
    if stats["max_etf_trade_share"]>h["max_single_etf_trade_share"]:reasons.append("trade_concentration")
    if stats["mdd_med"] is None or stats["mdd_med"]<hold["mdd_med"]:reasons.append("drawdown_vs_hold")
    if stats["wr_eq"] is None or stats["cagr_med"] is None:reasons.append("unsupported_objective")
    return reasons


def rank_scores(items):
    scores={k:0.0 for k in items}
    for field in ("wr_eq","cagr_med"):
        values=[items[k][field] for k in items]
        for key,s in items.items():
            x=s[field]
            rank=(sum(v<x for v in values)+(sum(v==x for v in values)-1)/2)/max(1,len(values)-1)
            scores[key]+=.5*rank
    return scores


def complexity(c):
    return sum(c[k] is not None for k in ("n","lo","hi","cap","wait"))+3*(c["macd"] is not None)


def train(panel,grid):
    per_asset,summary,stats_by_id,signatures=[],[],{},{}
    hold=run_config(panel,controls()["HOLD"],P["windows"]["train"])[0]
    for key,config in grid.items():
        rows,_,_,signature=run_config(panel,config,P["windows"]["train"])
        per_asset.extend({"config":key,**r} for r in rows)
        stats_by_id[key]={g:summarize(members(rows,g)) for g in ("full","good","non_good")}
        signatures[key]=signature
        for group,stats in stats_by_id[key].items():
            summary.append({"config":key,"group":group,**stats})
    representative={}
    unique=[]
    for key in grid:
        signature=signatures[key]
        if signature not in representative:
            representative[signature]=key;unique.append(key)
    shortlists={};gate_rows=[]
    for group in ("full","good"):
        hold_stats=summarize(members(hold,group))
        passed={};descriptive={}
        for key in unique:
            stats=stats_by_id[key][group]
            reasons=hard_gates(stats,hold_stats,stats_by_id[key]["good"],"train",group)
            gate_rows.append({"config":key,"target":group,"passed":not reasons,"reasons":";".join(reasons)})
            if stats["wr_eq"] is not None and stats["cagr_med"] is not None:
                descriptive[key]=stats
                if not reasons:passed[key]=stats
        frontier=[k for k,a in passed.items() if not any(b["wr_eq"]>=a["wr_eq"] and b["cagr_med"]>=a["cagr_med"]
                   and (b["wr_eq"]>a["wr_eq"] or b["cagr_med"]>a["cagr_med"]) for j,b in passed.items() if j!=k)]
        near={k:a for k,a in passed.items() if any(a["wr_eq"]>=passed[f]["wr_eq"]-.01 and a["cagr_med"]>=passed[f]["cagr_med"]-.01 for f in frontier)}
        fallback=not near
        pool=near or descriptive
        scores=rank_scores(pool)
        selected=sorted(pool,key=lambda k:(-scores[k],complexity(grid[k]),k))[:30]
        shortlists[group]={"configs":selected,"frontier":frontier,"fallback_training_gates_failed":fallback,
                           "train_passed":list(passed)}
    save_csv(OUT/"train_per_etf.csv.gz",per_asset)
    save_csv(OUT/"train_summary.csv",summary)
    save_csv(OUT/"train_gates.csv",gate_rows)
    state={"source_hashes":code_hashes(),"grid":grid,"training_signature_representatives":representative,
           "canonical_count":len(grid),"distinct_train_sequences":len(unique),"shortlists":shortlists,"train_stats":stats_by_id}
    (OUT/"train_state.json").write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"phase":"train","canonical":len(grid),"distinct_sequences":len(unique),
                      "shortlists":{g:len(s["configs"]) for g,s in shortlists.items()}},ensure_ascii=False))


def select(panel,grid):
    state=json.loads((OUT/"train_state.json").read_text());assert state["source_hashes"]==code_hashes()
    keys=sorted({k for group in state["shortlists"].values() for k in group["configs"]})
    per_asset,summary,rows_by_id=[],[],{}
    for key in keys:
        rows,_,_,_=run_config(panel,grid[key],P["windows"]["validation"])
        rows_by_id[key]=rows;per_asset.extend({"config":key,**r} for r in rows)
        summary.extend({"config":key,"group":g,**summarize(members(rows,g))} for g in ("full","good","non_good"))
    hold=run_config(panel,controls()["HOLD"],P["windows"]["validation"])[0]
    selections=[];gates=[]
    for group,shortlist in state["shortlists"].items():
        qualified={};all_supported={}
        for key in shortlist["configs"]:
            rows=rows_by_id[key];s=summarize(members(rows,group))
            reasons=hard_gates(s,summarize(members(hold,group)),summarize(members(rows,"good")),"validation",group)
            if key not in shortlist["train_passed"]:reasons.append("training_gates_failed")
            training=state["train_stats"][key][group]
            wr_drop=training["wr_eq"]-s["wr_eq"] if s["wr_eq"] is not None else None
            if wr_drop is None or wr_drop>.10:reasons.append("win_rate_instability")
            ns=[state["train_stats"][n][group]["cagr_med"] for n in neighbors(grid[key],grid)]
            ns=[x for x in ns if x is not None]
            floor=training["cagr_med"]-max(.01,.2*abs(training["cagr_med"]))
            stable=not ns or statistics.median(ns)>=floor
            if not stable:reasons.append("parameter_spike")
            gates.append({"config":key,"target":group,"passed":not reasons,"reasons":";".join(reasons),
                          "train_wr":training["wr_eq"],"validation_wr":s["wr_eq"],
                          "neighbor_cagr_median":statistics.median(ns) if ns else None,"platform_floor":floor})
            if s["wr_eq"] is not None and s["cagr_med"] is not None:
                all_supported[key]=s
                if not reasons:qualified[key]=s
        pool=qualified or all_supported
        if not pool:
            continue
        scores=rank_scores(pool)
        ids={"compromise":min(pool,key=lambda k:(-scores[k],complexity(grid[k]),k)),
             "annual_leader":min(pool,key=lambda k:(-pool[k]["cagr_med"],-pool[k]["wr_eq"],complexity(grid[k]),k)),
             "win_leader":min(pool,key=lambda k:(-pool[k]["wr_eq"],-pool[k]["cagr_med"],complexity(grid[k]),k))}
        for label,key in ids.items():
            selections.append({"target":group,"label":label,"id":key,"config":grid[key],
                               "qualified":key in qualified,"descriptive_only":not qualified,
                               "validation_stats":pool[key],"rank_score":scores[key]})
    full=next((s for s in selections if s["target"]=="full" and s["label"]=="compromise"),None)
    for s in selections:
        if s["target"]=="good":
            s["conditional_full_history_label"]=True
            non=summarize(members(rows_by_id[s["id"]],"non_good"))["cagr_med"]
            reference=summarize(members(rows_by_id[full["id"]],"non_good"))["cagr_med"] if full else None
            s["non_good_validation_no_worse_than_full"]=non is not None and reference is not None and non>=reference
    save_csv(OUT/"validation_per_etf.csv.gz",per_asset);save_csv(OUT/"validation_summary.csv",summary);save_csv(OUT/"validation_gates.csv",gates)
    lock={"source_hashes":code_hashes(),"train_state_sha256":digest(OUT/"train_state.json"),"selections":selections,
          "controls":controls(),"code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
          "test_has_not_run":True,"warning":"selected on train/validation only; final historical test cannot choose or retune any candidate"}
    (ROOT/"selection_lock.json").write_text(json.dumps(lock,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"phase":"select","evaluated":len(keys),"locked":selections},ensure_ascii=False))


def bootstrap_difference(a,b):
    ma={r["code"]:r for r in a};mb={r["code"]:r for r in b}
    ids=sorted(ma.keys()&mb.keys());rng=random.Random(20261113);ann=[];wr=[]
    for _ in range(1000):
        draw=[rng.choice(ids) for _ in ids]
        pairs=[(ma[k]["cagr"],mb[k]["cagr"]) for k in draw if ma[k]["cagr"] is not None and mb[k]["cagr"] is not None]
        wp=[ma[k]["wr"]-mb[k]["wr"] for k in draw if ma[k]["wr"] is not None and mb[k]["wr"] is not None]
        if pairs:ann.append(statistics.median(x[0] for x in pairs)-statistics.median(x[1] for x in pairs))
        if wp:wr.append(statistics.fmean(wp))
    def ci(values):
        values.sort()
        return [values[int((len(values)-1)*p)] for p in (.025,.975)] if values else [None,None]
    return {"paired_etfs":len(ids),"paired_annual_etfs":sum(ma[k]["cagr"] is not None and mb[k]["cagr"] is not None for k in ids),
            "paired_wr_etfs":sum(ma[k]["wr"] is not None and mb[k]["wr"] is not None for k in ids),
            "cagr_med_difference_ci":ci(ann),"paired_wr_mean_difference_ci":ci(wr),"replicates":1000,"seed":20261113}


def test(panel):
    lock=json.loads((ROOT/"selection_lock.json").read_text());assert lock["source_hashes"]==code_hashes()
    assert not (OUT/"test_complete.json").exists(),"test already run; never rerun for parameter selection"
    configs={s["id"]:s["config"] for s in lock["selections"]};configs.update(lock["controls"])
    records,summary,trades,nav,primary=[],[],[],[],{}
    windows={"test":P["windows"]["test"],"test_part1":P["test_subperiods"][0],"test_part2":P["test_subperiods"][1]}
    for phase,window in windows.items():
        costs=(20,*P["cost_sensitivity_bps_round_trip"]) if phase=="test" else (20,)
        for cost in costs:
            for key,config in configs.items():
                r,t,n,_=run_config(panel,config,window,cost,retain=phase=="test" and cost==20)
                records.extend({"config":key,"phase":phase,"cost":cost,**x} for x in r)
                summary.extend({"config":key,"phase":phase,"cost":cost,"group":g,**summarize(members(r,g))}
                               for g in ("full","good","non_good","cross_commodity","late"))
                trades.extend({"config":key,**x} for x in t);nav.extend({"config":key,**x} for x in n)
                if phase=="test" and cost==20:primary[key]=r
    comparisons=[]
    for key in configs:
        if key in controls():continue
        for baseline in controls():
            for group in ("full","good","non_good"):
                a=members(primary[key],group);b=members(primary[baseline],group)
                if a and b:
                    comparisons.append({"config":key,"baseline":baseline,"group":group,
                                        "candidate":summarize(a),"control":summarize(b),**bootstrap_difference(a,b)})
    save_csv(OUT/"test_per_etf.csv.gz",records);save_csv(OUT/"test_summary.csv",summary)
    save_csv(OUT/"test_trades.csv.gz",trades);save_csv(OUT/"test_nav.csv.gz",nav)
    (OUT/"test_comparisons.json").write_text(json.dumps(comparisons,ensure_ascii=False,indent=2)+"\n")
    (OUT/"test_complete.json").write_text(json.dumps({"selection_lock_sha256":digest(ROOT/"selection_lock.json"),
        "source_hashes":code_hashes(),"configs_tested":list(configs),"selection_from_test":False},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"phase":"test","configs":len(configs),"records":len(records)},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=("train","select","test"));args=parser.parse_args()
    OUT.mkdir(exist_ok=True);panel=load_panel();grid=enumerate_grid()
    if args.phase=="train":train(panel,grid)
    elif args.phase=="select":select(panel,grid)
    else:test(panel)


if __name__=="__main__":main()
