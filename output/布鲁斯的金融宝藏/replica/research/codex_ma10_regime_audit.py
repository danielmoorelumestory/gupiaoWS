"""Independent cash/unit matching and regime features; frozen input CSVs.
Run in replica: python research/codex_ma10_regime_audit.py
Original definitions loaded only for post-hoc equality checks, no original trials.
Random nulls: original daily Bernoulli (300); fixed-count whole above-MA
runs with first-day entry, matched empirical delay, and strict-crossing policy
(2000 each). Nulls use test counts for diagnostic matching, not deployable rules.
"""
from pathlib import Path
import contextlib,io,os,json,hashlib
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parents[1];O=P/'research'
N=dict(zip(['sh000300','sh000001','sh000905','sh000016','sh000852','sz399006','sh000688'],['沪深300','上证指数','中证500','上证50','中证1000','创业板指','科创50']))
D={k:pd.read_csv(P/f'data/index_{k}_ohlc.csv',parse_dates=['date']).set_index('date') for k in N}
def rma(x,seed=False):
 x=np.asarray(x,float);y=np.full(len(x),np.nan);v=np.flatnonzero(np.isfinite(x))
 if not len(v):return y
 b=v[0]+(13 if seed else 0)
 if b>=len(x):return y
 y[b]=np.mean(x[b-13:b+1]) if seed else x[b]
 for i in range(b+1,len(x)):y[i]=y[i-1]+(x[i]-y[i-1])/14 if np.isfinite(x[i]) else y[i-1]
 return y
def features(d,seed=False):
 c=d.close;f=pd.DataFrame(index=d.index);f['above']=c>c.rolling(10).mean();f['ser']=c.diff(60)/c.diff().abs().rolling(60).sum()
 m=c.rolling(200).mean();f['trend200']=(c>m)&(m.diff(20)>0)
 cross=f.above.ne(f.above.shift()).astype(float);cross.iloc[0]=np.nan;f['cross60']=cross.rolling(60).sum()
 prev=c.shift();tr=np.fmax.reduce([np.asarray(d.high-d.low),np.asarray(abs(d.high-prev)),np.asarray(abs(d.low-prev))]);u=d.high.diff().to_numpy();v=-d.low.diff().to_numpy()
 plus=np.where((u>v)&(u>0),u,0.);minus=np.where((v>u)&(v>0),v,0.)
 if seed:tr[0]=plus[0]=minus[0]=np.nan
 with np.errstate(divide='ignore',invalid='ignore'):
  f['pdi']=100*rma(plus,seed)/rma(tr,seed);f['ndi']=100*rma(minus,seed)/rma(tr,seed);f['adx']=rma(100*abs(f.pdi-f.ndi)/(f.pdi+f.ndi),seed)
 f['ret60']=c/c.shift(60)-1;f['width60']=c.rolling(60).max()/c.rolling(60).min()-1
 return f
F={k:features(d) for k,d in D.items()};train=pd.concat([F[k].loc['2006':'2015'] for k in list(N)[:3]]);TH={k:float(train[k].median()) for k in ['ser','cross60','width60']}
def gates(f):return {'base':pd.Series(True,index=f.index),'F1':f.ser>=TH['ser'],'F2':f.trend200,'F3':f.cross60<=TH['cross60'],'F4':(f.adx>=25)&(f.pdi>f.ndi),'F5':f.width60>=TH['width60']}
def state(a,g,strict=False):
 a=np.asarray(a);g=np.asarray(g);s=np.zeros(len(a),bool);on=False
 for i in range(1,len(a)):
  if not a[i]:on=False
  elif not on and g[i] and (not strict or not a[i-1]):on=True
  s[i]=on
 return s
def ledger(d,s,start,end=None,cost=.001):
 ids=np.flatnonzero((d.index>=pd.Timestamp(start))&(d.index<=pd.Timestamp(end or d.index[-1])));cash=1.;units=0.;entry=None;rows=[];tr=[];orders=0
 for i in ids:
  assert i>0
  o=d.open.iloc[i];c=d.close.iloc[i];want=bool(s[i-1])
  if want and units==0:entry=(i,cash);units=cash*(1-cost)/o;cash=0.;orders+=1
  elif not want and units:cash=units*o*(1-cost);units=0.;orders+=1;tr.append((entry[0],i,cash/entry[1]-1));entry=None
  rows.append((d.index[i],cash+units*c,bool(units)))
 n=pd.DataFrame(rows,columns=['date','nav','held']).set_index('date');t=pd.DataFrame(tr,columns=['buy_i','sell_i','return']);years=(n.index[-1]-n.index[0]).days/365.25
 m=dict(nav=n.nav.iloc[-1],cagr=100*(n.nav.iloc[-1]**(1/years)-1),mdd=100*(n.nav/np.maximum(1,n.nav.cummax())-1).min(),trades=len(t),orders=orders,exposure=100*n.held.mean())
 if entry is None and len(t):assert abs(np.prod(1+t['return'])-m['nav'])<1e-10
 return m,n,t
