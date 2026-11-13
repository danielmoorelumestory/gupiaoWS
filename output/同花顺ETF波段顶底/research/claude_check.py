import json,sys,math
from fractions import Fraction as F
d=json.load(open(sys.argv[1]))['data']['sh588060']['day']
dates=[r[0] for r in d]; C=[F(r[2]) for r in d]
N=13
dc=[None]+[C[i]-C[i-1] for i in range(1,len(C))]
def UD(i):
    w=dc[i-N+1:i+1]; return sum(x for x in w if x>0), sum(-x for x in w if x<0)
V={}
for i in range(N,len(C)):
    U,D=UD(i); V[i]=100*U/(U+D) if U+D else None
for t in ['2026-10-27','2026-11-12','2026-11-13','2026-10-19','2026-08-18']:
    i=dates.index(t); U,D=UD(i)
    print(t,float(C[i]),float(dc[i]),float(U),float(D),round(float(V[i]),3), 'exiting next day:',dates[i-N+1] if i+1<len(C) else '', float(dc[i-N+1]))
i=dates.index('2026-11-13'); print('leaving at 11/13:',dates[i-N],float(dc[i-N]),'entering',float(dc[i]))
# identity checks
bad=0
for i,v in V.items():
    U,D=UD(i); A=U+D
    if v!=50+50*(C[i]-C[i-N])/A: bad+=1
print('identity mismatches',bad)
# sign disagreement dV vs dC
keys=sorted(V); dis=same=0; exitdom=0
for a,b in zip(keys,keys[1:]):
    dv=V[b]-V[a];
    if dc[b]==0 or dv==0: continue
    if (dv>0)!=(dc[b]>0): dis+=1
    else: same+=1
print('dV vs dC sign disagree',dis,'agree',same)
# zone runs & episodes
def runs(cond):
    out=[];start=None
    for i in keys:
        if cond(V[i]):
            if start is None:start=i
        elif start is not None: out.append((dates[start],i-start)); start=None
    if start is not None: out.append((dates[start],keys[-1]-start+1))
    return out
lo=runs(lambda v:v<30); hi=runs(lambda v:v>70)
print('lo runs',len(lo),lo); print('hi runs',len(hi),hi)
print('bars<30',sum(v<30 for v in V.values()),'>70',sum(v>70 for v in V.values()),'total',len(V))
# zero changes, tick
z=sum(1 for x in dc[1:] if x==0); print('zero-change days',z,'of',len(dc)-1)
# pct-return version diff
mx=0
for i in keys:
    r=[math.log(C[j]/C[j-1]) for j in range(i-N+1,i+1)]
    U=sum(x for x in r if x>0);A=sum(abs(x) for x in r)
    mx=max(mx,abs(100*U/A-float(V[i])))
print('max |V_diff - V_logret|',mx)
# A/C as volatility
import statistics
ac=[float((UD(i)[0]+UD(i)[1])/C[i]/N*100) for i in keys]
print('mean abs daily move % (A/C/13) min/med/max',min(ac),statistics.median(ac),max(ac))
# Wilder-smoothed comparison (alpha 1/13), seeded with SMA at first window
up=[max(float(x),0) if x is not None else None for x in dc]; dn=[max(-float(x),0) if x is not None else None for x in dc]
au=sum(up[1:N+1])/N; ad=sum(dn[1:N+1])/N; W={N:100*au/(au+ad)}
for i in range(N+1,len(C)):
    au=au+(up[i]-au)/N; ad=ad+(dn[i]-ad)/N; W[i]=100*au/(au+ad)
ks=[k for k in keys if k>=N+40]
print('corr-ish: mean |V-W| after burn-in',statistics.mean(abs(float(V[k])-W[k]) for k in ks),'W<30 bars',sum(W[k]<30 for k in ks),'V<30 bars',sum(V[k]<30 for k in ks))
print('W at 11/12,11/13',round(W[i-1],3),round(W[i],3))
print('sd V',statistics.pstdev(float(V[k]) for k in ks),'sd W',statistics.pstdev(W[k] for k in ks))
print('--- up-crosses of 30 / down-crosses of 70')
for a,b in zip(keys,keys[1:]):
    for th,up in ((30,True),(70,False)):
        if (up and V[a]<30<=V[b]) or ((not up) and V[a]>70>=V[b]):
            print(dates[b],'th',th,'V',round(float(V[a]),1),'->',round(float(V[b]),1),'enter',float(dc[b]),'exit',float(dc[b-N]))
