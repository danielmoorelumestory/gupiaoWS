"""Independent MACD/volatility audit, frozen CSVs, no original mutations.
Run: python research/codex_macd_vol_audit.py
Cash/unit matching and recursive EMA; original definitions loaded post hoc only.
FWL regression, annual asset/year fixed effects, common-start and ex-DAX
sensitivities, source-data diagnostics and vendor replacements when available.
"""
from pathlib import Path
import pandas as pd,numpy as np
import os,io,contextlib,json,hashlib
P=Path(__file__).resolve().parents[1];O=P/'research';END=pd.Timestamp('2026-11-10')
SECT=dict(zip([f'sh00099{i}' for i in range(6)],['全指消费','全指医药','金融地产','全指信息','全指通信','全指公用']))
SECT={**dict(zip([f'sh00098{i}' for i in range(6,10)],['全指能源','全指材料','全指工业','全指可选'])),**SECT}
OVER=dict(zip(['spx','ixic','dji','hsi','hstech','hscei','n225','dax','ftse','sensex','kospi'],['标普500','纳斯达克','道琼斯','恒生','恒生科技','国企指数','日经225','德国DAX','富时100','印度SENSEX','韩国KOSPI']))
NEW={**SECT,**OVER};CAL=pd.DatetimeIndex(pd.to_datetime(pd.read_csv(P/'data/index_sh000001_ohlc.csv').date))
RAW={k:pd.read_csv(P/f'data/x_{k}.csv',parse_dates=['date']).set_index('date').sort_index() for k in NEW}
def clean(d,k):
 d=d[~d.index.duplicated()].dropna(subset=['open','close']);d=d.loc[:END];d=d[(d.open>0)&(d.close>0)]
 return d[d.index.isin(CAL)] if k in SECT else d
D={k:clean(d,k) for k,d in RAW.items()}
def ema(x,n):
 x=np.asarray(x,float);v=np.empty(len(x));v[0]=x[0];a=2/(n+1)
 for i in range(1,len(x)):v[i]=v[i-1]+a*(x[i]-v[i-1])
 return v
def signal(d):
 x=d.close.to_numpy();dif=ema(x,12)-ema(x,26);return dif>ema(dif,9)
def match(d,s,a,b,cost=.001,yield_rate=0.):
 ids=np.flatnonzero((d.index>=pd.Timestamp(a))&(d.index<=pd.Timestamp(b)));units=0.;cash=1.;orders=0;entry=None;trades=[];rows=[]
 for i in ids:
  if i==0:rows.append((d.index[i],cash,False));continue
  want=bool(s[i-1]);o=d.open.iloc[i];c=d.close.iloc[i]
  # Hypothetical continuous dividend yield sensitivity, not actual dividends.
  ent=units*d.close.iloc[i-1]*np.expm1(yield_rate*(d.index[i]-d.index[i-1]).days/365.25)
  if want and not units:entry=cash;units=cash*(1-cost)/o;cash=0.;orders+=1
  elif not want and units:cash=units*o*(1-cost)+ent;units=0.;orders+=1;trades.append(cash/entry-1);entry=None
  if units:units+=ent/c
  rows.append((d.index[i],cash+units*c,bool(units)))
 n=pd.DataFrame(rows,columns=['date','nav','held']).set_index('date');years=(n.index[-1]-n.index[0]).days/365.25
 return dict(macd=n.nav.iloc[-1]**(1/years)-1,mdd=(n.nav/np.maximum(1,n.nav.cummax())-1).min(),trades=len(trades),orders=orders,win=np.mean(np.array(trades)>0) if trades else None,exposure=n.held.mean()),n
SIG={k:signal(d) for k,d in D.items()}
WINDOWS=[('2016-01-01','2018-12-31'),('2019-01-01','2021-12-31'),('2022-01-01','2024-12-31'),('2025-01-01',str(END.date()))]
def evaluate(a,b,cost=.001,datasets=None,fixed_start=False,yield_rate=0.):
 datasets=D if datasets is None else datasets;rows=[]
 for k,d in datasets.items():
  start=max(pd.Timestamp(a),pd.Timestamp('2021-03-01')) if k=='hstech' and not fixed_start else pd.Timestamp(a)
  x=d.loc[start:b]
  if start>=pd.Timestamp(b) or len(x)<120:continue
  first=d.index.get_loc(x.index[0])
  if first<250:continue
  r=d.close.pct_change();pre=r.iloc[first-250:first]
  m,n=match(d,signal(d),start,b,cost,yield_rate if k!='dax' else 0.)
  years=(x.index[-1]-x.index[0]).days/365.25;hold=x.close.iloc[-1]/x.open.iloc[0]
  if yield_rate and k!='dax':hold*=np.exp(yield_rate*years)
  hold=hold**(1/years)-1
  rows.append(dict(key=k,name=NEW[k],group='A行业' if k in SECT else '海外',start=str(x.index[0].date()),last=str(x.index[-1].date()),vol_pre=pre.std(ddof=1)*np.sqrt(250),pre_n=int(pre.count()),vol_in=r.loc[start:b].std(ddof=1)*np.sqrt(250),prior_return=d.close.iloc[first-1]/d.close.iloc[first-251]-1 if first>=251 else np.nan,hold=hold,excess=m['macd']-hold,**m))
 return pd.DataFrame(rows)
