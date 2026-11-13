"""Independent exact-price interval and closed-form ledger reference.

This module never calls the trading engine to construct reference outcomes.
Feature recurrences use different algebra and Decimal60; bands/MA use Fraction.
"""
from datetime import date
from decimal import Decimal,localcontext
from fractions import Fraction as F
import math


def independent_features(rows):
    prices=[F(r["adjusted_close"]) for r in rows];above=[];below=[]
    for i,x in enumerate(prices):
        mean=sum(prices[i-9:i+1])/10 if i>=9 else x
        above.append(x>mean);below.append(x<mean)
    bands={}
    for n in (9,13,21):
        values=[]
        for i in range(len(prices)):
            changes=[prices[j]-prices[j-1] for j in range(i-n+1,i+1)] if i>=n else []
            absolute=sum(abs(x) for x in changes)
            values.append(100*sum(max(0,x) for x in changes)/absolute if absolute else None)
        bands[n]=values
    macds={}
    with localcontext() as ctx:
        ctx.prec=60
        for fast_n,slow_n,signal_n in ((8,17,9),(12,26,9),(16,35,9)):
            fast=slow=Decimal(rows[0]["adjusted_close"]);signal=Decimal(0);previous=None
            gold=[];dead=[]
            for row in rows:
                x=Decimal(row["adjusted_close"])
                fast+=(x-fast)*Decimal(2)/(fast_n+1)
                slow+=(x-slow)*Decimal(2)/(slow_n+1)
                dif=fast-slow;signal+=(dif-signal)*Decimal(2)/(signal_n+1)
                gold.append(previous is not None and previous[0]<=previous[1] and dif>signal)
                dead.append(previous is not None and previous[0]>=previous[1] and dif<signal)
                previous=dif,signal
            macds[(fast_n,slow_n,signal_n)]=(gold,dead)
    return {"bands":bands,"above":above,"below":below,"macds":macds}


def independent_intervals(rows,f,c,window,p):
    valid=[i for i,r in enumerate(rows) if i>=p["warmup_excluded_rows"] and window[0]<=r["date"]<=window[1]]
    if len(valid)<p["minimum_window_rows"]:return None
    start,end=valid[0],valid[-1]
    v=f["bands"][c["n"]] if c["n"] else [None]*len(rows)
    gold,dead=f["macds"][tuple(c["macd"])] if c["macd"] else ([False]*len(rows),[False]*len(rows))
    intervals=[];cursor=start
    while cursor<end:
        found=None;last_recovery=None
        for i in range(cursor,end):
            er=c["entry"]
            if er=="HOLD":ready=i==start
            elif er=="MA":ready=f["above"][i]
            elif er=="MACD":ready=gold[i]
            elif er=="E3":ready=f["above"][i] and gold[i] and (c["cap"] is None or v[i] is not None and v[i]<=c["cap"])
            else:
                cross=v[i] is not None and v[i-1] is not None and v[i-1]<c["lo"]<=v[i]
                if er=="E1":ready=cross and f["above"][i]
                else:
                    if v[i] is None or v[i]<c["lo"]:last_recovery=None
                    if cross:last_recovery=i
                    ready=last_recovery is not None and i-last_recovery<c["wait"] and f["above"][i] and v[i]>=c["lo"]
            if ready:
                found=i;break
        if found is None:break
        enter=found+1;exit_signal=None;seen_high=False
        for i in range(enter,end):
            xr=c["exit"]
            if c["hi"] is not None and v[i] is not None and v[i]>=c["hi"]:seen_high=True
            top=c["hi"] is not None and seen_high and v[i] is not None and v[i]<c["hi"]
            if ((xr=="X1" and f["below"][i]) or (xr=="X2" and dead[i])
                or (xr=="X3" and dead[i] and (f["below"][i] or top))
                or (xr=="X4" and (f["below"][i] or dead[i]))):
                exit_signal=i;break
        exit_=exit_signal+1 if exit_signal is not None else end
        intervals.append((found,enter,exit_signal,exit_,exit_signal is None))
        if exit_signal is None:break
        cursor=exit_
    return valid,intervals


def independent_ledger(rows,intervals,valid,cost):
    side=F(cost,20000);cash=F(1);reserve=F(0);components=[];natural=wins=0;fees=F(0)
    for span in intervals:
        signal,entry,exit_signal,exit_,forced=span
        a,b=rows[entry],rows[exit_]
        quantity=cash/(F(a["open"])*(1+side));base=quantity/F(a["share_factor"])
        coupon=base*(F(b["cumulative_cash"])-F(a["cumulative_cash"]))
        price=F(b["close"] if forced else b["open"])
        exit_shares=base*F(b["share_factor"]);sale=exit_shares*price*(1-side)
        ret=(sale+coupon)/cash-1
        fees+=quantity*F(a["open"])*side+exit_shares*price*side
        natural+=not forced;wins+=not forced and ret>0
        components.append({"span":span,"before_cash":cash,"before_reserve":reserve,"base":base,"sale":sale,"coupon":coupon,"return":ret,"shares":quantity})
        cash,reserve=sale,reserve+coupon
    nav=[];peak=1.0;dd=0.0
    for i in valid:
        cap,div,market=F(1),F(0),F(0)
        for component in components:
            _,entry,_,exit_,_=component["span"]
            if i<entry:break
            if i>=exit_:
                cap,div=component["sale"],component["before_reserve"]+component["coupon"]
            else:
                cap=F(0)
                div=component["before_reserve"]+component["base"]*(F(rows[i]["cumulative_cash"])-F(rows[entry]["cumulative_cash"]))
                market=component["base"]*F(rows[i]["share_factor"])*F(rows[i]["close"])
                break
        value=float(cap+div+market);nav.append(value)
        peak=max(peak,value);dd=min(dd,value/peak-1)
    return {"nav":nav,"components":components,"final_nav":float(cash+reserve),"natural":natural,"wins":wins,
            "mdd":dd,"fees":float(fees),"reserve":float(reserve)}
