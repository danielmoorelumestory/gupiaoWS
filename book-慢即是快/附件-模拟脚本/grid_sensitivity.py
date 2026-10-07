import statistics as st, random, importlib.util, sys
spec=importlib.util.spec_from_file_location("sim","grid_sim.py")
src=open("grid_sim.py").read().split("S={")[0]
ns={}; exec(src,ns)
import math
for cost in (0.001,0.003):
    ns["COST"]=cost
    print("cost",cost)
    for s in (0.02,0.05,0.08):
        out=[]
        for kind in ("range","up","down"):
            r=[]; b=[]
            for seed in range(300):
                p=ns["path"](kind,random.Random(seed))
                r.append(ns["half_grid"](p,s=s,step=0.0625*s/0.05)[0]); b.append(ns["buyhold"](p,0.5)[0])
            out.append("%s: 半仓+网格%.1f / 半仓持有%.1f"%(kind,st.median(r),st.median(b)))
        print(" 格距%.0f%% | "%(s*100)+" | ".join(out))
