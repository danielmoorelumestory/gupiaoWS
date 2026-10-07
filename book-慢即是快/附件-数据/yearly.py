import csv
N={"sh000300":"沪深300","sz399006":"创业板指","sh000922":"中证红利","sh000012":"上证国债","sh000905":"中证500"}
S={c:[(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]] for c in N}
def yr(c,y):
    rows=[p for d,p in S[c] if d.startswith(str(y))]; prev=[p for d,p in S[c] if d<f"{y}-01-01"]
    if not rows or not prev: return None
    return rows[-1]/prev[-1]-1
def mdd(c,y):
    rows=[p for d,p in S[c] if d.startswith(str(y))]; pk=rows[0]; m=0
    for x in rows: pk=max(pk,x); m=max(m,1-x/pk)
    return m
f=lambda v:"—" if v is None else "%+.1f%%"%(100*v)
print("| 年份 | 沪深300 | 创业板指 | 中证红利 | 上证国债 | 50/50（沪深300+国债，年初再平衡） | 沪深300年内最大回撤 |")
print("|---|---|---|---|---|---|---|")
for y in range(2013,2027):
    a,b,c,d=[yr(k,y) for k in ("sh000300","sz399006","sh000922","sh000012")]
    mix=None if a is None or d is None else 0.5*a+0.5*d
    print("| %d%s | %s | %s | %s | %s | %s | %.0f%% |"%(y,"（至9月30日）" if y==2026 else "",f(a),f(b),f(c),f(d),f(mix),100*mdd("sh000300",y)))
