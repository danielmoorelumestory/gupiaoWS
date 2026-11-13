"""只读执行原 protocol.py 并独立核对；不修改原脚本、不搜索参数。"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import numpy as np
import pandas as pd

buf = StringIO()
with redirect_stdout(buf):
    ns = runpy.run_path('research/protocol.py')
saved = Path('research/protocol_output.txt').read_text()
print('reproduction_equals_saved', buf.getvalue() == saved)
print(buf.getvalue())
d, m, p = ns['d'], ns['m'], ns['p']
for file,col in [('tr_H00300.csv','close'),('tr_H00905.csv','close'),('cbond_treasury_7-10Y_wealth.csv','value'),('cn10y.csv','cn10y')]:
    t = pd.read_csv('data/'+file,parse_dates=['date']).set_index('date')
    print('data',file,len(t),t.index.min(),t.index.max(),'duplicates',t.index.duplicated().sum(),'sorted',t.index.is_monotonic_increasing,'missing',t[col].isna().sum())
    ix=d.index[(d.index>=t.index.min()) & (d.index<=t.index.max())]
    print('missing_equity_calendar_dates_in_overlap',len(ix.difference(t.index)))
print('last month observation',m.index[-1],'E last row',p.tail(1).to_string())

q=m.dropna(subset=['Y','r250','z'])
for year in sorted(set(q.index.year)):
    tr=q[q.mature < pd.Timestamp(year,1,1)]
    te=q[q.index.year==year]
    if len(tr)>=60 and len(te):
        assert tr.mature.max()<pd.Timestamp(year,1,1)<=te.index.min()
        print('fit_year',year,'ntrain',len(tr),'last_feature',tr.index.max().date(),'last_mature',tr.mature.max().date(),'ntest',len(te))

for file in ['csi300_pe_lg.csv','pe_lg_sh000905.csv']:
    pe=pd.read_csv('data/'+file,parse_dates=['日期']).set_index('日期')
    print('PE',file,'tail',pe.tail(3).to_string(),'noncalendar',list(pe.index.difference(d.index)))
    for months in [36,18]:
        ps=d.index.searchsorted(pe.index[:-1])
        print('monthly window trading-day span',months,pd.Series(ps[months-1:]-ps[:len(ps)-months+1]).describe().to_dict())

rows=[]
w_sig=ns['w_sig']
for i in range(len(w_sig)-1):
    t0,t1=w_sig.index[i:i+2]
    if t1 not in p.index: continue
    a=d.index.get_loc(t0)+1
    end=d.index.get_loc(t1)+1
    full=end<len(d)
    end=min(end,len(d)-1)
    S=d.tr.iloc[end]/d.tr.iloc[a]-1
    B=d.bw.iloc[end]/d.bw.iloc[a]-1
    assert np.isclose(p.loc[t1,'dyn'],p.loc[t1,'w']*S+(1-p.loc[t1,'w'])*B)
    rows.append((t1,t0,d.index[a],d.index[end],end-a,full,S,B))
audit=pd.DataFrame(rows,columns=['date','signal','entry','exit','days','full','S','B']).set_index('date').join(p)
print('E execution tail\n',audit[['signal','entry','exit','days','full']].tail(3).to_string())
full=audit[audit.full]
print('E full intervals',len(full),'original',len(p),'mean gross edge',(full.dyn-full.fix).mean()*100)
print('E gross monthly return stdev',full.dyn.std()*np.sqrt(12)*100,full.fix.std()*np.sqrt(12)*100)
for c in ['dyn','fix','half','stock']:
    r=full[c]
    eq=pd.Series(np.r_[1,(1+r).cumprod().values])
    print('E full monthly',c,'ann',(eq.iloc[-1]**(12/len(r))-1)*100,'monthly_dd',(eq/eq.cummax()-1).min()*100)
    daily_eq=[1.]
    for _,r0 in full.iterrows():
        seg=d.loc[r0.entry:r0.exit]
        w=r0.w if c=='dyn' else r0.wf if c=='fix' else .5 if c=='half' else 1.
        curve=w*seg.tr/seg.tr.iloc[0]+(1-w)*seg.bw/seg.bw.iloc[0]
        daily_eq.extend((daily_eq[-1]*curve.iloc[1:]).tolist())
    eqd=pd.Series(daily_eq)
    print('E full daily_dd',c,(eqd/eqd.cummax()-1).min()*100)

prev=full.shift(1)
drift=prev.w*(1+prev.S)/(1+prev.dyn)
driftf=prev.wf*(1+prev.S)/(1+prev.fix)
turn=(full.w-drift).abs()
turnf=(full.wf-driftf).abs()
sel=turn.notna()&turnf.notna()
print('turnover mean excluding initial','reported',full.turn[sel].mean(),'drift_adjusted_dynamic',turn[sel].mean(),'drift_adjusted_fixed',turnf[sel].mean())
print('10bp stock-leg-only gross-cost approx mean edge',((full.dyn-full.fix)[sel]-.001*(turn-turnf)[sel]).mean()*100)
print('10bp both-legs gross-cost approx mean edge',((full.dyn-full.fix)[sel]-.002*(turn-turnf)[sel]).mean()*100)

# 只定位既有 A 的误差来源，不拟合新模型，也不据此选分段策略。
err=ns['oos'](m,'Y',[[],['r250'],['r250','z']])
auditA=m.loc[err.index,['z','Y']].join(err.rename(columns={0:'e0',1:'e1',2:'e2'}))
auditA['loss_diff']=auditA.e1**2-auditA.e2**2
print('A largest negative error differences\n',auditA.nsmallest(6,'loss_diff').to_string())
print('A sign decomposition\n',auditA.groupby(auditA.z>0).loss_diff.agg(['count','mean','sum']).to_string())
print('E same calendar as A gross edge', (p.loc[p.index.intersection(err.index)].dyn-p.loc[p.index.intersection(err.index)].fix).mean()*100,'n',len(p.index.intersection(err.index)))

tr_daily=ns['load']('data/tr_H00905.csv','close')
px_daily=pd.read_csv('data/index_sh000905.csv',parse_dates=['date']).set_index('date')
print('price_calendar_dates_absent_spread',list(px_daily.loc[d.index.min():].index.difference(d.index)))
print('totalreturn_extra_vs_price',list(tr_daily.loc[px_daily.index.min():].index.difference(px_daily.index)))
for yr in [2013,2015,2016]:
    train=q[q.mature<pd.Timestamp(yr,1,1)]
    X=np.column_stack([np.ones(len(train)),train.r250,train.z])
    beta=np.linalg.lstsq(X,train.Y,rcond=None)[0]
    print('A fitted coeff',yr,'intercept,r250,z',beta)
