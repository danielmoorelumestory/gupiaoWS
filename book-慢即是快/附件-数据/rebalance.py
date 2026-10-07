import csv, math, statistics as st
def load(c): return dict((a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:])
S={"沪深300":load("sh000300"),"创业板指":load("sz399006"),"中证红利":load("sh000922"),"上证国债":load("sh000012")}
dates=sorted(set.intersection(*[set(v) for v in S.values()])); dates=[d for d in dates if d>="2013-01-01"]
R={k:[S[k][dates[i]]/S[k][dates[i-1]]-1 for i in range(1,len(dates))] for k in S}; D=dates[1:]
def mdd(v):
    pk=v[0]; m=0
    for x in v: pk=max(pk,x); m=max(m,1-x/pk)
    return m
def run(w,mode,cost=0.0005,band=0.25):
    hold={k:w[k] for k in w}; v=[1.0]; trades=0; turn=0.0; last=D[0][:4]; lastq=(D[0][:4],(int(D[0][5:7])-1)//3)
    for i,d in enumerate(D):
        reb=False
        if mode=="年度" and d[:4]!=last: reb=True
        if mode=="季度" and (d[:4],(int(d[5:7])-1)//3)!=lastq: reb=True
        if mode=="阈值":
            tot=sum(hold.values())
            if any(abs(hold[k]/tot-w[k])>band*w[k] for k in w): reb=True
        last=d[:4]; lastq=(d[:4],(int(d[5:7])-1)//3)
        if reb:
            tot=sum(hold.values()); t=sum(abs(hold[k]-tot*w[k]) for k in w)/2
            cst=t*cost*2/1 if False else t*cost*2   # 买卖双边近似
            tot-=cst; trades+=1; turn+=t/tot
            hold={k:tot*w[k] for k in w}
        for k in hold: hold[k]*=1+R[k][i]
        v.append(sum(hold.values()))
    r=[v[i]/v[i-1]-1 for i in range(1,len(v))]; yrs=len(r)/243
    return (v[-1]**(1/yrs)-1, st.pstdev(r)*math.sqrt(243), mdd(v), v[-1], trades, turn)
def table(title,w):
    print("###",title)
    print("| 方式 | 年化 | 年化波动 | 最大回撤 | 期末(1起) | 再平衡次数 | 累计换手(占组合) |"); print("|---|---|---|---|---|---|---|")
    for m in ["不再平衡","年度","季度","阈值"]:
        a,b,c,d,e,f=run(w,m)
        print("| %s | %.2f%% | %.1f%% | %.1f%% | %.3f | %d | %.0f%% |"%(m if m!="阈值" else "阈值(相对±25%)",100*a,100*b,100*c,d,e,100*f))
table("沪深300/国债 50/50",{"沪深300":.5,"上证国债":.5})
table("沪深300/创业板/红利/国债 各25%",{"沪深300":.25,"创业板指":.25,"中证红利":.25,"上证国债":.25})
# 权重漂移：不再平衡时，权益占比的终点
w={"沪深300":.5,"上证国债":.5}; hold=dict(w)
mx=0
for i in range(len(D)):
    for k in hold: hold[k]*=1+R[k][i]
    mx=max(mx,hold["沪深300"]/sum(hold.values()))
print("不再平衡时沪深300占比终点%.0f%% 最高%.0f%%"%(100*hold["沪深300"]/sum(hold.values()),100*mx))
