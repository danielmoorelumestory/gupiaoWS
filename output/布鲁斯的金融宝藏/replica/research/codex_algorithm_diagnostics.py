"""只检查息差自身的AR(1)估计与长度换算，不产生或读取未来收益。"""
import numpy as np
import pandas as pd

s = pd.read_csv('data/equity_bond_spread.csv', usecols=['date','spread'], parse_dates=['date']).set_index('date').spread
cal = pd.read_csv('data/index_sh000300.csv', usecols=['date'], parse_dates=['date']).date
s = s.reindex(pd.DatetimeIndex(cal)).loc['2005-04-08':]
print('No equity or bond returns loaded; no new-score return comparisons performed.')
print('year n_pairs phi half_life innovation_variance')
for year in range(2011,2027):
    t = s[s.index < pd.Timestamp(year,1,1)]
    pairs = pd.concat([t.shift(1).rename('a'),t.rename('b')],axis=1).dropna()
    a,b=pairs.a.to_numpy(),pairs.b.to_numpy()
    phi=np.dot(a-a.mean(),b-b.mean())/np.dot(a-a.mean(),a-a.mean())
    c=b.mean()-phi*a.mean()
    q=np.mean((b-c-phi*a)**2)
    h=-np.log(2)/np.log(phi) if 0<phi<1 else np.nan
    print(year,len(pairs),f'{phi:.9f}',f'{h:.3f}',f'{q:.9f}')
phi_equal=(750-1)/(750+1)
print('EW same infinite-history weight ESS as rectangular750:', 'phi',phi_equal,'half_life',-np.log(2)/np.log(phi_equal))

# 只验证推荐的有限指数加权矩递推是否等于直接按权重计算。
values=np.array([1.3,-.2,2.,1.,-.7])
phi=.9
W=0.; mean=0.; M2=0.
for j,x in enumerate(values):
    W=phi*W+1
    delta=x-mean
    mean=mean+delta/W
    M2=phi*M2+delta*(x-mean)
    weights=phi**np.arange(j,-1,-1)
    direct=np.average(values[:j+1],weights=weights)
    var=np.average((values[:j+1]-direct)**2,weights=weights)
    assert np.allclose([mean,M2/W],[direct,var])
print('weighted mean/variance recurrence matches direct finite-weight calculation')