def rho(a,b):
 a=pd.Series(np.asarray(a)).rank(method='average').to_numpy(copy=True);b=pd.Series(np.asarray(b)).rank(method='average').to_numpy(copy=True);a-=a.mean();b-=b.mean();return float(a@b/np.sqrt((a@a)*(b@b)))
def reg(t,vol='vol_pre',extra=None,hold=True):
 y=t.excess.to_numpy();v=t[vol].to_numpy();W=[np.ones(len(t))]
 if hold:W.append(t.hold.to_numpy())
 if extra is not None:
  for col in extra:W.append(np.asarray(col,float))
 W=np.column_stack(W);vr=v-W@np.linalg.lstsq(W,v,rcond=None)[0];yr=y-W@np.linalg.lstsq(W,y,rcond=None)[0]
 b=float(vr@yr/(vr@vr));X=np.c_[W,v];beta=np.linalg.lstsq(X,y,rcond=None)[0];assert abs(beta[-1]-b)<1e-8
 return dict(n=len(t),rho_vol_ex=rho(v,y),b=b,c=float(beta[1]) if hold else None,rho_vol_hold=rho(v,t.hold),rank=int(np.linalg.matrix_rank(X)),condition=float(np.linalg.cond(X)))
# Independent core results completed before audited definitions are loaded.
RESULTS={};rows=[];statsrows=[]
for cost in (.001,0.):
 for name,a,b in [('full','2016-01-01',str(END.date()))]+[(f'window{i+1}',a,b) for i,(a,b) in enumerate(WINDOWS)]:
  t=evaluate(a,b,cost);RESULTS[name,cost]=t;rows.append(t.assign(period=name,cost_bp=cost*1e4))
  for vol in ('vol_pre','vol_in'):statsrows.append(dict(period=name,cost_bp=cost*1e4,vol=vol,**reg(t,vol)))
source=(O/'macd_vol_test.py').read_text();prefix=source.split('NEW = {**SECT, **OVER}')[0];ns={};cwd=os.getcwd()
try:
 os.chdir(P)
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(prefix,'original_vol_definitions','exec'),ns)
finally:os.chdir(cwd)
checks=[]
for (name,cost),t in RESULTS.items():
 a,b=('2016-01-01',str(END.date())) if name=='full' else WINDOWS[int(name[-1])-1]
 old=ns['evaluate'](list(NEW),NEW,a,b,cost).set_index('key');ours=t.set_index('key');assert set(ours.index)==set(old.index)
 for k in ours.index:
  for col in ['vol_pre','vol_in','hold','macd','excess','trades']:assert abs(ours.loc[k,col]-old.loc[k,col])<1e-10,(name,k,col)
  d=D[k];st=SIG[k];on,orders=ns['backtest'](d,pd.Series(st,index=d.index),ours.loc[k,'start'],b,cost);m,n=match(d,st,ours.loc[k,'start'],b,cost);err=float(abs(on-n.nav).max());assert err<1e-10;assert orders==m['orders'];checks.append(dict(period=name,cost_bp=cost*1e4,key=k,max_nav_error=err))
 for vol in ['vol_pre','vol_in']:
  os_=ns['stats'](old.reset_index(),vol);me=reg(t,vol)
  for c in ['rho_vol_ex','b','c','rho_vol_hold']:assert abs(os_[c]-me[c])<1e-9
# Main planned verdict, versus group FE, common-start and exclusion diagnostics.
sens=[]
for name in ['full','window1','window2','window3','window4']:
 t=RESULTS[name,.001];dummy=(t.group=='A行业').astype(int).to_numpy()
 for label,z,extra in [('original',t,None),('group_FE',t,[dummy]),('exclude_DAX',t[t.key!='dax'],None),('A_only',t[t.group=='A行业'],None),('overseas_only',t[t.group=='海外'],None)]:
  sens.append(dict(period=name,model=label,**reg(z,extra=extra)))
