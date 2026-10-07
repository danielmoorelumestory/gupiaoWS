# 生成附录F的“数据口径对照表”：同一指数在不同起点下的年化、波动、最大回撤。价格指数，不含分红。
import csv, math, statistics as st
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
def stat(code,start,end=None):
    rows=[(d,p) for d,p in load(code) if d>=start and (end is None or d<=end)]
    P=[p for _,p in rows]; r=[P[i]/P[i-1]-1 for i in range(1,len(P))]
    N=252 if code.startswith('us_') else 247 if code.startswith('hk') else 243   # 年交易日：A股约243、美股252、港股约247
    yrs=len(r)/N; pk=P[0]; m=0
    for x in P: pk=max(pk,x); m=max(m,1-x/pk)
    return rows[0][0],rows[-1][0],(P[-1]/P[0])**(1/yrs)-1,st.pstdev(r)*math.sqrt(N),m
NAMES={"sh000300":"沪深300","sz399006":"创业板指","sh000922":"中证红利","sh000012":"上证国债","us_INX":"标普500（美元）","us_NDX":"纳指100（美元）","hkHSTECH":"恒生科技（港元）","sh518880":"黄金ETF 518880（未复权）"}
WIN=[("2008-01-02","全部可得"),("2009-06-01","第3章"),("2013-01-01","第7、8章等"),("2020-07-27","第9章（受恒生科技起点限制）")]
print("| 指数 | 起点 | 终点 | 年化 | 年化波动 | 最大回撤 | 主要用于 |"); print("|---|---|---|---|---|---|---|")
for code in ("sh000300","sh000922","sz399006","sh000012"):
    for s,use in WIN:
        a,b,ann,vol,m=stat(code,s)
        if a>s[:4]+"-12-31": continue
        print("| %s | %s | %s | %.1f%% | %.1f%% | %.0f%% | %s |"%(NAMES[code],a,b,100*ann,100*vol,100*m,use))
for code,s,use in (("us_INX","2010-01-01","第11章（原第10章）"),("us_NDX","2010-01-01","同上"),("hkHSTECH","2020-07-27","第9章"),("sh518880","2020-07-27","第9章"),("us_INX","2020-07-27","第9章")):
    a,b,ann,vol,m=stat(code,s); print("| %s | %s | %s | %.1f%% | %.1f%% | %.0f%% | %s |"%(NAMES[code],a,b,100*ann,100*vol,100*m,use))
