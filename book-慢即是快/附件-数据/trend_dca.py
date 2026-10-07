import csv, statistics as st
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
def classify(r):
    return "上涨" if r>0.15 else "下跌" if r<-0.15 else "震荡" if abs(r)<=0.05 else "其他"
def mdd(v):
    pk=v[0]; m=0
    for x in v: pk=max(pk,x); m=max(m,1-x/pk)
    return m
def ma_state(P,n):
    # 第t日收盘后判断，t+1日起生效：s[t]=1 表示持有 t→t+1 的收益
    s=[0]*len(P)
    for t in range(n-1,len(P)):
        s[t]=1 if P[t]>sum(P[t-n+1:t+1])/n else 0
    return s
def trend_window(P,s,i,W,cost):
    # 窗口 [i, i+W]，窗口开始时按 s[i] 决定初始仓位
    val=1.0; pos=s[i]; trades=0; v=[1.0]
    if pos: val*=1-cost; trades+=1
    for t in range(i,i+W):
        if pos: val*=P[t+1]/P[t]
        new=s[t+1] if t+1<i+W else pos
        if new!=pos: val*=1-cost; trades+=1; pos=new
        v.append(val)
    return 100*val,mdd(v),trades
def hold_window(P,i,W,cost):
    v=[(1-cost)*P[t]/P[i] for t in range(i,i+W+1)]; return 100*v[-1],mdd(v),1
def half_window(P,i,W,cost):
    v=[0.5+0.5*(1-cost)*P[t]/P[i] for t in range(i,i+W+1)]; return 100*v[-1],mdd(v),1
def dca_window(P,i,W,cost,every=21):
    n=W//every; amt=100/n; cash=100.0; sh=0.0; v=[]
    for k,t in enumerate(range(i,i+W+1)):
        if (t-i)%every==0 and (t-i)//every<n:
            sh+=amt*(1-cost)/P[t]; cash-=amt
        v.append(cash+sh*P[t])
    return v[-1],mdd(v),n
def run(code,W,step,cost=0.0005):
    P=[p for _,p in load(code)]; D=[d for d,_ in load(code)]
    s200=ma_state(P,200); s120=ma_state(P,120)
    res={}
    for i in range(200,len(P)-W-1,step):   # 从第200日后开始，保证均线可用
        r=P[i+W]/P[i]-1; k=classify(r)
        d=res.setdefault(k,{n:[] for n in ["买入持有","半仓持有","定投","200日均线","120日均线"]})
        d["买入持有"].append(hold_window(P,i,W,cost)); d["半仓持有"].append(half_window(P,i,W,cost))
        d["定投"].append(dca_window(P,i,W,cost))
        d["200日均线"].append(trend_window(P,s200,i,W,cost)); d["120日均线"].append(trend_window(P,s120,i,W,cost))
    return res
def table(code,name,W,step):
    res=run(code,W,step); cols=["买入持有","半仓持有","定投","200日均线","120日均线"]
    print("###",name,"窗口",W)
    print("| 区间类型 | 窗口数 | "+" | ".join(cols)+" |"); print("|---|---|"+"---|"*len(cols))
    for k in ["上涨","下跌","震荡","其他"]:
        if k not in res: continue
        r=res[k]; n=len(r["买入持有"])
        print("| %s | %d | "%(k,n)+" | ".join("%.1f / %.0f%%"%(st.median(x[0] for x in r[c]),100*st.median(x[1] for x in r[c])) for c in cols)+" |")
    allw={c:[x for k in res for x in res[k][c]] for c in cols}
    base=allw["买入持有"]
    for c in ["定投","200日均线","120日均线","半仓持有"]:
        d=[a[0]-b[0] for a,b in zip(allw[c],base)]
        print("  全部窗口(%d) %s−买入持有: 平均%.1f 中位%.1f 跑赢%.0f%% | 回撤中位 %.0f%% 对 %.0f%% | 交易次数中位 %d"%(len(d),c,st.mean(d),st.median(d),100*sum(x>0 for x in d)/len(d),100*st.median(x[1] for x in allw[c]),100*st.median(x[1] for x in base),st.median(x[2] for x in allw[c])))
def fullperiod(code,name,cost=0.0005):
    D=[d for d,_ in load(code)]; P=[p for _,p in load(code)]
    for n in (200,120):
        s=ma_state(P,n); i=200; W=len(P)-1-i
        v,m,tr=trend_window(P,s,i,W,cost); h,mh,_=hold_window(P,i,W,cost)
        yrs=W/243
        print("%s 全期(%s→%s) %d日均线: 终值%.0f 年化%.1f%% 最大回撤%.0f%% 交易%d次 | 买入持有: 终值%.0f 年化%.1f%% 最大回撤%.0f%%"%(name,D[i],D[-1],n,v,100*((v/100)**(1/yrs)-1),100*m,tr,h,100*((h/100)**(1/yrs)-1),100*mh))
if __name__=="__main__":
    for code,name in (("sh000300","沪深300"),("sz399006","创业板指"),("sh000922","中证红利")):
        table(code,name,250,20); fullperiod(code,name)
    table("sh000300","沪深300",750,40)