common=evaluate('2022-01-01',str(END.date()),fixed_start=True);rows.append(common.assign(period='common2022',cost_bp=10));sens.append(dict(period='common2022',model='original',**reg(common)));sens.append(dict(period='common2022',model='group_FE',**reg(common,extra=[(common.group=='A行业').astype(int)])))
# Other explicitly post-hoc data/cohort sensitivities.
for name in ['full','window1','window2','window3','window4']:
 t=RESULTS[name,.001];z=t[~t.key.isin(['dax','sensex'])];sens.append(dict(period=name,model='exclude_DAX_and_SENSEX',**reg(z)))
jan4=evaluate('2016-01-04',str(END.date()));rows.append(jan4.assign(period='strict_Jan4_start',cost_bp=10));sens.append(dict(period='strict_Jan4_start',model='original',**reg(jan4)))
def fe_basis(frame):
 # Center dummy columns, then retain only their independent column space.
 # This avoids redundant asset/group-year dummy columns without altering fit.
 a=pd.get_dummies(frame.astype(str),drop_first=True,dtype=float).to_numpy(copy=True);a-=a.mean(axis=0)
 u,s,_=np.linalg.svd(a,full_matrices=False);return u[:,s>s[0]*1e-10]
# Annual non-overlapping panel, own prior-250 volatility (no pooled level proxy).
panel=[]
for year in range(2016,2027):
 a=f'{year}-01-01';b=min(pd.Timestamp(f'{year}-12-31'),END)
 t=evaluate(a,str(b.date()),fixed_start=True)
 panel.append(t.assign(year=year))
panel=pd.concat(panel,ignore_index=True);panelrows=[]
for label,z in [('all_years',panel),('through2025',panel[panel.year<2026]),('ex_DAX',panel[panel.key!='dax']),('A_only',panel[panel.group=='A行业']),('overseas_only',panel[panel.group=='海外'])]:
 fe=fe_basis(z[['key','year']])
 for model,usehold,extra in [('asset_year_FE_and_realized_hold',True,list(fe.T)),('asset_year_FE_only',False,list(fe.T)),('asset_year_FE_and_prior_return',False,list(fe.T)+[z.prior_return.fillna(0).to_numpy()])]:
  panelrows.append(dict(sample=label,model=model,**reg(z,extra=extra,hold=usehold)))
# Asset FE plus market-group x year FE controls different regional regimes.
for label,z in [('all_years',panel),('through2025',panel[panel.year<2026])]:
 z=z.copy();z['group_year']=z.group+'_'+z.year.astype(str)
 fe=fe_basis(z[['key','group_year']])
 for model,usehold,extra in [('asset_groupyear_FE_and_realized_hold',True,list(fe.T)),('asset_groupyear_FE_and_prior_return',False,list(fe.T)+[z.prior_return.fillna(0).to_numpy()])]:
  panelrows.append(dict(sample=label,model=model,**reg(z,extra=extra,hold=usehold)))
# Hypothetical constant dividend yield, on unchanged signals; DAX not topped up.
divrows=[]
for yld in (0.,.015,.03):
 t=evaluate('2016-01-01',str(END.date()),yield_rate=yld);divrows.append(t.assign(assumed_yield=yld))
# Data diagnostics: raw vs after cutoff/clean, not silently deleting anomalies.
data=[]
for k,d in RAW.items():
 z=D[k];x=z.loc['2016':];badopen=(x.open>x.high+.01)|(x.open<x.low-.01);badclose=(x.close>x.high+.01)|(x.close<x.low-.01)
 noncal=d.loc[~d.index.isin(CAL)] if k in SECT else d.iloc[:0]
 data.append(dict(key=k,name=NEW[k],raw_first=str(d.index[0].date()),raw_last=str(d.index[-1].date()),raw_rows=len(d),post_cutoff=int(sum(d.index>END)),clean_last=str(z.index[-1].date()),clean_rows=len(z),duplicates=int(d.index.duplicated().sum()),open_close_equal=int((x.open==x.close).sum()),bad_open_over_001=int(badopen.sum()),bad_close_over_001=int(badclose.sum()),bad_open_dates=x.index[badopen].astype(str).tolist(),equal_dates=x.index[x.open==x.close].astype(str).tolist(),noncal_dates=noncal.index.astype(str).tolist(),missing_trade_dates=len(CAL[(CAL>=z.index[0])&(CAL<=z.index[-1])].difference(z.index)) if k in SECT else None))
