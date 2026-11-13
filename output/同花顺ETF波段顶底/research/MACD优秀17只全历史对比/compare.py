"""Frozen MACD/B versus inception buy-and-hold, extended to completed quotes.

No tuning. The original archive is read-only. New raw responses and merged
inputs are stored here; overlapping prices and historical factors must agree.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent
SPEC=json.loads((ROOT/"protocol.json").read_text())
SOURCE=ROOT.parents[0]/"数据训练优化ETF"
sys.path.insert(0,str(SOURCE))
import engine
from reference import independent_features,independent_intervals,independent_ledger
from prepare_data import normalize_cash_factors


def get(name,url):
    path=ROOT/"raw"/name
    if path.exists():return gzip.decompress(path.read_bytes())
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://finance.sina.com.cn/"})
    error=None
    for _ in range(2):
        try:
            with urllib.request.urlopen(request,timeout=18) as response:body=response.read()
            path.write_bytes(gzip.compress(body,mtime=0));return body
        except Exception as exc:error=exc
    raise RuntimeError(str(error))


def collect(item):
    code=item["code"];symbol=("sh" if code.startswith("5") else "sz")+code
    oldpath=SOURCE/f"data/{code}.csv.gz"
    old=list(csv.DictReader(io.StringIO(gzip.decompress(oldpath.read_bytes()).decode())))
    merged={r["date"]:{k:r[k] for k in ("date","open","high","low","close")} for r in old}
    url=f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,2026-10-20,2026-11-14,100,"
    payload=json.loads(get(f"{code}-tencent-raw.json.gz",url))
    assert payload.get("code")==0
    bars=payload["data"][symbol].get("day",[]);assert bars,"no recent raw quotes"
    overlap=0;added=[]
    for bar in bars:
        day=bar[0]
        if day>SPEC["cutoff_requested"]:continue
        r=dict(date=day,open=bar[1],close=bar[2],high=bar[3],low=bar[4])
        if day in merged:
            assert all(D(merged[day][k])==D(r[k]) for k in ("open","high","low","close")),("overlapping quote mismatch",code,day)
            overlap+=1
        else:
            merged[day]=r;added.append(day)
    assert overlap>0 and added,"no current extension or no shared quote for validation"
    factor_url=f"https://finance.sina.com.cn/realstock/company/{symbol}/hfq.js"
    text=get(f"{code}-sina-hfq.js.gz",factor_url).decode("gb18030",errors="replace")
    assert text.startswith(f"var {symbol}hfq=")
    factors_json,_=json.JSONDecoder().raw_decode(text.split("=",1)[1])
    fs=[]
    for row in sorted(factors_json["data"],key=lambda x:x["d"]):
        if row["d"]>SPEC["cutoff_requested"]:continue
        assert D(row["f"])==1
        fs.append((row["d"],D(row["s"]),D(row["u"])))
    capitals=normalize_cash_factors(fs);factor_dates=[f[0] for f in capitals]
    rows=[]
    for day in sorted(merged):
        r=merged[day];values=[D(r[k]) for k in ("open","high","low","close")]
        assert min(values)>0 and values[2]<=min(values[0],values[3])<=max(values[0],values[3])<=values[1]
        index=bisect.bisect_right(factor_dates,day)-1;assert index>=0
        _,s,k=capitals[index]
        rows.append({**r,"share_factor":str(s),"cumulative_cash":str(k),"adjusted_close":str(D(r["close"])*s+k)})
    for a,b in zip(old,rows[:len(old)]):
        assert a["date"]==b["date"] and all(D(a[k])==D(b[k]) for k in ("share_factor","cumulative_cash","adjusted_close")),("past factor revision",code,a["date"])
    hfq_url=f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,2026-10-20,2026-11-14,100,hfq"
    hp=json.loads(get(f"{code}-tencent-hfq.json.gz",hfq_url));assert hp.get("code")==0
    hd=hp["data"][symbol];hb=hd.get("hfqday",hd.get("day",[]))
    by_date={r["date"]:r for r in rows};checked=0
    for bar in hb:
        if bar[0] not in by_date:continue
        actual=D(by_date[bar[0]]["adjusted_close"]);vendor=D(bar[2])
        assert abs(actual-vendor)<=max(D("0.003"),abs(vendor)*D("0.001")),("current HFQ mismatch",code,bar[0],actual,vendor)
        checked+=1
    assert checked>0
    engine.save_csv(ROOT/f"data/{code}.csv.gz",rows)
    return item,rows,{"code":code,"first":rows[0]["date"],"last":rows[-1]["date"],"rows":len(rows),
                     "added_dates":added,"raw_overlap_quotes_checked":overlap,"hfq_quotes_checked":checked,
                     "raw_url":url,"hfq_url":hfq_url,"factor_url":factor_url,
                     "source_sha256":hashlib.sha256(oldpath.read_bytes()).hexdigest(),
                     "merged_sha256":engine.digest(ROOT/f"data/{code}.csv.gz")}


def hold_from_first_open(rows):
    side=F(1,1000);q=1/(F(rows[0]["open"])*(1+side));s0=F(rows[0]["share_factor"]);k0=F(rows[0]["cumulative_cash"])
    base=q/s0;peak=1.;mdd=0.;nav=[]
    for i,r in enumerate(rows):
        market=base*F(r["share_factor"])*F(r["close"])
        cash=base*(F(r["cumulative_cash"])-k0)
        value=float(market+cash-(market*side if i==len(rows)-1 else 0))
        nav.append(value);peak=max(peak,value);mdd=min(mdd,value/peak-1)
    # Independent sequential entitlement/share update for the hold baseline.
    qq=float(q);reserve=0.
    for a,b in zip(rows,rows[1:]):
        reserve+=qq/float(a["share_factor"])*(float(b["cumulative_cash"])-float(a["cumulative_cash"]))
        qq*=float(b["share_factor"])/float(a["share_factor"])
    sequential=qq*float(rows[-1]["close"])*.999+reserve
    assert abs(sequential-nav[-1])<1e-9
    return {"final_nav":nav[-1],"total_return":nav[-1]-1,"mdd":mdd,"natural":0,"wins":0,"wr":None,"entries":1},nav


def main():
    for name in ("raw","data","results"):(ROOT/name).mkdir(exist_ok=True)
    collected=[];audit=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(collect,item) for item in SPEC["items"]]
        for future in as_completed(futures):
            item,rows,a=future.result();collected.append((item,rows));audit.append(a)
            print(item["code"],a["last"],"added",len(a["added_dates"]),flush=True)
    assert len(collected)==17
    assert all(a["last"]==SPEC["cutoff_requested"] for a in audit),"not all ETFs have the requested completed closing date"
    output=[];trades=[];checks=0;max_error=0.;daily_checks=0;secondary=[]
    for item,rows in sorted(collected,key=lambda x:x[0]["code"]):
        code=item["code"];data=engine.prepare(rows,item);ref_features=independent_features(rows)
        years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.25
        hold,_=hold_from_first_open(rows)
        output.append({"code":code,"name":item["name"],"scheme":"HOLD","first":rows[0]["date"],"last":rows[-1]["date"],"years":years,
                       **hold,"cagr":math.expm1(math.log(hold["final_nav"])/years)})
        for key,config in SPEC["configs"].items():
            result=engine.simulate(data,config,(rows[0]["date"],rows[-1]["date"]),20,True)
            valid,spans=independent_intervals(rows,ref_features,config,(rows[0]["date"],rows[-1]["date"]),engine.P)
            ref=independent_ledger(rows,spans,valid,20)
            assert len(spans)==len(result["trades"])
            for actual,want in zip(result["trades"],spans):
                assert (actual["entry_signal_index"],actual["entry_index"],actual["exit_signal_index"],actual["exit_index"],actual["forced_end"])==want
            for actual,want in zip(result["nav"],ref["nav"]):
                error=abs(actual["nav"]-want);max_error=max(error,max_error);assert error<1e-9;daily_checks+=1
            m=result["metric"]
            assert m["natural"]==ref["natural"] and m["wins"]==ref["wins"]
            output.append({"code":code,"name":item["name"],"scheme":key,"first":rows[0]["date"],"last":rows[-1]["date"],"years":years,
                           "final_nav":m["final_nav"],"total_return":m["total_return"],"mdd":m["mdd"],"natural":m["natural"],"wins":m["wins"],
                           "wr":m["wr"],"entries":m["entries"],"cagr":math.expm1(math.log(m["final_nav"])/years)})
            trades.extend({"code":code,"scheme":key,**t} for t in result["trades"]);checks+=1
        old_hold=engine.simulate(data,engine.P and {"entry":"HOLD","exit":"HOLD","n":None,"macd":None,"lo":None,"hi":None,"cap":None,"wait":None},
                                 (rows[0]["date"],rows[-1]["date"]),20,False)
        secondary.append({"code":code,"name":item["name"],**old_hold["metric"]})
    engine.save_csv(ROOT/"results/lifetime_long.csv",output);engine.save_csv(ROOT/"results/lifetime_trades.csv.gz",trades)
    engine.save_csv(ROOT/"results/hold_after_warmup_secondary.csv",secondary)
    table=[]
    for item in SPEC["items"]:
        r={x["scheme"]:x for x in output if x["code"]==item["code"]}
        table.append({"code":item["code"],"name":item["name"],"first":r["HOLD"]["first"],"last":r["HOLD"]["last"],
                      **{f"{s}_{field}":r[s][field] for s in ("HOLD","MACD","B") for field in ("total_return","cagr","wr","natural","mdd")}})
    engine.save_csv(ROOT/"results/lifetime_17_comparison.csv",table)
    aggregate={}
    for scheme in ("HOLD","MACD","B"):
        rs=[r for r in output if r["scheme"]==scheme]
        aggregate[scheme]={"cagr_median":statistics.median(r["cagr"] for r in rs),"cagr_mean":statistics.fmean(r["cagr"] for r in rs),
                           "total_return_median":statistics.median(r["total_return"] for r in rs),
                           "wr_equal":statistics.fmean(r["wr"] for r in rs if r["wr"] is not None) if scheme!="HOLD" else None,
                           "natural_trades":sum(r["natural"] for r in rs),
                           "positive_etfs":sum(r["total_return"]>0 for r in rs)}
    pairs={r["code"]:{x["scheme"]:x for x in output if x["code"]==r["code"]} for r in table}
    aggregate["B_beats_MACD_annual_etfs"]=sum(p["B"]["cagr"]>p["MACD"]["cagr"] for p in pairs.values())
    aggregate["B_beats_HOLD_annual_etfs"]=sum(p["B"]["cagr"]>p["HOLD"]["cagr"] for p in pairs.values())
    (ROOT/"results/summary.json").write_text(json.dumps(aggregate,ensure_ascii=False,indent=2)+"\n")
    (ROOT/"data_audit.json").write_text(json.dumps({"downloaded_at_utc":datetime.now(timezone.utc).isoformat(),"symbols":sorted(audit,key=lambda x:x["code"])},ensure_ascii=False,indent=2)+"\n")
    (ROOT/"results/verification.json").write_text(json.dumps({"status":"PASS","strategies_checked":checks,"daily_nav_checked":daily_checks,
        "max_absolute_error":max_error,"holding_closed_form_vs_sequential":True,"primary_history_and_overlap_unchanged":True},indent=2)+"\n")
    print(json.dumps(aggregate,ensure_ascii=False))


if __name__=="__main__":main()