# Gate failure after entry does not sell; a later passing day may enter.
assert state([0,1,1,1,0],[0,0,1,0,1]).tolist()==[False,False,True,True,False]
assert state([0,1,1,1,0],[0,0,1,0,1],True).tolist()==[False,False,False,False,False]
summary=[];trades=[];paths={}
for code,d in D.items():
 start='2020-07-23' if code=='sh000688' else '2016-01-01'
 for seg,a,b in [('test',start,None),('post2020',max(start,'2020-01-01'),None),('2020_2025',max(start,'2020-01-01'),'2025-12-31'),('2026','2026-01-01',None)]:
  for name,g in gates(F[code]).items():
   for cost in (0.,.001):
    m,n,t=ledger(d,state(F[code].above,g),a,b,cost);summary.append(dict(code=code,name=N[code],segment=seg,start=a,filter=name,cost_bp=cost*1e4,**m))
    if seg=='test' and cost==.001 and len(t):trades.append(t.assign(code=code,filter=name))
  x=d.loc[a:b];h=x.close/x.open.iloc[0];years=(x.index[-1]-x.index[0]).days/365.25;summary.append(dict(code=code,name=N[code],segment=seg,start=a,filter='hold',cost_bp=0,cagr=100*(h.iloc[-1]**(1/years)-1),mdd=100*(h/np.maximum(1,h.cummax())-1).min()))
 paths[code]=d.close.pct_change().loc[start:]
# Post-hoc verification: original functions only, excluding its experiments.
original=(O/'ma10_regime.py').read_text();prefix=original.split('# ---------------------------------------------------------------- 一、诊断')[0];ns={};cwd=os.getcwd()
try:
 os.chdir(P)
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(prefix,'original_definitions','exec'),ns)
finally:os.chdir(cwd)
checks=[]
for k in TH:assert abs(TH[k]-ns['TH'][k])<1e-12
for code,d in D.items():
 f=F[code];old=ns['F'][code];errors={k:float(np.nanmax(abs(f[k].astype(float)-old[k].astype(float)))) for k in f};assert max(errors.values())<1e-9,(code,errors)
 start='2020-07-23' if code=='sh000688' else '2016-01-01'
 for name,g in gates(f).items():
  st=state(f.above,g);ost=ns['state'](old,g);assert np.array_equal(st,ost);m,n,t=ledger(d,st,start);on,ot=ns['backtest'](d,ost,start);error=float(abs(n.nav-on).max());assert error<1e-11
  assert len(t)==len(ot)
  if len(t):assert np.max(abs(t['return'].to_numpy()-[x[1] for x in ot]))<1e-11
  checks.append(dict(code=code,filter=name,nav_error=error))
 sf=features(d,True);mask=f.index>=pd.Timestamp(start);checks.append(dict(code=code,seeded_adx_error=float(abs(f.adx[mask]-sf.adx[mask]).max()),F4_changed=int(((gates(f)['F4']!=gates(sf)['F4'])&mask).sum())))
 short=features(d.iloc[:-100])
 for col in f:assert np.allclose(short[col].astype(float),f[col].iloc[:-100].astype(float),equal_nan=True)
# Regime attribution is on the signal close, not subsequent return paths.
diags=[]
for group,codes,a,b in [('train',list(N)[:3],'2006-01-01','2015-12-31'),('test',list(N),'2016-01-01',None)]:
 rr=[]
 for code in codes:
  start=max(a,{'sh000852':'2015-07-01','sz399006':'2011-06-01','sh000688':'2020-07-23'}.get(code,a));f=F[code];_,_,t=ledger(D[code],state(f.above,np.ones(len(f),bool)),start,b)
  for bi,si,r in t.itertuples(index=False,name=None):
   z=f.iloc[bi-1];label='上涨' if z.ret60>.1 else '下跌' if z.ret60<-.1 else '窄幅震荡' if z.width60<TH['width60'] else '宽幅震荡';rr.append(dict(regime=label,ret=r,code=code))
 for label,g in pd.DataFrame(rr).groupby('regime'):diags.append(dict(group=group,regime=label,n=len(g),mean=100*g.ret.mean(),median=100*g.ret.median(),win=100*(g.ret>0).mean(),arithmetic_sum=100*g.ret.sum(),log_sum=100*np.log1p(g.ret).sum()))