# Vendor sensitivity. Other vendor covers US/HK since 2010 and global recent
# 1000 rows. Replacements are a diagnostic, not an assertion of ground truth.
vendors={'em_spx':'spx','em_dji':'dji','em_hsi':'hsi','em_hscei':'hscei','sina_dax':'dax','sina_ftse':'ftse','sina_sensex':'sensex','sina_n225':'n225','sina_kospi':'kospi'};vendorrows=[];ALT={k:d.copy() for k,d in D.items()}
for label,k in vendors.items():
 path=O/f'codex_vol_{label}.csv'
 if not path.exists():continue
 v=pd.read_csv(path,parse_dates=['date']).set_index('date');v=v[~v.index.duplicated()].sort_index().loc[:END];v=v[['open','close']].apply(pd.to_numeric,errors='coerce').dropna();v=v[(v.open>0)&(v.close>0)];idx=D[k].index.intersection(v.index);idx=idx[idx>=pd.Timestamp('2016-01-01')]
 for col in ['open','close']:
  err=(D[k].loc[idx,col]-v.loc[idx,col]).abs();vendorrows.append(dict(key=k,source=label,column=col,overlap=len(idx),first=str(idx[0].date()),last=str(idx[-1].date()),max_abs_error=err.max(),median_abs_error=err.median(),gt_001=int((err>.01).sum()),largest_dates=err.nlargest(5).index.astype(str).tolist()))
 ALT[k].loc[idx,['open','close']]=v.loc[idx,['open','close']]
altt=evaluate('2016-01-01',str(END.date()),datasets=ALT);rows.append(altt.assign(period='vendor_sensitivity',cost_bp=10));sens.append(dict(period='vendor_sensitivity',model='original',**reg(altt)))
# Exclude rows with suspect opens entirely (changes local trading clock) ONLY
# as an additional diagnostic; high/low not used in trading signals.
DROP={k:d.drop(d.index[((d.open>d.high+.01)|(d.open<d.low-.01))&(d.index>=pd.Timestamp('2016'))]) for k,d in D.items()};dropt=evaluate('2016-01-01',str(END.date()),datasets=DROP);rows.append(dropt.assign(period='drop_suspect_open',cost_bp=10));sens.append(dict(period='drop_suspect_open',model='original',**reg(dropt)))
pd.concat(rows,ignore_index=True).to_csv(O/'codex_macd_vol_results.csv',index=False);pd.DataFrame(statsrows).to_csv(O/'codex_macd_vol_stats.csv',index=False);pd.DataFrame(checks).to_csv(O/'codex_macd_vol_comparison.csv',index=False);pd.DataFrame(sens).to_csv(O/'codex_macd_vol_sensitivity.csv',index=False);panel.to_csv(O/'codex_macd_vol_panel.csv',index=False);pd.DataFrame(panelrows).to_csv(O/'codex_macd_vol_panel_models.csv',index=False);pd.concat(divrows).to_csv(O/'codex_macd_vol_dividends.csv',index=False);pd.DataFrame(data).to_csv(O/'codex_macd_vol_data.csv',index=False);pd.DataFrame(vendorrows).to_csv(O/'codex_macd_vol_vendor.csv',index=False)
meta=dict(original_sha256=hashlib.sha256(source.encode()).hexdigest(),input_sha256={k:hashlib.sha256((P/f'data/x_{k}.csv').read_bytes()).hexdigest() for k in NEW},compared_paths=len(checks),max_nav_error=max(x['max_nav_error'] for x in checks),hstech_march2021_prior_rows=int(D['hstech'].index.searchsorted(pd.Timestamp('2021-03-01'))),hstech_first_with_250_prior_returns=str(D['hstech'].index[251].date()),cutoff=str(END.date()),planned_verdict={})
for cost in (.001,0.):
 bs=[x['b'] for x in statsrows if x['cost_bp']==cost*1e4 and x['vol']=='vol_pre' and x['period']!='full'];full=next(x['b'] for x in statsrows if x['cost_bp']==cost*1e4 and x['vol']=='vol_pre' and x['period']=='full');positive=sum(v>0 for v in bs);meta['planned_verdict'][str(cost)]=dict(full_b=full,positive_windows=positive,verdict='支持' if full>0 and positive>=3 else '不支持' if full<=0 else '不一致')
(O/'codex_macd_vol_diagnostics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,default=str));print(pd.DataFrame(statsrows).to_string(index=False));print('Sensitivity',pd.DataFrame(sens).to_string(index=False));print('Panel',pd.DataFrame(panelrows).to_string(index=False));print('Independent prices, states, NAV, OLS/Spearman and verdict matched.')
