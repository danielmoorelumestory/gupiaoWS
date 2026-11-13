"""只检查输入指标与日期，不计算任何未来收益或策略净值。"""
import numpy as np
import pandas as pd

cal=pd.DatetimeIndex(pd.read_csv('data/index_sh000300.csv',usecols=['date'],parse_dates=['date']).date)
print('No future-return labels or strategy NAV calculated.')
for f,dc,cols in [
    ('below_net_asset_all.csv','date',['below_net_asset','total_company','below_net_asset_ratio']),
    ('margin_sh.csv','日期',['融资余额','融资买入额']),
    ('margin_sz.csv','日期',['融资余额','融资买入额']),
    ('csindex_000985.csv','日期',['成交金额'])]:
    d=pd.read_csv('data/'+f,parse_dates=[dc]).set_index(dc)
    ix=cal[(cal>=d.index.min())&(cal<=d.index.max())]
    missing=ix.difference(d.index)
    print('\nFILE',f,'rows',len(d),'start',d.index.min(),'end',d.index.max(),'duplicate_extras',d.index.duplicated().sum())
    print('missing',len(missing),'by_year',pd.Series(missing.year).value_counts().sort_index().to_dict())
    print('nulls',d[cols].isna().sum().to_dict())
    print('nonpositive', (d[cols]<=0).sum().to_dict())
    if f.startswith('below'):
        du=d[d.index.duplicated(keep=False)]
        print('duplicate rows\n',du.to_string())
        print('max ratio rounding error',(d.below_net_asset/d.total_company-d.below_net_asset_ratio).abs().max())
        print('invalid counts',((d.below_net_asset<0)|(d.total_company<=0)|(d.below_net_asset>d.total_company)).sum())
    if f.startswith('margin'):
        flag=pd.Series(~ix.isin(d.index),index=ix)
        groups=flag.ne(flag.shift()).cumsum()
        runs=[(g.index[0].date(),g.index[-1].date(),len(g)) for _,g in flag.groupby(groups) if g.iloc[0]]
        print('largest gaps',sorted(runs,key=lambda x:x[2],reverse=True)[:5])
        print('zero balance dates',d.index[d['融资余额']==0].tolist())
    if f.startswith('csindex'):
        print('dates outside equity calendar',d.index.difference(cal).tolist())
        print('nonpositive turnover on trading dates',d.reindex(ix).index[d.reindex(ix)['成交金额']<=0].tolist())
