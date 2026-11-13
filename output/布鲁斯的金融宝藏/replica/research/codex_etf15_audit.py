"""Round 15 independent ETF audit. Run in replica with Python + pandas/numpy.
Original scripts never executed. Reimplements event mapping for replication,
manual EMA/RMA, per-MACD-cycle rule construction and cash/unit matching.
Compares stored original CSVs only after independent calculation.
Writes codex_etf15_* summaries, discrepancies, events and corrected controls.
"""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
P=Path(__file__).resolve().parents[1];O=P/'research';END='2026-11-10';ITEMS=json.load(open(P/'data/page_etfs_plus.json'));PICK=json.load(open(P/'data/etf_picked.json'))

def ema(x,alpha):
 x=np.asarray(x,float);out=np.full(len(x),np.nan);valid=np.flatnonzero(np.isfinite(x))
 if not len(valid):return out
 b=valid[0];out[b]=x[b]
 for i in range(b+1,len(x)):out[i]=out[i-1]+alpha*(x[i]-out[i-1]) if np.isfinite(x[i]) else out[i-1]
 return out

def load(code):
 d=pd.read_csv(P/f'data/etf_{code}_raw.csv',parse_dates=['date']).set_index('date').sort_index().loc[:END];d=d[~d.index.duplicated()];j=json.load(open(P/f'data/etf_{code}_events.json'));dv=np.zeros(len(d));mult=np.ones(len(d));events=[]
 for date,amount in j['div']:
  k=d.index.searchsorted(pd.Timestamp(date))
  if not 0<k<len(d):continue
  frac=amount/d.close.iloc[k-1];gap=d.open.iloc[k]/d.close.iloc[k-1]-1;keep=not(frac>=.02 and gap>-.5*frac)
  if keep:dv[k]+=amount
  events.append(dict(code=code,type='div',reported=date,effective=str(d.index[k].date()),value=amount,keep=keep,gap=gap))
 for date,ratio in j['spl']:
  k0=d.index.searchsorted(pd.Timestamp(date));candidates=list(range(max(1,k0-2),min(len(d),k0+4)))
  k=min(candidates,key=lambda i:abs(np.log(d.close.iloc[i-1]/d.open.iloc[i])-np.log(ratio)));mult[k]=ratio
  events.append(dict(code=code,type='split',reported=date,effective=str(d.index[k].date()),value=ratio,keep=True,offset=k-k0))
 close=d.close.to_numpy();o=d.open.to_numpy();ret=np.r_[1.,(close[1:]+dv[1:])*mult[1:]/close[:-1]];adj=close[0]*np.cumprod(ret)
 # Standard ex-reference proportional adjustment, a sensitivity, not the
 # original total-return-at-close signal series.
 factor=np.ones(len(d));factor[1:]=mult[1:]*close[:-1]/(close[:-1]-dv[1:]*mult[1:]);qadj=close*np.cumprod(factor)
 prefix=np.cumsum(np.log(mult*(1+dv/o)))
 return d,dv,mult,adj,qadj,prefix,events

def ind(d,c):
 c=np.asarray(c);dif=ema(c,2/13)-ema(c,2/27);dea=ema(dif,.2);h=d.high.to_numpy()*c/d.close.to_numpy();l=d.low.to_numpy()*c/d.close.to_numpy();s=pd.Series(c);change=np.r_[np.nan,np.diff(c)];up=ema(np.maximum(change,0),1/14);dn=ema(np.maximum(-change,0),1/14)
 with np.errstate(divide='ignore',invalid='ignore'):rsi=np.where((dn==0)|np.isnan(dn),100,100-100/(1+up/dn))
 hh=pd.Series(h).rolling(9,min_periods=1).max().to_numpy();ll=pd.Series(l).rolling(9,min_periods=1).min().to_numpy()
 with np.errstate(divide='ignore',invalid='ignore'):rsv=np.where(hh!=ll,(c-ll)/(hh-ll)*100,50)
 K=np.empty(len(c));DD=K.copy();a=b=50.
 for i,v in enumerate(rsv):a=(2*a+v)/3;b=(2*b+a)/3;K[i]=a;DD[i]=b
 return dict(c=c,dif=dif,dea=dea,M=dif>dea,rsi=rsi,K=K,D=DD,J=3*K-2*DD,dd60=c/s.rolling(60,min_periods=1).max().to_numpy()-1,ma5=s.rolling(5).mean().to_numpy(),ma10=s.rolling(10).mean().to_numpy(),max10=s.rolling(10).max().to_numpy(),difmax=pd.Series(dif).rolling(10).max().to_numpy())