# Fast independent episode matcher for Monte Carlo. One trade per uninterrupted
# above-MA run; actual filter may enter on ANY later passing day in the run.
def episodes(d,a,start):
 a=np.asarray(a,bool);first=np.searchsorted(d.index,pd.Timestamp(start));runs=[];i=0
 while i<len(a):
  if not a[i]:i+=1;continue
  b=i
  while i<len(a) and a[i]:i+=1
  e=i
  if e>first-1 and b<len(a)-1:
   cand=np.arange(b,min(e,len(a)-1));buy=np.maximum(cand+1,first);exit_i=e+1;closed=exit_i<len(d);terminal=d.open.iloc[exit_i] if closed else d.close.iloc[-1];gross=terminal/d.open.iloc[buy].to_numpy();runs.append((cand,gross,closed))
 return runs
def factors(runs,g,strict=False):
 logs=[];delay=[];g=np.asarray(g)
 for cand,gross,closed in runs:
  take=np.flatnonzero(g[cand]);take=take[take==0] if strict else take
  if len(take):j=take[0];logs.append(np.log(gross[j])+(1+int(closed))*np.log(.999));delay.append(j)
 return sum(logs),len(logs),delay
rng=np.random.default_rng(20261111);fair=np.random.default_rng(1447);randomrows=[]
for code,d in D.items():
 f=F[code];start='2020-07-23' if code=='sh000688' else '2016-01-01';runs=episodes(d,f.above,start);first=np.searchsorted(d.index,pd.Timestamp(start));yrs=(d.index[-1]-d.index[first]).days/365.25
 for name,g in list(gates(f).items())[1:]:
  sig=f.above&~f.above.shift(fill_value=False);p=float(g[sig&(f.index>=pd.Timestamp(start))].mean());lr,K,delays=factors(runs,g);ls,Ks,_=factors(runs,g,True);real=100*np.expm1(lr/yrs);strictreal=100*np.expm1(ls/yrs)
  expected=next(x['cagr'] for x in summary if x['code']==code and x['segment']=='test' and x['filter']==name and x['cost_bp']==10);assert abs(real-expected)<1e-9,(code,name,real,expected)
  legacy=[];counts=[]
  for _ in range(300):l,k,_=factors(runs,rng.random(len(f))<p);legacy.append(100*np.expm1(l/yrs));counts.append(k)
  fixed=[];matched=[];strict=[]
  # Precompute log factors for each episode and possible empirical delay.
  firstlogs=np.array([np.log(gross[0])+(1+int(closed))*np.log(.999) for cand,gross,closed in runs])
  for _ in range(2000):
   chosen=fair.choice(len(runs),K,replace=False);schosen=fair.choice(len(runs),Ks,replace=False);ld=0.
   for z,offset in zip(chosen,fair.choice(delays,K)):
    cand,gross,closed=runs[z];ld+=np.log(gross[min(int(offset),len(cand)-1)])+(1+int(closed))*np.log(.999)
   fixed.append(100*np.expm1(firstlogs[chosen].sum()/yrs));matched.append(100*np.expm1(ld/yrs));strict.append(100*np.expm1(firstlogs[schosen].sum()/yrs))
  randomrows.append(dict(code=code,name=N[code],filter=name,cross_pass=p,episodes=len(runs),real_entries=K,strict_entries=Ks,real_cagr=real,strict_cagr=strictreal,delayed_entries=sum(x>0 for x in delays),legacy_entries_median=np.median(counts),legacy_q=100*np.mean(np.array(legacy)<real),legacy_median=np.median(legacy),fixedK_q=100*np.mean(np.array(fixed)<real),fixedK_median=np.median(fixed),matched_delay_q=100*np.mean(np.array(matched)<real),strict_q=100*np.mean(np.array(strict)<strictreal),strict_random_median=np.median(strict)))
cor=pd.DataFrame(paths).corr();cor.to_csv(O/'codex_ma10_regime_correlations.csv')
pd.DataFrame(summary).to_csv(O/'codex_ma10_regime_summary.csv',index=False);pd.DataFrame(randomrows).to_csv(O/'codex_ma10_regime_random.csv',index=False);pd.DataFrame(diags).to_csv(O/'codex_ma10_regime_regimes.csv',index=False);pd.concat(trades).to_csv(O/'codex_ma10_regime_trades.csv',index=False)
meta=dict(thresholds=TH,checks=checks,input_sha256={k:hashlib.sha256((P/f'data/index_{k}_ohlc.csv').read_bytes()).hexdigest() for k in N},original_sha256=hashlib.sha256(original.encode()).hexdigest(),random_reps=dict(legacy=300,fixedK=2000),mean_pair_correlation=float(cor.to_numpy()[np.triu_indices(7,1)].mean()))
(O/'codex_ma10_regime_diagnostics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print('Thresholds',TH);print(pd.DataFrame(randomrows).to_string(index=False));print('Independent feature, daily NAV, trades, and prefix checks passed.')
