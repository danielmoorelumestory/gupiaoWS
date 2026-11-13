"""Fixed-design rolling-origin filters, see codex_macd_filter17_design.md.
Run with replica venv. Only own independent helper imported.
"""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
from codex_macd_common import load,indicators,wilder,ledger,metric,P,EVENTS
O=P/'research';DB={};TRAIN=[];ITEMS=json.load(open(P/'data/page_etfs_plus.json'));RULES=['M','C2','A20','T60','K20','C2K20']
for code,name,group in ITEMS:
 d,dv,mm,c=load(code);f,m,gold,dead=indicators(d,c);fac=c/d.close.to_numpy();h=d.high.to_numpy()*fac;l=d.low.to_numpy()*fac;prev=np.r_[np.nan,c[:-1]];tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev)));atr=wilder(tr);f['hist_atr']=f['hist'].to_numpy()*c/atr;s=pd.Series(c,index=d.index);ma=s.rolling(60).mean();f['trend']=(s>ma)&(ma>ma.shift(20));idx=d.index;o=d.open.to_numpy();prefix=np.cumsum(np.log(mm*(1+dv/o)));cycles=[];i=0
 while i<len(d):
  if not m[i]:i+=1;continue
  b=i
  while i<len(d) and m[i]:i+=1
  e=i;cycles.append((b,e))
  if b>=60 and e<len(d)-1:TRAIN.append(dict(code=code,date=idx[b],sell=idx[e+1],kd=f.kd.iloc[b],hist_atr=f.hist_atr.iloc[b]))
 DB[code]=dict(d=d,dv=dv,mm=mm,c=c,f=f,m=m,gold=gold,dead=dead,name=name,group=group,prefix=prefix,cycles=cycles)
T=pd.DataFrame(TRAIN);TH=[];threshold={}
for year in range(2013,2027):
 cut=pd.Timestamp(year=year,month=1,day=1);begin=pd.Timestamp(year=year-3,month=1,day=1);a=T[(T.date>=begin)&(T.sell<cut)];kd=a.kd.quantile(.2) if len(a)>=50 else np.nan;am=a.hist_atr.quantile(.2) if len(a)>=50 else np.nan;threshold[year]=(kd,am);TH.append(dict(year=year,n=len(a),train_first=str(begin.date()),train_end=str((cut-pd.Timedelta(days=1)).date()),kd20=kd,amplitude20=am))
pd.DataFrame(TH).to_csv(O/'codex_filter17_thresholds.csv',index=False)
for code,z in DB.items():
 f=z['f'];m=z['m'];n=len(m);states={r:np.zeros(n,bool) for r in RULES};states['M']=m.copy();decisions=[]
 for b,e in z['cycles']:
  qk,qa=threshold.get(z['d'].index[b].year,(np.nan,np.nan));k=f.kd.iloc[b]>=qk;a=f.hist_atr.iloc[b]>=qa;t=bool(f.trend.iloc[b]);states['A20'][b:e]=a;states['T60'][b:e]=t;states['K20'][b:e]=k
  if b+1<e:states['C2'][b+1:e]=True;states['C2K20'][b+1:e]=k
  if b>=60:decisions.append(dict(code=code,date=z['d'].index[b],end=(str(z['d'].index[e].date()) if e<n else None),days=e-b,K20=k,A20=a,T60=t,C2=b+1<e,C2K20=k and b+1<e))
 z['states']=states;z['decisions']=decisions
MET=[];TRADES=[];GROUP=[];YEAR=[];MONTH=[];NAV={};DEC=[];SAMPLE=[]
for label,start in [('2020',pd.Timestamp('2020-01-02')),('2023',pd.Timestamp('2023-01-03'))]:
 codes=[code for code,z in DB.items() if len(z['d'])>60 and z['d'].index[60]<=start];SAMPLE.append(dict(sample=label,n=len(codes),codes=codes))
 for code in codes:
  z=DB[code];idx=z['d'].index;o=z['d'].open;prefix=z['prefix'];DEC.extend(dict(sample=label,**d) for d in z['decisions'] if d['date']>=start)
  for cost in [.001,0.]:
   for rule in RULES:
    nav,fills=ledger(z,z['states'][rule],start=start,cost=cost);NAV[label,code,cost,rule]=nav;returns=[];entry=None
    for date,side in fills:
     if side=='buy':entry=idx.get_loc(date)
     elif entry is not None:
      k=idx.get_loc(date);r=o.iloc[k]/o.iloc[entry]*np.exp(prefix[k]-prefix[entry])*(1-cost)**2-1;returns.append(r);TRADES.append(dict(sample=label,code=code,cost=cost,rule=rule,buy=idx[entry],sell=date,ret=r,days=k-entry));entry=None
    MET.append(dict(sample=label,code=code,name=z['name'],cost=cost,rule=rule,**metric(nav),buys=sum(side=='buy' for _,side in fills),completed=len(returns),win=np.mean(np.array(returns)>0) if returns else np.nan,trade_mean=np.mean(returns) if returns else np.nan))
 for cost in [.001,0.]:
  for rule in RULES:
   n=pd.DataFrame({code:NAV[label,code,cost,rule] for code in codes}).ffill().mean(axis=1);GROUP.append(dict(sample=label,n=len(codes),cost=cost,rule=rule,**metric(n)));yr=n.groupby(n.index.year).last();prev=yr.shift(1);prev.iloc[0]=1
   for year,r in (yr/prev-1).items():YEAR.append(dict(sample=label,cost=cost,rule=rule,year=year,ret=r))
   end=n.groupby(n.index.to_period('M')).last();prev=end.shift(1);prev.iloc[0]=1
   for month,r in np.log(end/prev).items():MONTH.append(dict(sample=label,cost=cost,rule=rule,month=str(month),logret=r))
