import csv, math, statistics as st, importlib
ns={}; exec(open("../附件-模拟脚本/grid_sim.py").read().split("S={")[0],ns)
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
def classify(ret):
    if ret>0.15: return "上涨(>+15%)"
    if ret<-0.15: return "下跌(<-15%)"
    if abs(ret)<=0.05: return "震荡(±5%内)"
    return "其他"
def run(code,W=250,step=20,cost=0.0005,start="2013-01-01",end="2026-12-31"):
    ns["COST"]=cost
    rows=[(d,p) for d,p in load(code) if start<=d<=end]; P=[p for _,p in rows]
    S={"买入持有":lambda p:ns["buyhold"](p,1.0),"半仓持有":lambda p:ns["buyhold"](p,0.5),
       "季度再平衡":ns["rebal"],"纯网格":ns["pure_grid"],"半仓+网格":ns["half_grid"]}
    res={}
    for i in range(0,len(P)-W,step):
        w=[x/P[i] for x in P[i:i+W+1]]
        k=classify(w[-1]-1)
        res.setdefault(k,{n:[] for n in S})
        for n,f in S.items(): res[k][n].append(f(w))
    return res
def show(code,name,**kw):
    res=run(code,**kw)
    print("###",name,kw)
    print("| 区间类型 | 窗口数 | "+" | ".join(["买入持有","半仓持有","季度再平衡","纯网格","半仓+网格"])+" |")
    print("|---|---|---|---|---|---|---|")
    for k in ["上涨(>+15%)","下跌(<-15%)","震荡(±5%内)","其他"]:
        if k not in res: continue
        r=res[k]; n=len(r["买入持有"])
        cells=[]
        for s in ["买入持有","半仓持有","季度再平衡","纯网格","半仓+网格"]:
            cells.append("%.1f / %.0f%%"%(st.median(x[0] for x in r[s]),100*st.median(x[1] for x in r[s])))
        print("| %s | %d | "%(k,n)+" | ".join(cells)+" |")
if __name__=="__main__":
    for code,name in (("sh000300","沪深300"),("sz399006","创业板指"),("sh000922","中证红利")):
        show(code,name,W=250,cost=0.0005)
    show("sh000300","沪深300",W=250,cost=0.001)
    show("sh000300","沪深300",W=500,cost=0.0005,step=40)