def states(x):
 c=x['c'];m=x['M'];n=len(c);hist=x['dif']-x['dea'];out={'M':m.copy()};entry={'R50':x['rsi']>50,'R70':x['rsi']<70,'KD':x['K']>x['D'],'J100':x['J']<100,'UW':x['dea']<0,'AW':x['dea']>=0,'D10':x['dd60']<=-.1,'D20':x['dd60']<=-.2}
 for k in [*entry,'W1','W5','B','DH5','DH10','W55','W510','B5','RSIX','KDX']:out[k]=np.zeros(n,bool)
 cycles=[];i=0
 while i<n:
  if not m[i]:i+=1;continue
  b=i
  while i<n and m[i]:i+=1
  e=i;cycles.append((b,e))
  for k,g in entry.items():
   if g[b]:out[k][b:e]=True
  for k in ['W1','W5','B','DH5','DH10','W55','W510','B5','RSIX','KDX']:
   stop=e;warn=False;ma=x['ma5'] if k in ['DH5','W55','B5'] else x['ma10']
   for t in range(b+1,e):
    if k=='W1' and c[t]>c[t-1] and 0<hist[t]<hist[t-1]:warn=True
    if k in ['W5','W55','W510'] and t>=5 and c[t]>c[t-5] and x['dif'][t]<x['dif'][t-5]:warn=True
    if k in ['DH5','DH10'] and t>=9 and c[t]>=x['max10'][t] and x['dif'][t]<x['difmax'][t]:warn=True
    hit=(k in ['B','B5'] or warn) and c[t]<ma[t]
    if k=='RSIX':hit=x['rsi'][t-1]>=70 and x['rsi'][t]<70
    if k=='KDX':hit=x['K'][t-1]>80 and x['K'][t-1]>=x['D'][t-1] and x['K'][t]<x['D'][t]
    if hit:stop=t;break
   out[k][b:stop]=True
 return out,entry,cycles

def book(d,dv,mult,st,a=60,b=None,cost=.001,mode='open'):
 b=len(d) if b is None else b;o=d.open.to_numpy();c=d.close.to_numpy();cash=1.;q=0.;entry=None;returns=[];nav=np.empty(b-a)
 for i in range(a,b):
  want=bool(st[i-1]);D=q*mult[i]*dv[i]
  if q:
   q*=mult[i]
   if mode=='open':q+=D/o[i]
  if want and q==0:entry=cash;q=cash*(1-cost)/o[i];cash=0.
  elif not want and q:cash+=q*o[i]*(1-cost)+(D if mode!='open' else 0);q=0.;returns.append(cash/entry-1);entry=None
  if q and mode!='open':q+=D/c[i]
  nav[i-a]=cash+q*c[i]
 return nav,np.array(returns)
def metrics(nav,idx):
 years=(idx[-1]-idx[0]).days/365.25
 return dict(ann=nav[-1]**(1/years)-1,dd=np.min(nav/np.maximum.accumulate(np.r_[1.,nav])[1:]-1),cum=nav[-1]-1)
def env(c):
 s=pd.Series(c);ma=s.rolling(200).mean();up=ma>ma.shift(20);r=np.repeat('震荡',len(s)).astype(object);r[(s>ma)&up]='牛';r[(s<ma)&~up&ma.notna()]='熊';return r
PE=pd.read_csv(P/'data/hs300_pe_lg_monthly.csv',parse_dates=['日期']).set_index('日期').sort_index();BANDS={}
for lens,col in [('整体PE','滚动市盈率'),('PE中位数','滚动市盈率中位数')]:
 v=PE[col].to_numpy();bb=[]
 for i,z in enumerate(v):
  h=v[max(0,i-119):i+1];rank=((h<z).sum()+((h==z).sum()-1)/2)/len(h);bb.append(None if len(h)<60 else '低估' if rank<.3 else '高估' if rank>.7 else '中性')
 BANDS[lens]=pd.Series(bb,index=PE.index).dropna()
def bands(idx,lens,lag=True):
 z=BANDS[lens];j=z.index.searchsorted(idx,side='right')-1;v=np.array([z.iloc[i] if i>=0 else '中性' for i in j],object)
 return np.concatenate([np.array(['中性'],object),v[:-1]]) if lag else v
