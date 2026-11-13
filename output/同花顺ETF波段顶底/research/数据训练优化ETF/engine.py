"""Causal, standard-library long/cash engine with explicit corporate actions."""
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import sys

from grid import MACDS, PERIODS

ROOT = Path(__file__).resolve().parent
P = json.loads((ROOT/"protocol.json").read_text())
sys.path.insert(0,str(ROOT.parents[2]/"布鲁斯的金融宝藏/replica"))
from bruce_replica.etf_band import etf_band


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    body=stream.getvalue().encode()
    path.write_bytes(gzip.compress(body,mtime=0) if path.suffix==".gz" else body)


def load_panel():
    assert digest(ROOT/"data_audit.json")==P["audit_sha256"]
    audit=json.loads((ROOT/"data_audit.json").read_text())
    panel={}
    for item in audit["symbols"]:
        if item["code"] not in P["eligible_symbols"]:
            continue
        path=ROOT/item["normalized_file"]
        assert digest(path)==item["normalized_sha256"]
        rows=list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        panel[item["code"]]=prepare(rows,item)
    return panel


def prepare(rows,item):
    c=[Decimal(r["adjusted_close"]) for r in rows]
    above=[False]*len(rows);below=above.copy()
    for i in range(9,len(rows)):
        mean=sum(c[i-9:i+1])/10
        above[i],below[i]=c[i]>mean,c[i]<mean
    bands={n:etf_band([str(x) for x in c],n) for n in PERIODS}
    macds={}
    with localcontext() as context:
        context.prec=40
        for fast_n,slow_n,signal_n in MACDS:
            fast=slow=c[0];dea=Decimal(0);prior=None
            gold=[];dead=[]
            for x in c:
                fast=(2*x+(fast_n-1)*fast)/(fast_n+1)
                slow=(2*x+(slow_n-1)*slow)/(slow_n+1)
                dif=fast-slow
                dea=(2*dif+(signal_n-1)*dea)/(signal_n+1)
                gold.append(prior is not None and prior[0]<=prior[1] and dif>dea)
                dead.append(prior is not None and prior[0]>=prior[1] and dif<dea)
                prior=dif,dea
            macds[(fast_n,slow_n,signal_n)]=(gold,dead)
    return {"item":item,"rows":rows,"dates":[r["date"] for r in rows],
            "open":[float(r["open"]) for r in rows],"close":[float(r["close"]) for r in rows],
            "s":[float(r["share_factor"]) for r in rows],"u":[float(r["cumulative_cash"]) for r in rows],
            "above":above,"below":below,"bands":bands,"macds":macds}


def bounds(data,window):
    indices=[i for i,d in enumerate(data["dates"]) if i>=P["warmup_excluded_rows"] and window[0]<=d<=window[1]]
    return (indices[0],indices[-1]) if len(indices)>=P["minimum_window_rows"] else None


