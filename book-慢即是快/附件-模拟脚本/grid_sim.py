import math, random, statistics as st
COST=0.001  # 单边成本 0.1%（假设）
DAYS=500
def path(kind,rng):
    vol=0.012; p=[1.0]
    for t in range(1,DAYS):
        if kind=="up":    mu=math.log(1.45)/DAYS
        elif kind=="down":mu=math.log(0.60)/DAYS
        elif kind=="range":mu=-0.04*math.log(p[-1])      # 向1回归
        elif kind=="vshape": mu=(math.log(0.70) if t<DAYS/2 else math.log(1.45))/(DAYS/2)
        p.append(p[-1]*math.exp(mu+vol*rng.gauss(0,1)))
    return p
def mdd(v):
    pk=v[0]; m=0
    for x in v: pk=max(pk,x); m=max(m,1-x/pk)
    return m
def buyhold(p,w=1.0):
    sh=100*w/p[0]; cash=100*(1-w)-100*w*COST; sh=100*w*(1-COST)/p[0]
    v=[cash+sh*x for x in p]; return v[-1],mdd(v),1
def rebal(p,w=0.5,every=63):
    cash=100*(1-w); sh=100*w*(1-COST)/p[0]; n=1; v=[]
    for t,x in enumerate(p):
        if t>0 and t%every==0:
            tot=cash+sh*x; tgt=w*tot; d=tgt-sh*x
            if abs(d)>1e-9: n+=1; sh+=d*(1-COST)/x if d>0 else d/x; cash-=d if d>0 else d*(1-COST)
        v.append(cash+sh*x)
    return v[-1],mdd(v),n
def pure_grid(p,s=0.05,N=8):
    C=100.0; unit=C/N; cash=C; lots={}; n=0; v=[]
    L=lambda k:p[0]*(1-k*s)
    for x in p:
        for k in range(1,N+1):
            if k in lots:
                if x>=L(k-1): cash+=lots[k]*L(k-1)*(1-COST); del lots[k]; n+=1
            else:
                if x<=L(k) and cash>=unit-1e-9: lots[k]=unit*(1-COST)/L(k); cash-=unit; n+=1
        v.append(cash+sum(sh*x for sh in lots.values()))
    return v[-1],mdd(v),n
def half_grid(p,s=0.05,step=0.0625,lo=0.25,hi=0.75):
    sh=50*(1-COST)/p[0]; cash=50.0; idx0=0; n=1; v=[]
    for x in p:
        idx=math.floor(math.log(x/p[0])/math.log(1+s))
        if idx!=idx0:
            tot=cash+sh*x; w=min(hi,max(lo,0.5-step*idx)); d=w*tot-sh*x
            if abs(d)>1e-9:
                n+=1
                if d>0: sh+=d*(1-COST)/x; cash-=d
                else: sh+=d/x; cash-=d*(1-COST)
            idx0=idx
        v.append(cash+sh*x)
    return v[-1],mdd(v),n
S={"买入持有(100%)":lambda p:buyhold(p,1.0),"半仓持有(50%)":lambda p:buyhold(p,0.5),
   "季度50/50再平衡":rebal,"纯网格":pure_grid,"半仓+网格":half_grid}
names={"up":"单边上涨","down":"单边下跌","range":"区间震荡","vshape":"先跌后涨"}
res={}
for kind in names:
    rows={k:[] for k in S}
    for seed in range(300):
        rng=random.Random(seed); p=path(kind,rng)
        for k,f in S.items(): rows[k].append(f(p))
    res[kind]=rows
print("| 路径 | 方案 | 期末资产中位数 | 最大回撤中位数 | 成交次数中位数 |")
print("|---|---|---|---|---|")
for kind,rows in res.items():
    for k,r in rows.items():
        print("| %s | %s | %.1f | %.0f%% | %d |"%(names[kind],k,st.median(x[0] for x in r),100*st.median(x[1] for x in r),st.median(x[2] for x in r)))
# 标的期末价中位数
for kind in names:
    print(kind, round(st.median(path(kind,random.Random(s))[-1] for s in range(300)),3))