sh=pd.read_csv(P/'data/index_sh000001_ohlc.csv',parse_dates=['date']).set_index('date');market=pd.Series(env(sh.close),index=sh.index)
REPLICATION=[];EVENTS=[];TRADES=[];SUM=[];FAIR=[];VALUATION=[];DATA=[];LOADED={};NAVS={};PAGE=[]
PAGESET={z[0] for z in ITEMS}
POOL=ITEMS+[(c,v[1],'原20只额外') for c,v in PICK.items() if c not in PAGESET]
for code,name,grp in POOL:
 d,dv,mult,c,qadj,prefix,events=load(code);LOADED[code]=(d,dv,mult,c,qadj,prefix);EVENTS+=events
 if len(d)<120:continue
 x=ind(d,c);sts,gates,cycles=states(x);years=(d.index[-1]-d.index[60]).days/365.25;mid=60+(len(d)-60)//2;idx=d.index
 close=d.close.to_numpy();o=d.open.to_numpy();ao=o*c/close;alltrue=np.ones(len(d),bool)
 strategies={**sts};own=env(c);mr=market.reindex(idx).ffill().fillna('震荡').to_numpy()
 for lens,rg in [('大盘',mr),('自身',own)]:
  strategies[lens+'P1']=(rg=='牛')|((rg=='震荡')&x['M']);strategies[lens+'P2']=(rg=='牛')|((rg!='牛')&x['M']);strategies[lens+'P3']=(rg!='熊')&x['M']
 for lens in BANDS:
  for lag in [True,False]:
   rg=bands(idx,lens,lag)
   for k,st in {'V1':(rg=='低估')|((rg!='低估')&x['M']),'V2':(rg!='高估')|((rg=='高估')&x['M']),'V3':(rg=='低估')|((rg=='中性')&x['M'])}.items():strategies[lens+k+('' if lag else '_nextopen')]=st
 local={}
 for rule,st in {'H':alltrue,**strategies}.items():
  cost=0 if rule=='H' else .001;n,tr=book(d,dv,mult,st,cost=cost);met=metrics(n,idx[60:]);n1,_=book(d,dv,mult,st,60,mid+1,cost);n2,_=book(d,dv,mult,st,mid,None,cost)
  rec=dict(code=code,name=name,rule=rule,years=years,ann=met['ann'],dd=met['dd'],n=len(tr),win=np.mean(tr>0) if len(tr) else np.nan,h1=metrics(n1,idx[60:mid+1])['ann'],h2=metrics(n2,idx[mid:])['ann'],exposure=np.mean(st[60:]));SUM.append(rec);local[rule]=rec
  if rule in ['H','M','D20','D10']:NAVS[code,rule]=n
 # Page screening reconstructed without consulting selected originals.
 page=dict(code=code,name=name,years=years,hold=local['H']['ann'],macd=local['M']['ann'],ex=local['M']['ann']-local['H']['ann'],hold_dd=local['H']['dd'],macd_dd=local['M']['dd'],h1=local['M']['h1']-local['H']['h1'],h2=local['M']['h2']-local['H']['h2']);page['good']=years>=3 and page['ex']>=.03 and page['h1']>0 and page['h2']>0 and page['macd_dd']>page['hold_dd'];page.update(h1=np.nan,h2=np.nan) if years<1 else None;PAGE.append(page) if code in PAGESET else None
 # Matched-cycle returns with legacy proxy AND cashflow-consistent endpoints.
 for b,e in cycles:
  if b<60 or e>=len(d)-1 or code not in PAGESET:continue
  buy=b+1;sell=e+1;exact=o[sell]/o[buy]*np.exp(prefix[sell]-prefix[buy])*.999**2-1;proxy=ao[sell]/ao[buy]*.999**2-1
  TRADES.append(dict(code=code,name=name,date=str(idx[b].date()),long=years>=3,ret=proxy,exact_ret=exact,fall=x['dd60'][b],uw=x['dea'][b]<0,**{k:bool(g[b]) for k,g in gates.items()}))
 # Early-exit event matching includes original horizon and start convention.
 for rule in ['W1','W5','B','DH5','DH10','W55','W510','B5','RSIX','KDX']:
  st=sts[rule]
  if code not in PAGESET:continue
  for i in np.flatnonzero(st[:-1]&~st[1:])+1:
   if i<61 or i>=len(d)-1 or not x['M'][i]:continue
   j=i
   while j<len(d)-1 and x['M'][j]:j+=1
   if j>=len(d)-1:continue
   EVENTS.append(dict(code=code,type='exit',rule=rule,date=str(idx[i].date()),long=years>=3,days=j-i,gain=ao[i+1]/ao[j+1]-1,exact_gain=o[i+1]/o[j+1]*np.exp(prefix[i+1]-prefix[j+1])-1))
 # Correct wealth-weighted exposure for buy-and-hold mix of subaccounts.
 nm=NAVS[code,'M'];held=lambda st:np.asarray(st[59:-1],float);hm=held(sts['M']);expM=hm.mean()
 for rule in ['D20','D10']:
  nd=NAVS[code,rule];hd=held(sts[rule]);comb=.5*(nm+nd);target=np.mean((nm*hm+nd*hd)/(nm+nd));oldc=min(1,target/expM) if expM else 0
  exposure=lambda a:np.mean(a*nm*hm/(a*nm+1-a));lo=0.;hi=1.
  for _ in range(60):md=(lo+hi)/2;lo,hi=(md,hi) if exposure(md)<target else (lo,md)
  corrected=(lo+hi)/2;oldfair=oldc*nm+1-oldc;newfair=corrected*nm+1-corrected
  FAIR.append(dict(code=code,name=name,years=years,rule=rule,target=target,old_c=oldc,old_actual_exposure=exposure(oldc),new_c=corrected,new_actual_exposure=exposure(corrected),combo=metrics(comb,idx[60:])['ann'],old_fair=metrics(oldfair,idx[60:])['ann'],new_fair=metrics(newfair,idx[60:])['ann'],half=metrics(.5*nm+.5,idx[60:])['ann'],half_actual_exposure=exposure(.5),half_reported_exposure=.5*expM))
 # Data/signal/ledger sensitivities; no event-data correction invented here.
 nq,_=book(d,dv,mult,ind(d,qadj)['M']);nc,_=book(d,dv,mult,sts['M'],mode='close');hc,_=book(d,dv,mult,alltrue,cost=0,mode='close')
 DATA.append(dict(code=code,name=name,years=years,first=str(idx[0].date()),last=str(idx[-1].date()),raw_rows=len(d),div_count=int(sum(dv>0)),split_count=int(sum(mult!=1)),kept_div_nominal=sum(dv),qfq_signal_different=int(sum(ind(d,qadj)['M']!=sts['M'])),qfq_macd=metrics(nq,idx[60:])['ann'],close_reinvest_macd=metrics(nc,idx[60:])['ann'],close_reinvest_hold=metrics(hc,idx[60:])['ann']))
 # Current 20-keyword cohort and common date/cumulative/yearly figures.
 if code in PICK or code in ['588170','588200']:
  for label,start in [('listing',idx[60]),('2021',pd.Timestamp('2021-01-04')),('202507',pd.Timestamp('2025-07-07'))]:
   a=idx.searchsorted(start)
   if a<60 or a>=len(d)-1:continue
   h,_=book(d,dv,mult,alltrue,a,cost=0);m,tr=book(d,dv,mult,sts['M'],a);SUM.append(dict(code=code,name=name,rule='cohort_'+label,years=years,ann=metrics(m,idx[a:])['ann'],hold_ann=metrics(h,idx[a:])['ann'],dd=metrics(m,idx[a:])['dd'],hold_dd=metrics(h,idx[a:])['dd'],cum=m[-1]-1,hold_cum=h[-1]-1,n=len(tr)))