def simulate(data,config,window,cost=20,retain=False,liquidate_end=True):
    span=bounds(data,window)
    if span is None:
        return None
    start,end=span
    op,cl,s,u,dates=data["open"],data["close"],data["s"],data["u"],data["dates"]
    above,below=data["above"],data["below"]
    n=config["n"]
    v=data["bands"][n] if n else [None]*len(dates)
    macd=tuple(config["macd"]) if config["macd"] else None
    gold,dead=data["macds"][macd] if macd else ([False]*len(dates),[False]*len(dates))
    entry_rule,exit_rule=config["entry"],config["exit"]
    lo,hi,cap=config["lo"],config["hi"],config["cap"]
    cash,reserve,q,fees=1.0,0.0,0.0,0.0
    pending,active,armed,seen_high=None,None,None,False
    trades,nav,intervals,orders=[],[],[],[]
    natural,wins,entries,peak,dd,exposure_days,exposure_capital=0,0,0,1.0,0.0,0,0.0

    def close_trade(i,price,signal,forced):
        nonlocal cash,q,active,fees,natural,wins
        fee=q*price*cost/20000
        cash=q*price-fee;fees+=fee
        coupon=reserve-active["entry_reserve"]
        ret=(cash+coupon)/active["entry_cash"]-1
        if not forced:
            natural+=1;wins+=ret>0
        intervals.append((active["entry_index"],i,int(forced)))
        if retain:
            trades.append({**active,"exit_index":i,"exit_date":dates[i],"exit_signal_index":signal,
                           "exit_signal_date":dates[signal] if signal is not None else "",
                           "exit_price":price,"exit_cash":cash,"dividends":coupon,
                           "exit_fee":fee,"net_return":ret,"forced_end":forced})
        q,active=0.0,None

    for i in range(start,end+1):
        if q and i>start:
            reserve+=q/s[i-1]*(u[i]-u[i-1])
            q*=s[i]/s[i-1]
        if pending:
            action,signal=pending
            if action=="buy":
                q=cash/(op[i]*(1+cost/20000));fee=q*op[i]*cost/20000
                active={"entry_index":i,"entry_date":dates[i],"entry_signal_index":signal,
                        "entry_signal_date":dates[signal],"entry_price":op[i],"entry_cash":cash,
                        "entry_reserve":reserve,"entry_shares":q,"entry_fee":fee}
                fees+=fee;cash=0.0;armed=None;seen_high=False;entries+=1
            else:
                close_trade(i,op[i],signal,False)
                armed=None;seen_high=False
            pending=None
        value=cash+reserve+q*cl[i]
        held=bool(q)
        exposure_days+=held
        exposure_capital+=q*cl[i]/value
        if i==end and q and liquidate_end:
            close_trade(i,cl[i],None,True)
            value=cash+reserve
        peak=max(peak,value);dd=min(dd,value/peak-1)
        if retain:
            nav.append({"date":dates[i],"row_index":i,"nav":value,"shares":q,"cash":cash,"reserve":reserve,
                        "held_session":int(held)})
        if i==end:
            continue
        action=None
        current=v[i];previous=v[i-1] if i else None
        if q:
            armed=None
            if hi is not None and current is not None and current>=hi:
                seen_high=True
            top=seen_high and current is not None and current<hi if hi is not None else False
            sell=(exit_rule=="X1" and below[i] or exit_rule=="X2" and dead[i]
                  or exit_rule=="X3" and dead[i] and (below[i] or top)
                  or exit_rule=="X4" and (below[i] or dead[i]))
            if sell:
                action="sell"
        elif entry_rule=="HOLD":
            if i==start:
                action="buy"
        elif entry_rule=="MA":
            if above[i]:
                action="buy"
        elif entry_rule=="MACD":
            if gold[i]:
                action="buy"
        elif entry_rule=="E3":
            if gold[i] and above[i] and (cap is None or current is not None and current<=cap):
                action="buy"
        else:
            cross=previous is not None and current is not None and previous<lo<=current
            if entry_rule=="E1":
                if cross and above[i]:
                    action="buy"
            else:
                if current is None or current<lo:
                    armed=None
                if cross:
                    armed=i
                if armed is not None and i-armed>=config["wait"]:
                    armed=None
                if armed is not None and current>=lo and above[i]:
                    action="buy"
        if action:
            pending=action,i
            if retain:
                orders.append({"signal_index":i,"signal_date":dates[i],"action":action})
    days=(date.fromisoformat(dates[end])-date.fromisoformat(dates[start])).days
    years=days/365.25
    annual_valid=end-start+1>=P["annual_stats_minimum_rows"] and days>=P["annual_stats_minimum_calendar_days"]
    metric={"first":dates[start],"last":dates[end],"sessions":end-start+1,"years":years,
            "final_nav":value,"total_return":value-1,
            "cagr":math.expm1(math.log(value)/years) if annual_valid else None,
            "mdd":dd,"entries":entries,"natural":natural,"wins":wins,
            "wr":wins/natural if natural>=3 else None,"pooled_wr":wins/natural if natural else None,
            "natural_fraction":natural/entries if entries else 0.0,
            "time_exposure":exposure_days/(end-start+1),"capital_exposure":exposure_capital/(end-start+1),
            "dividend_reserve":reserve,"fees":fees}
    return {"metric":metric,"intervals":intervals,"trades":trades,"nav":nav,"orders":orders}


def summarize(records):
    wr=[r["wr"] for r in records if r["wr"] is not None]
    ann=[r["cagr"] for r in records if r["cagr"] is not None]
    entries=sum(r["entries"] for r in records);natural=sum(r["natural"] for r in records)
    years=sum(r["years"] for r in records)
    size=len(records)
    return {"etfs":size,"wr_supported_etfs":len(wr),"annual_etfs":len(ann),
            "wr_eq":statistics.fmean(wr) if wr else None,
            "pooled_wr":sum(r["wins"] for r in records)/natural if natural else None,
            "cagr_med":statistics.median(ann) if ann else None,
            "cagr_mean":statistics.fmean(ann) if ann else None,
            "mdd_med":statistics.median(r["mdd"] for r in records) if records else None,
            "natural":natural,"entries":entries,"natural_fraction":natural/entries if entries else 0,
            "one_trade_coverage":sum(r["natural"]>0 for r in records)/size if size else 0,
            "wr_coverage":len(wr)/size if size else 0,
            "trades_per_year":natural/years if years else 0,
            "max_etf_trade_share":max((r["natural"] for r in records),default=0)/natural if natural else 1,
            "total_etf_years":years}
