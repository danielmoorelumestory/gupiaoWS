"""只读复现three_indicators.py并独立核算；不搜索任何新策略。"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import hashlib
import runpy
import numpy as np
import pandas as pd

files=[Path('research/three_indicators.py'),Path('research/patch_margin.py')]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
out=StringIO()
with redirect_stdout(out): ns=runpy.run_path('research/three_indicators.py')
print('reproduced_output_exactly',out.getvalue()==Path('research/three_indicators_output.txt').read_text())
print(out.getvalue())
cal,tr,bw=ns['cal'],ns['tr'],ns['bw']
seg,idx,sig=ns['seg'],ns['idx'],ns['sig']
print('calendar end',cal[-1],'last full month-end',ns['me'][-1])
print('signal/entry/exit first',seg[0][0],cal[seg[0][1]],cal[seg[0][2]],'last',seg[-1][0],cal[seg[-1][1]],cal[seg[-1][2]])
print('one exit per month',not idx.to_period('M').duplicated().any(),'missing exit months',len(pd.period_range(idx[0],idx[-1],freq='M').difference(idx.to_period('M'))))

def ledger(target_fn, cost=.001, exact_fee=False):
    nav=1.; prior=None; rets=[]; daily=[1.]; trades=[]; fees=[]; dates=[]; weights=[]
    for i,(t0,a,b) in enumerate(seg):
        w=float(target_fn(i,t0))
        trade=1. if prior is None else 2*abs(w-prior)
        net=1-cost*trade
        if exact_fee and prior is not None:
            lo,hi=0.,1.
            for _ in range(60):
                mid=(lo+hi)/2
                f=mid+cost*(abs(w*mid-prior)+abs((1-w)*mid-(1-prior)))-1
                if f>0: hi=mid
                else: lo=mid
            net=(lo+hi)/2
        start=nav
        # 计入调仓时点的费用扣款点；之后用两资产持有金额独立计算。
        nav*=net
        daily.append(nav)
        stock=nav*w; bond=nav*(1-w)
        for j in range(a+1,b+1):
            vs=stock*tr.iloc[j]/tr.iloc[a]
            vb=bond*bw.iloc[j]/bw.iloc[a]
            nav=vs+vb
            daily.append(nav); dates.append(cal[j]); weights.append(vs/nav)
        rets.append(nav/start-1); prior=vs/nav
        trades.append(trade); fees.append(1-net)
    return np.array(rets),np.array(daily),np.array(trades),np.array(fees),np.array(weights)

targets={'dyn':lambda i,t:float(sig[t]),'fix':lambda i,t:float(ns['wf'](t))}
for name,fn in targets.items():
    a=ledger(fn); original=ns['simulate'](fn,.001)
    print('ledger',name,'return max abs delta',np.max(np.abs(a[0]-original[0])),'weight max abs delta',np.max(np.abs(a[4]-original[2])))
    assert np.allclose(a[0],original[0],atol=1e-14)
    print('fee timing drawdown',name,(a[1]/np.maximum.accumulate(a[1])-1).min())
    print('turnover correct excl init',name,np.mean(a[2][1:]/2),'reported',original[3],'fee normalized sum',a[3].sum())
    ex=ledger(fn,exact_fee=True)
    print('exact fee diagnostic',name,'annual',((1+ex[0]).prod()**(12/len(seg))-1)*100,'approx annual',((1+a[0]).prod()**(12/len(seg))-1)*100)

lab=ns['lab']
def predictive(X,sign,name):
    df=lab.assign(X=X.reindex(lab.index)).dropna(subset=['Y','r250','X'])
    rows=[]; param=[]
    for year in sorted(set(df.index.year)):
        cut=pd.Timestamp(year,1,1)
        a=df[df.mature<cut]; b=df[df.index.year==year]
        if len(a)<60 or b.empty: continue
        assert a.mature.max()<cut<=b.index.min()
        Z=np.column_stack([np.ones(len(a)),a.r250])
        beta0=np.linalg.lstsq(Z,a.Y,rcond=None)[0]
        # Frisch-Waugh-Lovell独立求新增项，以核对原三列OLS和量纲。
        rx=a.X.to_numpy()-Z@np.linalg.lstsq(Z,a.X,rcond=None)[0]
        ry=a.Y.to_numpy()-Z@beta0
        gamma=np.dot(rx,ry)/np.dot(rx,rx)
        used=gamma if gamma*sign>=0 else 0.
        beta=np.linalg.lstsq(Z,a.Y-used*a.X,rcond=None)[0]
        design=np.column_stack([Z,a.X])
        assert np.linalg.matrix_rank(design)==3
        raw_beta=np.linalg.lstsq(design,a.Y,rcond=None)[0]
        assert np.allclose(gamma,raw_beta[-1],atol=1e-10)
        if name=='PB':
            ppbeta=np.linalg.lstsq(np.column_stack([Z,100*a.X]),a.Y,rcond=None)[0]
            assert np.allclose(design@raw_beta,np.column_stack([Z,100*a.X])@ppbeta,atol=1e-12)
        param.append((year,len(a),gamma,used,a.X.mean(),a.X.min(),a.X.max(),b.X.mean(),np.sum((b.X<a.X.min())|(b.X>a.X.max()))))
        for t,r in b.iterrows():
            pred0=beta0@[1,r.r250]; pred=beta@[1,r.r250]+used*r.X
            rows.append((t,r.Y,r.X,pred0,pred,(r.Y-pred0)**2-(r.Y-pred)**2))
    z=pd.DataFrame(rows,columns=['date','Y','X','pred0','pred','d']).set_index('date')
    print('predictive independent',name,'n',len(z),'MSE0',np.mean((z.Y-z.pred0)**2)*1e4,'MSE1',np.mean((z.Y-z.pred)**2)*1e4,'gain',z.d.mean()*1e4)
    print('parameters',name,'\n',pd.DataFrame(param,columns=['year','ntrain','unconstrained','used','train_mean','train_min','train_max','test_mean','outside_train_range']).to_string(index=False))
    print('largest deterioration',name,'\n',z.nsmallest(6,'d').to_string())
    return z

pb=predictive(ns['XB'],1,'PB')
fin=predictive(ns['XF'],-1,'financing')
for key in ['XB','XF']:
    X=ns[key]
    raw=ns['Bd'] if key=='XB' else ns['XF_d']
    expected=pd.Series({t:raw.get(cal[cal.get_loc(t)-1],np.nan) for t in X.index})
    assert np.allclose(X.to_numpy(),expected.to_numpy(),equal_nan=True)
    print('previous-trading-day mapping verified',key)

print('finance patch counts',len(ns['pz']),len(ns['ps']),'check_bool',ns['pz']['核对用'].dtype)
print('finance missing through actual patched end',ns['L'].loc['2010-03-31':'2026-11-09'].isna().sum())
print('repaired zero date sz yuan',ns['sz'].loc['2024-08-08'])
print('SZ check largest relative error',max(abs(ns['sz'][t]/v-1) for t,v in ns['chk'].items()))
L=ns['sh'].reindex(cal)+ns['sz'].reindex(cal)
amt=pd.read_csv('data/csindex_000985.csv',parse_dates=['日期']).set_index('日期')['成交金额'].reindex(cal)*1e8
f=np.log(L/amt.rolling(20,min_periods=20).mean())
assert np.allclose(f,ns['XF_d'],equal_nan=True)
print('finance scalar identity checked L yuan / A20 yuan')
used_u=pd.DatetimeIndex([cal[cal.get_loc(t)-1] for t in ns['XF'].index])
print('SZ patched rows used as monthly observations',len(ns['add'].index.intersection(used_u)))
print('full-rank designs and PB fraction-versus-percent prediction invariance checked')
print('global P',ns['P'])
for p in files: assert hashlib.sha256(p.read_bytes()).hexdigest()==before[str(p)]
print('original scripts hashes unchanged',before)
