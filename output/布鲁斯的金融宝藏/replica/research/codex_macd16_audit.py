"""Round16, independent fixed-design study. Run with replica venv.
See codex_macd16_design.md written before results. No original scripts executed.
Correct prelisting splits, use proportional ex-reference signal; cash/unit ledger.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parents[1];O=P/'research';END=pd.Timestamp('2026-11-10');CUT=pd.Timestamp('2023-01-01');START=pd.Timestamp('2023-01-03');COST=.001
ITEMS=json.load(open(P/'data/page_etfs_plus.json'));DB={};EVENTS=[];ROWS=[];FEATURES=['dd60','ma200','dea','slope60','adx','vol20','cross60','since_dead','prev_ret','kd','rsi','market_ma200','pe_rank','volume_ratio','dif_speed','hist','sync']

def ema(v,alpha):
 v=np.asarray(v,float);z=np.full(len(v),np.nan);valid=np.flatnonzero(np.isfinite(v))
 if not len(valid):return z
 k=valid[0];z[k]=v[k]
 for i in range(k+1,len(v)):z[i]=z[i-1]+alpha*(v[i]-z[i-1]) if np.isfinite(v[i]) else z[i-1]
 return z

def wilder(v,n=14):
 v=np.asarray(v,float);z=np.full(len(v),np.nan)
 for k in range(n-1,len(v)):
  if np.all(np.isfinite(v[k-n+1:k+1])):z[k]=np.mean(v[k-n+1:k+1]);break
 else:return z
 for i in range(k+1,len(v)):z[i]=(z[i-1]*(n-1)+v[i])/n if np.isfinite(v[i]) else z[i-1]
 return z

def load(code):
 d=pd.read_csv(P/f'data/etf_{code}_raw.csv',parse_dates=['date']).set_index('date').sort_index().loc[:END];d=d[~d.index.duplicated()];j=json.load(open(P/f'data/etf_{code}_events.json'));dv=np.zeros(len(d));mm=np.ones(len(d))
 for date,amount in j['div']:
  k=d.index.searchsorted(pd.Timestamp(date))
  if 0<k<len(d):dv[k]+=amount
 for date,ratio in j['spl']:
  t=pd.Timestamp(date)
  if t<d.index[0] or t>d.index[-1]:EVENTS.append(dict(code=code,date=date,ratio=ratio,status='outside_quote_history'));continue
  k0=d.index.searchsorted(t);choices=range(max(1,k0-2),min(len(d),k0+4));k=min(choices,key=lambda i:abs(np.log(d.close.iloc[i-1]/d.open.iloc[i])-np.log(ratio)));mm[k]*=ratio;EVENTS.append(dict(code=code,date=date,effective=str(d.index[k].date()),ratio=ratio,status='gap_mapped'))
 c=d.close.to_numpy();factor=np.ones(len(d));factor[1:]=mm[1:]*c[:-1]/(c[:-1]-dv[1:]*mm[1:]);adj=c*np.cumprod(factor)
 return d,dv,mm,adj

def indicators(d,c):
 s=pd.Series(c,index=d.index);dif=ema(c,2/13)-ema(c,2/27);dea=ema(dif,.2);m=dif>dea;gold=m&~np.r_[False,m[:-1]];dead=~m&np.r_[False,m[:-1]];factor=c/d.close.to_numpy();hi=d.high.to_numpy()*factor;lo=d.low.to_numpy()*factor;last=np.r_[np.nan,c[:-1]];tr=np.maximum(hi-lo,np.maximum(abs(hi-last),abs(lo-last)));up=np.r_[np.nan,np.diff(hi)];dn=np.r_[np.nan,-np.diff(lo)];plus=np.where((up>dn)&(up>0),up,0.);minus=np.where((dn>up)&(dn>0),dn,0.);plus[0]=minus[0]=np.nan
 atr=wilder(tr);pp=wilder(plus);nn=wilder(minus)
 with np.errstate(divide='ignore',invalid='ignore'):dx=100*abs(pp-nn)/(pp+nn);adx=wilder(dx)
 delta=np.r_[np.nan,np.diff(c)];u=wilder(np.maximum(delta,0));v=wilder(np.maximum(-delta,0))
 with np.errstate(divide='ignore',invalid='ignore'):rsi=np.where(v==0,np.where(u==0,50,100),100-100/(1+u/v))
 hh=pd.Series(hi).rolling(9,min_periods=1).max().to_numpy();ll=pd.Series(lo).rolling(9,min_periods=1).min().to_numpy()
 with np.errstate(divide='ignore',invalid='ignore'):rsv=np.where(hh>ll,100*(c-ll)/(hh-ll),50)
 k=np.empty(len(c));dd=k.copy();a=b=50.
 for i,z in enumerate(rsv):a=(2*a+z)/3;b=(2*b+a)/3;k[i]=a;dd[i]=b
 since=np.full(len(c),np.nan);last_dead=None
 for i in range(len(c)):
  if dead[i]:last_dead=i
  if last_dead is not None:since[i]=i-last_dead
 f=pd.DataFrame(index=d.index);f['dd60']=c/s.rolling(60).max()-1;f['ma200']=c/s.rolling(200).mean()-1;f['dea']=dea/c;ma=s.rolling(60).mean();f['slope60']=ma/ma.shift(20)-1;f['adx']=adx;f['vol20']=s.pct_change().rolling(20).std()*np.sqrt(252);f['cross60']=pd.Series(np.r_[False,m[1:]!=m[:-1]],index=d.index).rolling(60).sum();f['since_dead']=since;f['kd']=k-dd;f['rsi']=rsi;f['dif_speed']=(dif-np.r_[np.full(3,np.nan),dif[:-3]])/c;f['hist']=(dif-dea)/c
 f['volume_ratio']=d.volume/d.volume.shift(1).rolling(20).mean() if 'volume' in d else np.nan
 return f,m,gold,dead

sh=pd.read_csv(P/'data/index_sh000001_ohlc.csv',parse_dates=['date']).set_index('date').close;market=sh/sh.rolling(200).mean()-1
pe=pd.read_csv(P/'data/hs300_pe_lg_monthly.csv',parse_dates=['日期']).set_index('日期')['滚动市盈率'];pe=pe.sort_index();ranks=[]
for i,z in enumerate(pe):
 h=pe.iloc[max(0,i-119):i+1];ranks.append(((h<z).sum()+((h==z).sum()-1)/2)/len(h) if len(h)>=60 else np.nan)
pe_rank=pd.Series(ranks,index=pe.index)
for code,name,group in ITEMS:
 d,dv,mm,c=load(code);f,m,gold,dead=indicators(d,c);f['market_ma200']=market.reindex(d.index).ffill();f['pe_rank']=pe_rank.reindex(d.index,method='ffill');DB[code]=dict(d=d,dv=dv,mm=mm,c=c,f=f,m=m,gold=gold,dead=dead,name=name,group=group)
# Only ETFs with observed history and warmup by the date enter synchronization denominator.
gold_panel=pd.DataFrame({code:pd.Series(z['gold'].astype(float),index=z['d'].index).where(np.arange(len(z['d']))>=60) for code,z in DB.items()});ng=gold_panel.notna().sum(axis=1);total=gold_panel.sum(axis=1)
for code,z in DB.items():
 d=z['d'];idx=d.index;o=d.open.to_numpy();prefix=np.cumsum(np.log(z['mm']*(1+z['dv']/o)));f=z['f'];f['sync']=((total-gold_panel[code].fillna(0))/(ng-gold_panel[code].notna().astype(int))).reindex(idx);m=z['m'];last_return=np.nan;i=0
 while i<len(d):
  if not m[i]:i+=1;continue
  b=i
  while i<len(d) and m[i]:i+=1
  e=i
  if e>=len(d)-1:continue
  buy=b+1;sell=e+1;ret=o[sell]/o[buy]*np.exp(prefix[sell]-prefix[buy])*(1-COST)**2-1
  if b>=60:
   row=dict(code=code,name=z['name'],group=z['group'],date=idx[b],buy=idx[buy],sell=idx[sell],ret=ret,duration=sell-buy,win=ret>0,period='train' if idx[sell]<CUT else 'valid' if idx[b]>=CUT else 'boundary',**f.iloc[b].to_dict());row['prev_ret']=last_return;ROWS.append(row)
  last_return=ret
T=pd.DataFrame(ROWS);train=T[T.period=='train'];valid=T[T.period=='valid'];thresholds={}
for k in FEATURES:
 values=train[k].dropna();thresholds[k]=np.quantile(values,[.2,.4,.6,.8]).tolist() if len(values) else [None]*4
T.to_csv(O/'codex_macd16_trades.csv',index=False);(O/'codex_macd16_thresholds.json').write_text(json.dumps(thresholds,ensure_ascii=False,indent=2));pd.DataFrame(EVENTS).to_csv(O/'codex_macd16_events.csv',index=False)
# All feature tables use training cut points. Empty bins remain empty.
bins=[];corr=[]
for k in FEATURES:
 q=thresholds[k]
 if q[0] is None:continue
 edges=np.unique(q);T[k+'_bin']=np.searchsorted(edges,T[k].to_numpy(),side='right')+1;T.loc[T[k].isna(),k+'_bin']=np.nan
 for per in ['train','valid']:
  a=T[T.period==per];b=a[[k,'ret']].dropna();rho=b.rank().corr().iloc[0,1] if len(b)>2 else np.nan;corr.append(dict(feature=k,period=per,n=len(b),rho=rho))
  for n,g in a.groupby(k+'_bin'):bins.append(dict(feature=k,period=per,bin=int(n),n=len(g),mean=g.ret.mean(),median=g.ret.median(),win=g.win.mean()))
pd.DataFrame(bins).to_csv(O/'codex_macd16_bins.csv',index=False);pd.DataFrame(corr).to_csv(O/'codex_macd16_correlations.csv',index=False)
KD20=thresholds['kd'][0];KD40=thresholds['kd'][1]
def rule_states(z):
 f=z['f'];m=z['m'];out={k:np.zeros(len(m),bool) for k in ['KD20','KD0','KD53','KD40','DEAD3','BOTH']};gates={'KD20':f.kd>=KD20,'KD0':f.kd>0,'KD53':f.kd>=5.3,'KD40':f.kd>=KD40,'DEAD3':f.since_dead>3,'BOTH':(f.kd>=KD20)&(f.since_dead>3)};start=0
 for i in range(len(m)):
  if m[i] and (i==0 or not m[i-1]):start=i
  if m[i]:
   for k,v in gates.items():out[k][i]=bool(v.iloc[start])
 out['M']=m;out['CURRENT53']=m&(f.kd.to_numpy()>=5.3)
 return out

def ledger(z,st,start=START,flat=False):
 d=z['d'];a=max(60,d.index.searchsorted(start));cash=1.;q=0.;vals=[];dates=[];fills=[];waiting=flat
 for i in range(a,len(d)):
  want=bool(st[i-1])
  if waiting:
   # No inherited cycle: wait until next fresh MACD gold after start.
   if z['gold'][i-1]:waiting=False
   else:want=False
  D=q*z['mm'][i]*z['dv'][i]
  if q:q=q*z['mm'][i]+D/d.open.iloc[i]
  if want and q==0:q=cash*(1-COST)/d.open.iloc[i];cash=0.;fills.append((d.index[i],'buy'))
  elif not want and q:cash=q*d.open.iloc[i]*(1-COST);q=0.;fills.append((d.index[i],'sell'))
  vals.append(cash+q*d.close.iloc[i]);dates.append(d.index[i])
 return pd.Series(vals,index=dates),fills

def metric(n):
 if len(n)<2:return dict(ann=np.nan,dd=np.nan)
 return dict(ann=n.iloc[-1]**(365.25/(n.index[-1]-n.index[0]).days)-1,dd=np.min(n.to_numpy()/np.maximum.accumulate(np.r_[1,n.to_numpy()])[1:]-1))
NAV={};ST={};MET=[];YEAR=[];DIFF=[]
eligible=[code for code,z in DB.items() if len(z['d'])>60 and z['d'].index[60]<=START]
for code in eligible:
 z=DB[code];states=rule_states(z);ST[code]=states
 for rule,st in states.items():
  n,fills=ledger(z,st);NAV[code,rule]=n;met=metric(n);MET.append(dict(code=code,name=z['name'],rule=rule,**met,buy_count=sum(t=='buy' for _,t in fills),sell_count=sum(t=='sell' for _,t in fills)))
  yr=n.groupby(n.index.year).last();prev=yr.shift(1);prev.iloc[0]=1
  for year,value in (yr/prev-1).items():YEAR.append(dict(code=code,rule=rule,year=year,ret=value))
 for rule in ['M','KD20']:
  n,_=ledger(z,states[rule],flat=True);MET.append(dict(code=code,name=z['name'],rule=rule+'_FLAT',**metric(n)))
 f=z['f'];m=z['m'];gold=z['gold'];scope=z['d'].index>=START;DIFF.append(dict(code=code,days_current_only=int(sum(scope&m&(f.kd.to_numpy()>=5.3)&~states['KD53'])),days_entry_only=int(sum(scope&states['KD53']&~(m&(f.kd.to_numpy()>=5.3)))),gold_current_pass=int(sum(scope&gold&(f.kd.to_numpy()>=5.3))),state_current_pass=int(sum(scope&m&(f.kd.to_numpy()>=5.3)))))
pd.DataFrame(MET).to_csv(O/'codex_macd16_portfolios.csv',index=False);pd.DataFrame(YEAR).to_csv(O/'codex_macd16_yearly.csv',index=False);pd.DataFrame(DIFF).to_csv(O/'codex_macd16_current_vs_entry.csv',index=False)
# Every ETF is an initially equal funded subaccount; cash retained in that account.
PORT={};MONTH=[]
for rule in ST[eligible[0]]:
 frame=pd.DataFrame({code:NAV[code,rule] for code in eligible}).ffill();port=frame.mean(axis=1);PORT[rule]=port;end=port.groupby(port.index.to_period('M')).last();prev=end.shift(1);prev.iloc[0]=1
 for date,value in np.log(end/prev).items():MONTH.append(dict(month=str(date),rule=rule,logret=value))
pd.DataFrame(MONTH).to_csv(O/'codex_macd16_monthly.csv',index=False)
# Cluster uncertainty on validation trades; endpoint labels keep each completed trade intact.
V=valid.copy();V['month']=V.date.dt.to_period('M').astype(str);V['sel']=V.kd>=KD20;clusters=[]
for month,g in V.groupby('month'):clusters.append([g.loc[g.sel,'ret'].sum(),g.sel.sum(),g.loc[~g.sel,'ret'].sum(),(~g.sel).sum()])
clusters=np.array(clusters);rng=np.random.default_rng(1601);bs=[]
for _ in range(5000):
 a=clusters[rng.integers(0,len(clusters),len(clusters))].sum(axis=0)
 if a[1] and a[3]:bs.append(a[0]/a[1]-a[2]/a[3])
# Six-month moving blocks of the full equally funded portfolio monthly return difference.
mth=pd.DataFrame(MONTH).pivot(index='month',columns='rule',values='logret');blocks=[]
for rule in ['KD20','KD0','KD53','KD40','DEAD3','BOTH','CURRENT53']:
 diff=(mth[rule]-mth.M).to_numpy();n=len(diff);sim=[]
 for _ in range(5000):
  starts=rng.integers(0,n-6+1,int(np.ceil(n/6)));sample=np.concatenate([diff[k:k+6] for k in starts])[:n];sim.append(np.mean(sample)*12)
 blocks.append(dict(rule=rule,annual_log_gain=diff.mean()*12,lo=np.quantile(sim,.025),hi=np.quantile(sim,.975)))
pd.DataFrame(blocks).to_csv(O/'codex_macd16_block_intervals.csv',index=False)
# Calendar-year group portfolios and fixed (historically selected) 17-good partition.
good=set(json.load(open(O/'codex_etf15_diagnostics.json'))['good']);GROUPS=[]
for group,codes in [('all',eligible),('historical_good',[c for c in eligible if c in good]),('other',[c for c in eligible if c not in good])]:
 for rule in ['M','KD20','KD0','KD53','KD40','DEAD3','BOTH','CURRENT53']:
  n=pd.DataFrame({c:NAV[c,rule] for c in codes}).ffill().mean(axis=1);met=metric(n);GROUPS.append(dict(group=group,rule=rule,n=len(codes),year='all',**met));yr=n.groupby(n.index.year).last();prev=yr.shift(1);prev.iloc[0]=1
  for year,v in (yr/prev-1).items():GROUPS.append(dict(group=group,rule=rule,n=len(codes),year=str(year),ann=v,dd=np.nan))
pd.DataFrame(GROUPS).to_csv(O/'codex_macd16_groups.csv',index=False)
meta=dict(design_sha256=hashlib.sha256((O/'codex_macd16_design.md').read_bytes()).hexdigest(),eligible=eligible,n_train=len(train),n_valid=len(valid),n_boundary=int(sum(T.period=='boundary')),kd20=KD20,kd40=KD40,cluster_difference=V[V.sel].ret.mean()-V[~V.sel].ret.mean(),cluster_ci=np.quantile(bs,[.025,.975]).tolist(),train_mean=train.ret.mean(),valid_mean=valid.ret.mean(),train_win=train.win.mean(),valid_win=valid.win.mean(),train_kd_low=train[train.kd<KD20].ret.mean(),train_kd_high=train[train.kd>=KD20].ret.mean(),validation_kd_low=V[~V.sel].ret.mean(),validation_kd_high=V[V.sel].ret.mean(),inputs_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'data').glob('etf_*') if f.suffix in ['.json','.csv']})
(O/'codex_macd16_diagnostics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in meta.items() if k!='inputs_sha256'},ensure_ascii=False,indent=2));print(pd.DataFrame(blocks).to_string(index=False));print('DONE independent fixed-design round16')
# Post-computation audit only: comparison does not change thresholds or choices.
old=pd.read_csv(O/'macd_loser_validate_results.csv',dtype={'code':str}).set_index('code');new=pd.DataFrame(MET);comp=[]
for rule,prior in [('M','M'),('KD53','C1'),('DEAD3','C2'),('BOTH','C12')]:
 z=new[new.rule==rule].set_index('code')
 for code in z.index:
  for metric_name,oldcol in [('ann',prior),('dd',prior+'_dd')]:comp.append(dict(code=code,rule=rule,metric=metric_name,difference=z.loc[code,metric_name]-old.loc[code,oldcol]))
comp=pd.DataFrame(comp);comp.to_csv(O/'codex_macd16_comparison.csv',index=False);assert comp.difference.abs().max()<1e-9
# Full 17/34 partition is retrospective, and six funds start after 2023-01-03.
page15=pd.read_csv(O/'codex_etf15_page.csv',dtype={'code':str});longset=set(page15[page15.years>=3].code);full=[]
for code in sorted(longset):
 for rule in ['M','KD20']:
  z=DB[code];st=rule_states(z)[rule];n,_=ledger(z,st);full.append(dict(code=code,group='historical_good' if code in good else 'other',rule=rule,start=str(n.index[0].date()),**metric(n)))
pd.DataFrame(full).to_csv(O/'codex_macd16_full51.csv',index=False)
# Mechanism diagnostics, explicitly descriptive: no new rule selected from them.
mechanism=[]
for period in ['train','valid']:
 a=T[T.period==period]
 for label,g in [('low',a[a.kd<KD20]),('rest',a[a.kd>=KD20])]:
  mechanism.append(dict(period=period,subset=label,n=len(g),mean=g.ret.mean(),median=g.ret.median(),win=g.win.mean(),dead_gap_median=g.since_dead.median(),quick_le3=np.mean(g.since_dead<=3),cross60_median=g.cross60.median(),duration_median=g.duration.median(),below_ma200=np.mean(g.ma200.dropna()<0),below_dea0=np.mean(g.dea<0),rsi_median=g.rsi.median(),slope60_median=g.slope60.median()))
pd.DataFrame(mechanism).to_csv(O/'codex_macd16_mechanism.csv',index=False)
# Completed trade date alignment and exact endpoint reconciliation with old trade file.
ot=pd.read_csv(O/'macd_loser_trades.csv',dtype={'code':str},parse_dates=['date']);joined=T.merge(ot,on=['code','date'],suffixes=('_new','_old'));joined[['code','date','ret_new','ret_old','kd_new','kd_old']].to_csv(O/'codex_macd16_trade_comparison.csv',index=False)
print('Postcheck:',len(comp),'portfolio metrics, max difference',comp.difference.abs().max(),'matched completed trades',len(joined),'old/new',len(ot),len(T))
print('Missing volume input:',sum('volume' not in z['d'] for z in DB.values()),'of',len(DB))

# Concrete page-semantics examples from validation, not new trading candidates.
examples=[]
for code in eligible:
 z=DB[code];st=ST[code]['KD53'];idx=z['d'].index;latest=None;seen=set()
 for i in range(60,len(idx)):
  if z['gold'][i]:latest=i
  if idx[i]<START or latest is None or not z['m'][i] or z['gold'][i]:continue
  now=z['f'].kd.iloc[i]>=5.3;before=bool(st[i]);kind='late_pass' if now and not before else 'lost_pass' if before and not now else None
  if kind and kind not in seen:
   seen.add(kind);examples.append(dict(code=code,kind=kind,date=str(idx[i].date()),gold_date=str(idx[latest].date()),kd_at_gold=z['f'].kd.iloc[latest],kd_current=z['f'].kd.iloc[i]))
pd.DataFrame(examples).to_csv(O/'codex_macd16_page_examples.csv',index=False)
# Causality check: indicators on a prefix must equal their full-history prefix.
for code in ['518880','512690','512480']:
 z=DB[code];n=min(700,len(z['d'])-1);f,m,g,dead=indicators(z['d'].iloc[:n],z['c'][:n]);assert np.array_equal(m,z['m'][:n]);assert np.allclose(f.kd,z['f'].kd.iloc[:n],equal_nan=True);assert np.allclose(f.adx,z['f'].adx.iloc[:n],equal_nan=True)
# Synthetic book tests: ex-dividend and split conserve gross wealth; ex-date
# entrants have no old-share dividend, and sell-day old shares retain dividend.
idx=pd.bdate_range('2020-01-01',periods=64);df=pd.DataFrame({'open':100.,'close':100.},index=idx);dv=np.zeros(64);mm=np.ones(64);dv[61]=5;df.loc[idx[61]:,['open','close']]=95.;state=np.ones(64,bool);z={'d':df,'dv':dv,'mm':mm,'gold':np.zeros(64,bool)};n,_=ledger(z,state,start=idx[60]);assert abs(n.iloc[-1]-(1-COST))<1e-12
state[60:]=False;n,_=ledger(z,state,start=idx[60]);assert abs(n.iloc[-1]-(1-COST)**2)<1e-12
state[:]=False;state[60:]=True;n,_=ledger(z,state,start=idx[60]);assert abs(n.iloc[-1]-(1-COST))<1e-12
z['dv']=np.zeros(64);z['mm']=np.ones(64);z['mm'][61]=2;z['d'].loc[idx[61]:,['open','close']]=50.;n,_=ledger(z,np.ones(64,bool),start=idx[60]);assert abs(n.iloc[-1]-(1-COST))<1e-12
print('Checks passed: original 360 metrics; prefix causality; buy/sell/dividend/split book examples.')
meta['supplemental_inputs_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [P/'data/page_etfs_plus.json',P/'data/index_sh000001_ohlc.csv',P/'data/hs300_pe_lg_monthly.csv',O/'codex_etf15_diagnostics.json']};meta['original_scripts_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [O/'macd_loser_features.py',O/'macd_loser_validate.py']};(O/'codex_macd16_diagnostics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
