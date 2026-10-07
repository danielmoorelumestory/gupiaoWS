import csv, statistics as st
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
def run(code,name,start):
    r=[x for x in load(code) if x[0]>=start]; P=[p for _,p in r]
    print("##",name,r[0][0],"→",r[-1][0])
    print("| 持有期 | 窗口数 | 盈利占比 | 收益中位数 | 最差 | 最好 |"); print("|---|---|---|---|---|---|")
    for W,label in ((21,"1个月"),(63,"3个月"),(125,"6个月"),(250,"1年"),(500,"2年"),(750,"3年"),(1250,"5年")):
        rs=[P[i+W]/P[i]-1 for i in range(len(P)-W)]
        if not rs: continue
        print("| %s | %d | %.0f%% | %+.1f%% | %+.1f%% | %+.1f%% |"%(label,len(rs),100*sum(x>0 for x in rs)/len(rs),100*st.median(rs),100*min(rs),100*max(rs)))
run("sh000300","沪深300","2008-01-01"); run("sh000300","沪深300","2013-01-01"); run("sz399006","创业板指","2011-01-01"); run("sh000922","中证红利","2009-01-01")
