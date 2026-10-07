import csv, statistics as st, math
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
print("## 看账户时，看到亏损的概率（沪深300，2013年起，价格指数）")
r=[p for d,p in load("sh000300") if d>="2013-01-01"]
for W,label in ((1,"每天"),(5,"每周"),(21,"每月"),(63,"每季度"),(250,"每年")):
    xs=[r[i+W]/r[i]-1 for i in range(0,len(r)-W,W)]  # 不重叠
    neg=[x for x in xs if x<0]
    print("| %s | %d | %.0f%% | %.1f%% |"%(label,len(xs),100*len(neg)/len(xs),100*st.median(neg) if neg else 0))
print("\n## 涨多了就卖（价格指数，前250日涨幅超过阈值后，未来250日的表现）")
for code,name,start in (("sh000300","沪深300","2008-01-01"),("sz399006","创业板指","2011-01-01"),("sh000922","中证红利","2009-01-01")):
    P=[p for d,p in load(code) if d>=start]
    for th in (0.3,0.5):
        fw=[];  # 触发日的未来250日收益
        i=250; 
        while i<len(P)-250:
            if P[i]/P[i-250]-1>th:
                fw.append(P[i+250]/P[i]-1); i+=20   # 每20日取一个触发点，减少重叠
            else: i+=1
        if fw: print("%s 过去250日涨幅>%d%% 触发%d次: 未来250日 中位%+.1f%% 上涨占比%.0f%% 最差%+.1f%% 最好%+.1f%%"%(name,th*100,len(fw),100*st.median(fw),100*sum(x>0 for x in fw)/len(fw),100*min(fw),100*max(fw)))
        # 全部250日窗口基准
    allw=[P[i+250]/P[i]-1 for i in range(len(P)-250)]
    print("  基准(全部窗口): 中位%+.1f%% 上涨占比%.0f%%"%(100*st.median(allw),100*sum(x>0 for x in allw)/len(allw)))