# Compare all independent strategy metrics with each original stored result CSV.
summ=pd.DataFrame(SUM);page=pd.DataFrame(PAGE);trades=pd.DataFrame(TRADES);events=pd.DataFrame(EVENTS);fair=pd.DataFrame(FAIR);checks=[]
files={'macd_exit_divergence':['M','W1','W5','B'],'macd_exit_dunhua':['M','DH5','DH10','W55','W510','B5'],'macd_rsi_kdj':['M','R50','R70','KD','J100','RSIX','KDX'],'macd_regime':['H','M',*[l+k for l in ['大盘','自身'] for k in ['P1','P2','P3']]],'macd_valuation':['H','M',*[l+k for l in ['整体PE','PE中位数'] for k in ['V1','V2','V3']]],'macd_underwater':['M','UW','AW'],'macd_after_drop':['M','D10','D20']}
for file,rules_ in files.items():
 old=pd.read_csv(O/f'{file}_results.csv',dtype={'code':str}).set_index('code')
 for code in old.index:
  for rule in rules_:
   me=summ[(summ.code==code)&(summ.rule==rule)].iloc[0]
   for col,oc in [('ann',rule),('dd',rule+'_dd'),('h1',rule+'_h1'),('h2',rule+'_h2')]:
    err=float(me[col]-old.loc[code,oc]);checks.append(dict(file=file,code=code,rule=rule,metric=col,difference=err))
    assert abs(err)<1e-9,(file,code,rule,col,err)
