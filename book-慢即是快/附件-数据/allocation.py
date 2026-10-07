import csv, math, statistics as st
def load(c): return dict((a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:])
S={"沪深300":load("sh000300"),"创业板指":load("sz399006"),"中证红利":load("sh000922"),"上证国债":load("sh000012")}
dates=sorted(set.intersection(*[set(v) for v in S.values()]))
dates=[d for d in dates if d>="2013-01-01"]
R={k:[S[k][dates[i]]/S[k][dates[i-1]]-1 for i in range(1,len(dates))] for k in S}
D=dates[1:]
def mdd(v):
    pk=v[0]; m=0
    for x in v: pk=max(pk,x); m=max(m,1-x/pk)
    return m
def port(w,reb="Y"):
    val=1.0; hold={k:val*w[k] for k in w}; v=[1.0]; lastkey=D[0][:4]
    for i,d in enumerate(D):
        key=d[:4] if reb=="Y" else None
        if reb=="Y" and key!=lastkey:
            tot=sum(hold.values()); hold={k:tot*w[k] for k in w}; lastkey=key
        for k in hold: hold[k]*=1+R[k][i]
        v.append(sum(hold.values()))
    return v
def summ(name,v):
    r=[v[i]/v[i-1]-1 for i in range(1,len(v))]
    yrs=len(r)/243; ann=v[-1]**(1/yrs)-1; vol=st.pstdev(r)*math.sqrt(243)
    print("| %s | %.1f%% | %.1f%% | %.0f%% | %.2f |"%(name,100*ann,100*vol,100*mdd(v),v[-1]))
print("区间",D[0],"→",D[-1],"交易日",len(D))
print("| 组合 | 年化 | 年化波动 | 最大回撤 | 期末(1起) |"); print("|---|---|---|---|---|")
for k in S: summ(k,port({k:1.0}))
summ("沪深300/创业板/红利 各1/3",port({"沪深300":1/3,"创业板指":1/3,"中证红利":1/3}))
summ("沪深300/国债 各50%",port({"沪深300":.5,"上证国债":.5}))
summ("沪深300 20%+国债 80%",port({"沪深300":.2,"上证国债":.8}))
summ("三权益+国债 各25%",port({"沪深300":.25,"创业板指":.25,"中证红利":.25,"上证国债":.25}))
ks=list(S)
print("\n日收益相关系数")
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); 
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
print("| |"+"|".join(ks)+"|"); print("|---|"+"---|"*len(ks))
for a in ks: print("|%s|"%a+"|".join("%.2f"%corr(R[a],R[b]) for b in ks)+"|")
# 股票大跌时国债表现：沪深300 周度跌幅最大的10%周
