import json
from fractions import Fraction as F
from pathlib import Path
D=str(Path(__file__).resolve().parents[1]/'evidence')
k=json.load(open(D+'/tencent-588060.json'))['data']['sh588060']['day']
dates=[r[0] for r in k]; O=[F(r[1]) for r in k]; C=[F(r[2]) for r in k]; Hh=[F(r[3]) for r in k]; L=[F(r[4]) for r in k]
i0=dates.index('2026-08-07'); WIN=range(i0,len(k))
def cutler(n,src=C):
    out=[None]*len(src)
    for i in range(n,len(src)):
        d=[src[j]-src[j-1] for j in range(i-n+1,i+1)]
        s=sum(abs(x) for x in d)
        out[i]=None if s==0 else 100*sum(max(x,0) for x in d)/s
    return out
def sma_rsi(n,m=1,src=C):
    # THS SMA(X,N,M): Y=(M*X+(N-M)*Y')/N, first value = X
    out=[None]*len(src); a=b=None
    for i in range(1,len(src)):
        d=src[i]-src[i-1]; up=max(d,0); ab=abs(d)
        a=up if a is None else (m*up+(n-m)*a)/n
        b=ab if b is None else (m*ab+(n-m)*b)/n
        out[i]=None if b==0 else 100*a/b
    return out
def ema_rsi(n,src=C):
    out=[None]*len(src); a=b=None
    for i in range(1,len(src)):
        d=src[i]-src[i-1]; up=max(d,0); ab=abs(d)
        a=up if a is None else (2*up+(n-1)*a)/(n+1)
        b=ab if b is None else (2*ab+(n-1)*b)/(n+1)
        out[i]=None if b==0 else 100*a/b
    return out