old=pd.read_csv(O/'macd_page_etfs_plus_results.csv',dtype={'code':str}).set_index('code')
for z in PAGE:
 for col in ['hold','macd','ex','hold_dd','macd_dd','h1','h2']:
  err=z[col]-old.loc[z['code'],col];err=0. if pd.isna(z[col]) and pd.isna(old.loc[z['code'],col]) else err;checks.append(dict(file='page',code=z['code'],rule='M',metric=col,difference=err));assert abs(err)<1e-9,(z['code'],col,err)
 assert bool(z['good'])==bool(old.loc[z['code'],'good'])
oldfair=pd.read_csv(O/'macd_add_on_drop_results.csv',dtype={'code':str}).set_index('code')
for z in FAIR:
 if z['code'] not in oldfair.index:continue
 for col,oc in [('combo',z['rule']),('old_fair',z['rule']+'_fair'),('old_c',z['rule']+'_c'),('target',z['rule']+'_inv')]:
  err=z[col]-oldfair.loc[z['code'],oc];checks.append(dict(file='add',code=z['code'],rule=z['rule'],metric=col,difference=err));assert abs(err)<1e-9,(z['code'],col,err)
# Matched event-proxy values checked by distribution because legacy event rows
# use a different rule iteration order. The exact cashflow version is separate.
for file,filters in [('macd_exit_events.csv',['W1','W5','B']),('macd_exit_dunhua_events.csv',['DH5','DH10','W55','W510','B5'])]:
 olde=pd.read_csv(O/file,dtype={'code':str})
 for rule in filters:
  a=np.sort(olde[olde.rule==rule].gain.to_numpy());b=np.sort(events[(events.type=='exit')&(events.rule==rule)].gain.to_numpy());assert len(a)==len(b);assert np.max(abs(a-b))<1e-9
# Simple naive and date-cluster uncertainty: not treated as family-adjusted p.
longset=set(page[page.years>=3].code);T=trades[trades.long].copy();T['month']=pd.to_datetime(T.date).dt.to_period('M').astype(str)
E=events[(events.type=='exit')].copy();E['month']=pd.to_datetime(E.date).dt.to_period('M').astype(str);rng=np.random.default_rng(0);random=[]
for name,mask in [('KD',T.KD),('UW',T.uw),('D10',T.fall<=-.1),('D20',T.fall<=-.2)]:
 v=T.ret.to_numpy();g=mask.to_numpy(bool);nk=g.sum();real=v[g].mean()-v[~g].mean();sims=[]
 for _ in range(5000):p_=rng.permutation(len(v));sims.append(v[p_[:nk]].mean()-v[p_[nk:]].mean())
 # Month-cluster bootstrap confidence interval keeps contemporaneous ETF
 # events together; descriptive only (few severe-drawdown months).
 groups=[x for _,x in T.assign(sel=g).groupby('month')];bs=[]
 for _ in range(2000):
  sample=pd.concat([groups[i] for i in rng.integers(0,len(groups),len(groups))]);a=sample[sample.sel].ret;b=sample[~sample.sel].ret
  if len(a) and len(b):bs.append(a.mean()-b.mean())
 random.append(dict(rule=name,selected=int(nk),other=len(v)-int(nk),mean_selected=v[g].mean(),mean_other=v[~g].mean(),difference=real,naive_p=float(np.mean(np.array(sims)>=real)),cluster_lo=np.quantile(bs,.025),cluster_hi=np.quantile(bs,.975)))
