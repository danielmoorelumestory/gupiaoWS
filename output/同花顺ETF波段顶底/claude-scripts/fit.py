from img import *
from ind import *
import statistics as st, math, json
def obs_mid():
    out=[]
    for i in range(64):
        x=28+18*i
        ys=darkrows(x,1972,2365)
        out.append(y2v(st.median(ys)) if ys else None)
    return out
OBS=obs_mid()
def score(series):
    e=[]
    for i in range(64):
        a,b=series[i0+i],series[i0+i+1]
        if a is None or b is None or OBS[i] is None: return None
        e.append(OBS[i]-float((a+b)/2))
    return math.sqrt(sum(x*x for x in e)/len(e)), max(map(abs,e)), e
