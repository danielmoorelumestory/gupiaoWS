"""独立复核既有口径；不搜索新策略参数。从 replica 目录执行。"""
from pathlib import Path
from math import comb
import numpy as np
import pandas as pd

d = pd.read_csv('data/equity_bond_spread.csv', parse_dates=['date']).set_index('date')
b = pd.read_csv('data/cn10y.csv', parse_dates=['date']).set_index('date').cn10y
d['bond'] = b.reindex(d.index).ffill()
d['ey'] = d.spread + d.bond
p = d['index']
z = lambda x: (x-x.rolling(750, min_periods=375).mean())/x.rolling(750, min_periods=375).std(ddof=0)
zs = z(d.spread)
def events(flag):
    hits = np.flatnonzero(flag.to_numpy())
    return hits[np.r_[True, np.diff(hits)>=20]] if len(hits) else hits
up, down = events(zs>=2), events(zs<=-2)
print('rows/start/end/duplicates/sorted', len(d), d.index.min(), d.index.max(), d.index.duplicated().sum(), d.index.is_monotonic_increasing)
print('warmup first', zs.first_valid_index(), 'valid', zs.notna().sum(), 'bond missing', d.bond.isna().sum())
for name, ix in [('upper',up), ('lower',down), ('ey_upper', events(z(d.ey)>=2))]:
    out = pd.DataFrame(index=d.index[ix])
    for h in (120,250):
        r=(p.shift(-h)/p-1)
        out[str(h)] = r.iloc[ix]*100
        valid=r[zs.notna()].dropna()
        rr=r.iloc[ix].dropna()
        print(name,h,'n',len(rr),'mean',rr.mean()*100,'median',rr.median()*100,'win',(rr>0).mean()*100,'base_n',len(valid),'base_mean',valid.mean()*100,'base_win',(valid>0).mean()*100)
        edges=[(str(d.index[a].date()),str(d.index[c].date())) for a,c in zip(ix[:-1],ix[1:]) if c-a<h]
        print('adjacent overlap',h,edges)
    print(out.round(4).to_string())
dv=d[['spread','ey','bond']].diff(250).dropna()
v=dv.var(); cov=dv.ey.cov(dv.bond)
print('variance', v.to_dict(),'cov_ey_bond',cov,'identity',v.ey+v.bond-2*cov)
print('ey/total',v.ey/v.spread,'ey/(ey+bond)',v.ey/(v.ey+v.bond),'symmetric_covariance_ey_share',(v.ey-cov)/v.spread)
print('z correlation',zs.corr(z(d.ey)))
print('all-day bins audit')
g=pd.cut(zs,[-np.inf,-2,-1,0,1,1.5,2,np.inf])
print(pd.DataFrame({str(h):(p.shift(-h)/p-1).groupby(g,observed=True).mean()*100 for h in (120,250)}).round(3).to_string())
pe=pd.read_csv('data/csi300_pe_lg.csv',parse_dates=['日期']).set_index('日期')
match=pe.join(d[['ey','index']],how='inner')
print('monthly matches',len(match),'index_max_diff', (match['指数']-match['index']).abs().max())
for c in ['滚动市盈率','静态市盈率']:
    err=(100/match[c]-match.ey).abs()
    print(c,'ey_abs_err_median',err.median(),'max',err.max(),'last',err.iloc[-1])
print('naive independent Bernoulli p>=7/9 under p=.5',sum(comb(9,k) for k in range(7,10))/2**9)