# W5 original finite-population subsampling null (not a bootstrap).
b=E[E.rule=='B'].gain.to_numpy();w=E[E.rule=='W5'].gain.to_numpy();rng2=np.random.default_rng(0);sims=[rng2.choice(b,len(w),replace=False).mean() for _ in range(20000)];random.append(dict(rule='W5_exit',selected=len(w),mean_selected=w.mean(),naive_p=np.mean(np.array(sims)>=w.mean())))
page.to_csv(O/'codex_etf15_page.csv',index=False);summ.to_csv(O/'codex_etf15_strategies.csv',index=False);trades.to_csv(O/'codex_etf15_trades.csv',index=False);events.to_csv(O/'codex_etf15_events.csv',index=False);fair.to_csv(O/'codex_etf15_fair.csv',index=False);pd.DataFrame(DATA).to_csv(O/'codex_etf15_data.csv',index=False);pd.DataFrame(checks).to_csv(O/'codex_etf15_comparison.csv',index=False);pd.DataFrame(random).to_csv(O/'codex_etf15_random.csv',index=False)
meta=dict(original_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in O.glob('macd*.py')},checked_metrics=len(checks),max_abs_difference=max(abs(z['difference']) for z in checks),good=page[page.good].code.tolist(),long_count=len(longset),inputs_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'data').glob('etf_*') if f.suffix in ['.json','.csv']})
(O/'codex_etf15_diagnostics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print('Independent strategy and event comparisons passed',meta['checked_metrics'],meta['max_abs_difference']);print(pd.DataFrame(random).to_string(index=False));print('Good',meta['good'])
# Explicit counterfactual corrections kept separate from exact replication.
fixes=[]
for code,(d,dv,mult,c,qadj,prefix) in LOADED.items():
 if len(d)<120:continue
 idx=d.index;x=ind(d,c);ss=pd.Series(c);ma=ss.rolling(200).mean();lag=ma.shift(20);rg=np.repeat('震荡',len(d)).astype(object);rg[(ss>ma)&(ma>lag)]='牛';rg[(ss<ma)&(ma<lag)]='熊'
 for rule,st in {'自身P1_strict':(rg=='牛')|((rg=='震荡')&x['M']),'自身P2_strict':(rg=='牛')|((rg!='牛')&x['M']),'自身P3_strict':(rg!='熊')&x['M']}.items():
  n,_=book(d,dv,mult,st);fixes.append(dict(code=code,rule=rule,ann=metrics(n,idx[60:])['ann'],signal_difference=int(sum(st!=({'自身P1_strict':(env(c)=='牛')|((env(c)=='震荡')&x['M']),'自身P2_strict':(env(c)=='牛')|((env(c)!='牛')&x['M']),'自身P3_strict':(env(c)!='熊')&x['M']}[rule])))))
 j=json.load(open(P/f'data/etf_{code}_events.json'));bad=[date for date,ratio in j['spl'] if pd.Timestamp(date)<idx[0]]
 if bad:
  mm=mult.copy()
  for e in EVENTS:
   if e['code']==code and e['type']=='split' and e['reported'] in bad:mm[idx.get_loc(pd.Timestamp(e['effective']))]=1
  cc=d.close.to_numpy();adj=cc[0]*np.cumprod(np.r_[1.,(cc[1:]+dv[1:])*mm[1:]/cc[:-1]]);st=ind(d,adj)['M'];n,_=book(d,dv,mm,st)
  fixes.append(dict(code=code,rule='remove_prelisting_split',ann=metrics(n,idx[60:])['ann'],signal_difference=int(sum(st[59:]!=x['M'][59:]))))
pd.DataFrame(fixes).to_csv(O/'codex_etf15_corrections.csv',index=False)
# Calendar-year attribution of the original cohort, with partial years labelled.
years_out=[];gaps=[]
for code in [*PICK,'588170','588200']:
 d,dv,mult,c,_,_=LOADED[code];st=ind(d,c)['M'];h,_=book(d,dv,mult,np.ones(len(d),bool),cost=0);m,_=book(d,dv,mult,st)
 for rule,nav in [('hold',h),('MACD',m)]:
  ser=pd.Series(nav,index=d.index[60:]);end=ser.groupby(ser.index.year).last();prior=end.shift(1);prior.iloc[0]=1
  for year,value in (end/prior-1).items():years_out.append(dict(code=code,rule=rule,year=year,ret=value,partial_start=year==d.index[60].year,partial_end=year==2026))
 if code=='588170':
  o=d.open.to_numpy();a=None
  for k in range(60,len(d)):
   want=st[k-1]
   if not want and (k==60 or st[k-2]):a=k
   if want and a is not None:
    gaps.append(dict(sell=str(d.index[a].date()),rebuy=str(d.index[k].date()),cash_interval_price_rise=o[k]/o[a]-1));a=None
pd.DataFrame(years_out).to_csv(O/'codex_etf15_yearly.csv',index=False);pd.DataFrame(gaps).to_csv(O/'codex_etf15_588170_gaps.csv',index=False)
