"""Independent MACD audit. Run: python research/codex_ma10_macd_audit.py
Manual recursive EMA and event-date matching; independent cash/units ledger.
Original definitions are loaded only AFTER independent summaries, for equality
checks. Original scripts are never edited; exec namespace cost behavior checked.
Random tests: (i) prune MA10 trades to MACD's count, (ii) rotate A's holdings
within MACD-positive episodes, preserving entry count and exposure exactly.
Random tests are retrospective nulls, not deployable trading strategies.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import os,io,contextlib,json,hashlib
P=Path(__file__).resolve().parents[1];O=P/'research'
N=dict(zip(['sh000300','sh000001','sh000016','sh000905','sh000852','sz399006','sh000688'],['沪深300','上证指数','上证50','中证500','中证1000','创业板指','科创50']))
D={k:pd.read_csv(P/f'data/index_{k}_ohlc.csv',parse_dates=['date']).set_index('date') for k in N}
START={'sh000852':'2015-07-01','sz399006':'2011-06-01','sh000688':'2020-07-23'}
def ema(x,n,seed='first'):
 x=np.asarray(x,float);y=np.full(len(x),np.nan);v=np.flatnonzero(np.isfinite(x))
 if not len(v):return y
 b=v[0]+(n-1 if seed=='sma' else 0)
 if b>=len(x):return y
 y[b]=x[b-n+1:b+1].mean() if seed=='sma' else x[b]
 alpha=2/(n+1)
 for i in range(b+1,len(x)):y[i]=y[i-1]+alpha*(x[i]-y[i-1])
 return y
def event_states(above,pos,window=5):
 a=np.asarray(above,bool);p=np.asarray(pos,bool);A=a&p;B=np.zeros(len(a),bool);last_a=last_p=-100000
 for i in range(len(a)):
  if a[i] and (i==0 or not a[i-1]):last_a=i
  if p[i] and (i==0 or not p[i-1]):last_p=i
  B[i]=A[i] and ((i>0 and B[i-1]) or (i-last_a<window and i-last_p<window))
 return A,B

def rules(d,seed='first'):
 c=d.close.to_numpy();dif=ema(c,12,seed)-ema(c,26,seed);dea=ema(dif,9,seed)
 above=(d.close>d.close.rolling(10).mean()).to_numpy();pos=dif>dea;A,B=event_states(above,pos)
 return dict(A=A,B=B,MA10=above,MACD=pos),dif,dea

def ledger(d,st,start,end=None,cost=.001,div=None):
 ids=np.flatnonzero((d.index>=pd.Timestamp(start))&(d.index<=pd.Timestamp(end or d.index[-1])));cash=1.;units=0.;entry=None;trades=[];rows=[];orders=0;div={} if div is None else div
 for i in ids:
  assert i>0
  date=d.index[i];o=float(d.open.iloc[i]);c=float(d.close.iloc[i]);want=bool(st[i-1]);entitlement=units*float(div.get(date,0.))
  if want and units==0:
   entry=(i,cash);units=cash*(1-cost)/o;cash=0.;orders+=1
  elif not want and units:
   cash=units*o*(1-cost)+entitlement;units=0.;orders+=1
   trades.append(dict(buy_i=entry[0],sell_i=i,ret=cash/entry[1]-1,days=i-entry[0]));entry=None
  if units:units+=entitlement/c
  rows.append((date,cash+units*c,bool(units)))
 n=pd.DataFrame(rows,columns=['date','nav','held']).set_index('date');t=pd.DataFrame(trades);years=(n.index[-1]-n.index[0]).days/365.25
 m=dict(nav=n.nav.iloc[-1],cagr=100*(n.nav.iloc[-1]**(1/years)-1),mdd=100*(n.nav/np.maximum(1,n.nav.cummax())-1).min(),trades=len(t),entries=orders//2+int(entry is not None),orders=orders,win=100*(t.ret>0).mean() if len(t) else None,exposure=100*n.held.mean(),open_trade=entry is not None)
 if entry is None and len(t):assert abs(np.prod(1+t.ret)-m['nav'])<1e-10
 return m,n,t
# Explicit window tests: a gap of four days is inside rolling(5), five outside;
# same-day events qualify, and expiry never forces sale of an existing position.
a=np.zeros(12,bool);a[1:]=True;p=np.zeros(12,bool);p[5:]=True;A,B=event_states(a,p);assert B[5] and B[-1]
p[:]=False;p[6:]=True;A,B=event_states(a,p);assert A[6] and not B[6]
A,B=event_states([0,1,1,0],[0,1,1,1]);assert B.tolist()==[False,True,True,False]
R={k:rules(d)[0] for k,d in D.items()};summary=[];cache={};trade_rows=[]
for code,d in D.items():
 test='2020-07-23' if code=='sh000688' else '2016-01-01'
 periods=[('test',test,None),('all',START.get(code,'2006-01-04'),None),('2016_2019','2016-01-01','2019-12-31'),('2020_2025',max(test,'2020-01-01'),'2025-12-31'),('2026','2026-01-01',None)]
 for period,a,b in periods:
  if period=='2016_2019' and code=='sh000688':continue
  for label,st in {**R[code],'hold':np.ones(len(d),bool)}.items():
   for cost in ((0.,) if label=='hold' else (0.,.001)):
    m,n,t=ledger(d,st,a,b,cost);key=(code,period,label,cost);cache[key]=(m,n,t);summary.append(dict(code=code,name=N[code],period=period,start=a,end=str(n.index[-1].date()),rule=label,cost_bp=cost*10000,**m))
    if period in ('test','all') and len(t):trade_rows.append(t.assign(code=code,period=period,rule=label,cost_bp=cost*1e4))
# Only now load the audited definitions for direct comparison.
source=(O/'ma10_macd.py').read_text();prefix=source.split('for cost in (0.001, 0.0):')[0];cwd=os.getcwd();ns={}
try:
 os.chdir(P)
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(prefix,'original_macd_definitions','exec'),ns)
finally:os.chdir(cwd)
labelmap={'A':'10日线+MACD','B':'严格版(5日内)','MA10':'只用10日线','MACD':'只用MACD'};checks=[];warming=[]
assert ns['backtest'].__globals__ is ns
for code,d in D.items():
 ours,dif,dea=rules(d);od,oe=ns['macd'](d.close)
 assert np.max(abs(dif-od))<1e-9;assert np.max(abs(dea-oe))<1e-9
 oldrules=ns['rules'](d)
 for label,olabel in labelmap.items():assert np.array_equal(ours[label],oldrules[olabel]),(code,label)
 for period in ('test','all'):
  a=('2020-07-23' if code=='sh000688' else '2016-01-01') if period=='test' else START.get(code,'2006-01-04')
  for label,olabel in labelmap.items():
   for cost in (0.,.001):
    before=ns['COST'];on,ot=ns['run_cost'](d,oldrules[olabel],a,cost);assert ns['COST']==before
    m,n,t=cache[code,period,label,cost];error=float(abs(on-n.nav).max());assert error<1e-10;assert len(t)==len(ot)
    if len(t):assert np.max(abs(t.ret.to_numpy()-[z[1] for z in ot]))<1e-10
    om=ns['summary'](on,ot,d,a);assert abs(100*om[0]-m['cagr'])<1e-9;assert abs(100*om[1]-m['mdd'])<1e-9;assert abs(100*om[3]-m['win'])<1e-9
    checks.append(dict(code=code,period=period,rule=label,cost_bp=cost*1e4,nav_error=error,cagr_diff_pp=100*om[0]-m['cagr'],mdd_diff_pp=100*om[1]-m['mdd'],trade_diff=len(ot)-len(t),win_diff_pp=100*om[3]-m['win']))
 for period in ('test','all'):
  start=next(x['start'] for x in summary if x['code']==code and x['period']==period);first=np.searchsorted(d.index,pd.Timestamp(start));seeded=rules(d,'sma')[0]
  warming.append(dict(code=code,period=period,mode='sma_seed',warmup_bars=first,**{k:int(np.sum(seeded[k][first-1:]!=ours[k][first-1:])) for k in ours}))
  for bars in (60,120,250):
   cut=max(0,first-bars);short=rules(d.iloc[cut:])[0]
   warming.append(dict(code=code,period=period,mode='first_seed',warmup_bars=first-cut,**{k:int(np.sum(short[k][first-cut-1:]!=ours[k][first-1:])) for k in ours}))
 # No future-dependence: entire historical signals must match truncated input.
 pre=rules(d.iloc[:-100])[0]
 for k in ours:assert np.array_equal(pre[k],ours[k][:-100])
 # fee multiplicative identity for the price-only strategy.
 for label in ours:
  m0=cache[code,'test',label,0.][0];m1=cache[code,'test',label,.001][0]
  assert abs(m1['nav']/m0['nav']-.999**m1['orders'])<1e-10
# Same-entry count and same-exposure null for the MA10 contribution to MACD.
# Rotate A's mask only within existing MACD-positive signal blocks; retain
# number of true runs and (on the terminal block) ending held state.
rng=np.random.default_rng(20261113);randomrows=[];REPS=3000
for code,d in D.items():
 start='2020-07-23' if code=='sh000688' else '2016-01-01';first=np.searchsorted(d.index,pd.Timestamp(start));A=R[code]['A'][first-1:-1];mac=R[code]['MACD'][first-1:-1];L=len(A);samples=np.tile(A,(REPS,1));i=0;movable=0;blocks=0
 while i<L:
  if not mac[i]:i+=1;continue
  b=i
  while i<L and mac[i]:i+=1
  e=i;v=A[b:e];count=int(np.sum(v&~np.r_[False,v[:-1]]));candidates=[]
  for offset in range(len(v)):
   q=np.roll(v,offset)
   if int(np.sum(q&~np.r_[False,q[:-1]]))==count and (e<L or q[-1]==v[-1]):candidates.append(q)
  assert candidates
  variants=np.unique(np.array(candidates),axis=0);blocks+=1
  if len(variants)>1:movable+=1
  samples[:,b:e]=variants[rng.integers(0,len(variants),REPS)]
 prev=np.concatenate([np.zeros((REPS,1),bool),samples[:,:-1]],axis=1);orders=np.sum(samples!=prev,axis=1)
 actual_orders=cache[code,'test','A',.001][0]['orders'];assert np.all(orders==actual_orders);assert np.all(samples.sum(axis=1)==A.sum())
 o=d.open.iloc[first:].to_numpy();c=d.close.iloc[first:].to_numpy();pc=d.close.iloc[first-1:-1].to_numpy();night=np.log(o/pc);day=np.log(c/o)
 lognav=prev@night+samples@day+orders*np.log(.999);years=(d.index[-1]-d.index[first]).days/365.25;sim=100*np.expm1(lognav/years);real=cache[code,'test','A',.001][0]['cagr'];base=cache[code,'test','MACD',.001][0]['cagr']
 actualprev=np.r_[False,A[:-1]];actual_log=actualprev@night+A@day+actual_orders*np.log(.999);assert abs(100*np.expm1(actual_log/years)-real)<1e-9
 # Simple trade pruning null for MACD versus MA10: same number of entries,
 # MA10's original entry and exit dates; does not match holding duration.
 st=R[code]['MA10'];_,_,t=cache[code,'test','MA10',.001];factors=list(1+t.ret)
 ma_m=cache[code,'test','MA10',.001][0]
 if ma_m['open_trade']:
  entry=np.flatnonzero(st[first-1:-1]&~np.r_[False,st[first-1:-2]])[-1]+first
  factors.append(d.close.iloc[-1]/d.open.iloc[entry]*.999)
 factors=np.log(np.array(factors));K=cache[code,'test','MACD',.001][0]['entries'];prune=[]
 assert K<=len(factors)
 for _ in range(REPS):prune.append(100*np.expm1(rng.choice(factors,K,replace=False).sum()/years))
 randomrows.append(dict(code=code,name=N[code],A_cagr=real,MACD_cagr=base,A_entries=cache[code,'test','A',.001][0]['entries'],A_exposure=cache[code,'test','A',.001][0]['exposure'],rotate_q=100*np.mean(sim<real),rotate_median=np.median(sim),rotate_low=np.quantile(sim,.025),rotate_high=np.quantile(sim,.975),macd_blocks=blocks,movable_blocks=movable,MACD_entries=K,pruned_MA10_q=100*np.mean(np.array(prune)<base),pruned_MA10_median=np.median(prune)))
# Calendar-year log excess and deleting-one-year sensitivity. Excluding a
# year removes already-realized returns, without refitting or changing signals.
yearrows=[];jackrows=[]
for code in D:
 nA=cache[code,'test','A',.001][1].nav;nM=cache[code,'test','MACD',.001][1].nav
 ra=nA/nA.shift().fillna(1.);rm=nM/nM.shift().fillna(1.)
 ya=np.log(ra).groupby(ra.index.year).sum();ym=np.log(rm).groupby(rm.index.year).sum();ex=ym-ya
 for y in ex.index:yearrows.append(dict(code=code,name=N[code],year=int(y),A_return=100*np.expm1(ya.loc[y]),MACD_return=100*np.expm1(ym.loc[y]),MACD_minus_A_log_pp=100*ex.loc[y]))
 for y in ex.index:jackrows.append(dict(code=code,name=N[code],removed_year=int(y),total_MACD_minus_A_log_pp=100*ex.sum(),remaining_MACD_minus_A_log_pp=100*(ex.sum()-ex.loc[y])))
pd.DataFrame(yearrows).to_csv(O/'codex_ma10_macd_years.csv',index=False)
pd.DataFrame(jackrows).to_csv(O/'codex_ma10_macd_leave_year_out.csv',index=False)
# Inferred index dividend sensitivities. Signed residual is a TR-consistent
# proxy, not verified constituent cash dividends; clip sensitivity also shown.
d=D['sh000300'];tr=pd.read_csv(P/'data/tr_H00300.csv',parse_dates=['date']).set_index('date').close.reindex(d.index);res=tr/tr.shift()-d.close/d.close.shift();divrows=[]
for mode,dv in [('signed',res),('clip',res.clip(lower=0))]:
 cashdiv=(dv*d.close.shift()).fillna(0).to_dict()
 for period,a in [('test','2016-01-01'),('all','2006-01-04')]:
  for label,st in {**R['sh000300'],'hold':np.ones(len(d),bool)}.items():
   for cost in ((0.,) if label=='hold' else (0.,.001)):
    m,_,_=ledger(d,st,a,cost=cost,div=cashdiv);divrows.append(dict(mode=mode,period=period,rule=label,cost_bp=cost*1e4,**m))
# Exposure/market correlation is descriptive, not seven independent trials.
corr=pd.DataFrame({k:d.close.pct_change().loc['2016':] for k,d in D.items()}).corr();corr.to_csv(O/'codex_ma10_macd_correlations.csv')
pd.DataFrame(summary).to_csv(O/'codex_ma10_macd_summary.csv',index=False);pd.DataFrame(checks).to_csv(O/'codex_ma10_macd_comparison.csv',index=False);pd.DataFrame(warming).to_csv(O/'codex_ma10_macd_warmup.csv',index=False);pd.DataFrame(randomrows).to_csv(O/'codex_ma10_macd_random.csv',index=False);pd.DataFrame(divrows).to_csv(O/'codex_ma10_macd_dividends.csv',index=False);pd.concat(trade_rows,ignore_index=True).to_csv(O/'codex_ma10_macd_trades.csv',index=False)
metadata=dict(original_sha256=hashlib.sha256(source.encode()).hexdigest(),input_sha256={k:hashlib.sha256((P/f'data/index_{k}_ohlc.csv').read_bytes()).hexdigest() for k in N},backtest_globals_is_exec_namespace=ns['backtest'].__globals__ is ns,max_daily_nav_error=max(z['nav_error'] for z in checks),compared_paths=len(checks),random_reps=REPS,synthetic_window_and_fee_checks='passed')
(O/'codex_ma10_macd_diagnostics.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2));print(pd.DataFrame(randomrows).to_string(index=False));print('All independent signal, cost, trade, NAV, and prefix checks passed.')