met=pd.DataFrame(MET);group=pd.DataFrame(GROUP);yearly=pd.DataFrame(YEAR);monthly=pd.DataFrame(MONTH);trades=pd.DataFrame(TRADES)
met.to_csv(O/'codex_filter17_funds.csv',index=False);group.to_csv(O/'codex_filter17_portfolios.csv',index=False);yearly.to_csv(O/'codex_filter17_years.csv',index=False);monthly.to_csv(O/'codex_filter17_months.csv',index=False);trades.to_csv(O/'codex_filter17_trades.csv',index=False);pd.DataFrame(DEC).to_csv(O/'codex_filter17_decisions.csv',index=False)
# Same time resampling for all five candidates retains their covariance.
BOOT=[];rng=np.random.default_rng(1701)
for label in ['2020','2023']:
 a=monthly[(monthly['sample']==label)&(monthly.cost==.001)].pivot(index='month',columns='rule',values='logret');diff=a[RULES[1:]].subtract(a.M,axis=0).to_numpy();n=len(a);sim=[]
 for _ in range(5000):
  starts=rng.integers(0,n-5,int(np.ceil(n/6)));sample=np.concatenate([diff[k:k+6] for k in starts])[:n];sim.append(sample.mean(axis=0)*12)
 sim=np.array(sim)
 for i,r in enumerate(RULES[1:]):BOOT.append(dict(sample=label,rule=r,annual_log_gain=diff[:,i].mean()*12,lo95=np.quantile(sim[:,i],.025),hi95=np.quantile(sim[:,i],.975),lo99=np.quantile(sim[:,i],.005),hi99=np.quantile(sim[:,i],.995)))
pd.DataFrame(BOOT).to_csv(O/'codex_filter17_bootstrap.csv',index=False)
# Main baseline must reproduce the earlier independently audited ledger.
old=pd.read_csv(O/'codex_macd16_portfolios.csv',dtype={'code':str});a=met[(met['sample']=='2023')&(met.rule=='M')&(met.cost==.001)].set_index('code');b=old[old.rule=='M'].set_index('code');assert a.index.equals(b.index);assert np.max(abs(a.ann-b.ann))<1e-10;assert np.max(abs(a.dd-b.dd))<1e-10
# Confirmation timing: first target on b+1, implies actual entry at b+2.
for z in DB.values():
 for b,e in z['cycles']:
  assert not z['states']['C2'][b]
  assert np.all(z['states']['C2'][b+1:e])
meta=dict(design_sha256=hashlib.sha256((O/'codex_macd_filter17_design.md').read_bytes()).hexdigest(),samples=SAMPLE,inputs_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'data').glob('etf_*') if f.suffix in ['.json','.csv']});(O/'codex_filter17_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print('Fixed rules, rolling 3-year thresholds. Main sample results:')
for label in ['2020','2023']:
 for cost in [.001,0.]:
  a=met[(met['sample']==label)&(met.cost==cost)];base=a[a.rule=='M'].set_index('code');print('sample',label,'cost',cost,'funds',len(base))
  for r in RULES:
   z=a[a.rule==r].set_index('code');p=group[(group['sample']==label)&(group.cost==cost)&(group.rule==r)].iloc[0];print(r,'mean/med/dd',*(round(v*100,4) for v in [z.ann.mean(),z.ann.median(),z.dd.median()]),'win',sum(z.ann>base.ann),'portfolio ann/dd',p.ann*100,p.dd*100,'trades',z.completed.sum())
print(pd.DataFrame(BOOT).to_string(index=False));print('Checks passed: baseline and confirmation timing.')
# Quality diagnostics use original full-cycle returns, not fictitious returns on
# skipped investments. Exclude inherited initial cycles and unclosed final cycle.
QUAL=[]
for sample in SAMPLE:
 label=sample['sample'];start=pd.Timestamp('2020-01-02' if label=='2020' else '2023-01-03')
 for code in sample['codes']:
  z=DB[code];idx=z['d'].index;o=z['d'].open.to_numpy();prefix=z['prefix']
  for b,e in z['cycles']:
   if b<60 or idx[b]<start or e>=len(idx)-1:continue
   ret=o[e+1]/o[b+1]*np.exp(prefix[e+1]-prefix[b+1])*.999**2-1;qk,qa=threshold[idx[b].year]
   for rule,passed in [('C2',b+1<e),('A20',z['f'].hist_atr.iloc[b]>=qa),('T60',bool(z['f'].trend.iloc[b])),('K20',z['f'].kd.iloc[b]>=qk),('C2K20',(b+1<e) and z['f'].kd.iloc[b]>=qk)]:QUAL.append(dict(sample=label,code=code,date=idx[b],rule=rule,passed=passed,original_ret=ret,original_win=ret>0))
pd.DataFrame(QUAL).to_csv(O/'codex_filter17_quality.csv',index=False)
