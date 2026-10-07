# 第十五轮：由 ../ref_plan.py 复制，红利与标普500换全收益指数；恒生科技仍为价格指数（未取得全收益序列），黄金ETF不分红，国债指数含利息。
import csv, math, statistics as st
from datetime import date
from bisect import bisect_right
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def load(c): return dict((a,float(b)) for a,b in list(csv.reader((ROOT / (c+".csv")).open()))[1:])
S={"红利(中证红利全收益)":load("H00922"),"纯债(上证国债)":load("../sh000012"),"标普500(全收益)":load("SP500TR"),"黄金ETF":load("../sh518880"),"恒生科技(价格)":load("../hkHSTECH")}  # 第十五轮：红利、标普换全收益；恒生科技无可得全收益序列，仍为价格
# 日期并集；休市时沿用最后可用价格。按日期对齐，未处理异步收盘。
dates=sorted({d for series in S.values() for d in series if "2020-07-27"<=d<="2026-09-30"})
for key, series in S.items():
    available=sorted(series)
    positions=[bisect_right(available,d)-1 for d in dates]
    if min(positions)<0: raise ValueError(key+"缺少起始估值")
    S[key]={d:series[available[i]] for d,i in zip(dates,positions)}
years=(date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days/365.2425
month_ends=[i for i,d in enumerate(dates) if i==len(dates)-1 or d[:7]!=dates[i+1][:7]]
def monthly(values):
    return [values[b]/values[a]-1 for a,b in zip(month_ends,month_ends[1:])]
K=list(S); R={k:[S[k][dates[i]]/S[k][dates[i-1]]-1 for i in range(1,len(dates))] for k in K}; D=dates[1:]
def mdd(v):
    pk=v[0]; m=0
    for x in v: pk=max(pk,x); m=max(m,1-x/pk)
    return m
def run(w,mode,bands=None,cost=0.0005):
    hold=dict(w); v=[1.0]; trades=0; last=D[0][:4]
    for i,d in enumerate(D):
        reb=False
        if mode=="年度" and d[:4]!=last: reb=True
        if mode=="阈值":
            tot=sum(hold.values())
            if any(abs(hold[k]/tot-w[k])>bands[k]*w[k] for k in w): reb=True
        last=d[:4]
        if reb:
            tot=sum(hold.values()); t=sum(abs(hold[k]-tot*w[k]) for k in w)/2; tot-=t*cost*2; trades+=1
            hold={k:tot*w[k] for k in w}
        for k in hold: hold[k]*=1+R[k][i]
        v.append(sum(hold.values()))
    r=[v[i]/v[i-1]-1 for i in range(1,len(v))]; yrs=years
    return v,(v[-1]**(1/yrs)-1,st.pstdev(monthly(v))*math.sqrt(12),mdd(v),v[-1],trades)
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
print("区间",dates[0],"→",dates[-1],"自然年数",round(years,6),"并集估值日",len(dates),"月收益数",len(month_ends)-1)
print("单项：自然日期年化/月度年化波动/最大回撤")
for k in K:
    v,s=run({k:1.0},"无"); print(" %s: %.1f%% / %.1f%% / %.0f%%"%(k,100*s[0],100*s[1],100*s[2]))
w={k:0.2 for k in K}; bands={k:(0.35 if k.startswith("恒生科技") else 0.25) for k in K}
print("五项等权（配置部分）")
for m,b in (("无",None),("年度",None),("阈值",bands)):
    v,s=run(w,m,b); print(" %s: 年化%.1f%% 波动%.1f%% 最大回撤%.0f%% 期末%.3f 再平衡%d次"%(m,100*s[0],100*s[1],100*s[2],s[3],s[4]))
print("相关系数(月度/统一自然月末估值/原币种)")
print("|"+"|".join(K)+"|")
for a in K: print("|"+"|".join("%.2f"%corr(monthly([S[a][d] for d in dates]),monthly([S[b][d] for d in dates])) for b in K)+"|")
print("分年(价格): ")
for y in range(2021,2027):
    row=[]
    for k in K:
        idx=[i for i,d in enumerate(D) if d.startswith(str(y))]; prev=[i for i,d in enumerate(D) if d<f"{y}-01-01"]
        base=S[k][dates[prev[-1]+1]] if prev else S[k][dates[0]]; end=S[k][D[idx[-1]]]
        row.append("%+.1f%%"%(100*(end/base-1)))
    v,_=run(w,"年度"); 
    print(y,row)
