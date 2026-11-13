from pathlib import Path
from PIL import Image
from ind import *
import statistics as st, math
im=Image.open(str(Path(__file__).resolve().parents[1]/'evidence/screenshots'/'588060-long-20261113.png')).convert('RGB'); px=im.load()
def wcenter(test,y0,y1,x=600):
    ws=[(y,1) for y in range(y0,y1) if test(px[x,y])]
    return sum(y for y,_ in ws)/len(ws)
Y70=wcenter(lambda p:p[1]>120 and p[0]<120 and p[2]<120,2080,2100)
Y30=wcenter(lambda p:p[0]>180 and p[1]<90 and p[2]<90,2235,2255)
def y2v(y): return 30+(Y30-y)*40/(Y30-Y70)
j0=dates.index('2025-07-10'); N=len(C)-j0
def dark(p): return max(p)<90
OBSX={}
for x in range(10,1190):
    ys=[y for y in range(1975,2370) if dark(px[x,y])]
    if x<110: ys=[y for y in ys if not 2140<y<2185]
    if ys: OBSX[x]=(y2v(st.median(ys)),y2v(min(ys)),y2v(max(ys)))
def interp(series,a,b,x):
    t=(x-a)/b
    i=math.floor(t)
    if i<0 or i>=N-1: return None
    f=t-i; v0=float(series[j0+i]); v1=float(series[j0+i+1]); return v0+(v1-v0)*f
def errs(series,a,b):
    e=[]
    for x,(m,top,bot) in OBSX.items():
        p=interp(series,a,b,x)
        if p is not None: e.append(m-p)
    return e
