import csv, math, random, statistics as st
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
def stats(code,name,start=None):
    rows=[(d,p) for d,p in load(code) if (start is None or d>=start)]
    D=[d for d,_ in rows]; P=[p for _,p in rows]
    R=[P[i]/P[i-1]-1 for i in range(1,len(P))]; DD=D[1:]
    n=len(R); tot=P[-1]/P[0]-1
    idx=sorted(range(n),key=lambda i:R[i])
    def comp(skip):
        v=1.0
        for i in range(n):
            if i not in skip: v*=1+R[i]
        return v-1
    yrs=n/243
    print("##",name,D[0],"→",D[-1],"交易日",n,"区间涨幅%.1f%%"%(100*tot),"年化%.1f%%"%(100*((1+tot)**(1/yrs)-1)))
    for N in (5,10,20,30):
        best=set(idx[-N:]); worst=set(idx[:N])
        print(" 错过最好%d天: 涨幅%.1f%% | 躲开最差%d天: 涨幅%.1f%% | 同时错过最好并躲开最差: %.1f%%"%(N,100*comp(best),N,100*comp(worst),100*comp(best|worst)))
    rng=random.Random(1); res=[]
    for _ in range(500):
        sk=set(rng.sample(range(n),10)); res.append(comp(sk))
    print(" 随机缺席10天(500次): 中位%.1f%% 范围[%.1f%%,%.1f%%]"%(100*st.median(res),100*min(res),100*max(res)))
    top=idx[-10:]; bot=idx[:10]
    near=sum(1 for t in top if any(abs(t-b)<=10 for b in bot))
    print(" 最好10天中，有%d天在最差10天的前后10个交易日内"%near)
    print(" 最好10天:",[(DD[i],round(100*R[i],1)) for i in sorted(top)])
    # 逐年：去掉当年最好5天
    print(" 逐年: 全年 / 去掉当年最好5天 / 当年最好5天合计占全年对数收益")
    for y in sorted(set(d[:4] for d in DD)):
        ii=[i for i in range(n) if DD[i].startswith(y)]
        if len(ii)<200: continue
        full=math.prod(1+R[i] for i in ii)-1
        b5=sorted(ii,key=lambda i:R[i])[-5:]
        ex=math.prod(1+R[i] for i in ii if i not in b5)-1
        print("  %s: %+.1f%% / %+.1f%%"%(y,100*full,100*ex))
stats("sh000300","沪深300")
stats("sz399006","创业板指",start="2011-01-01")
