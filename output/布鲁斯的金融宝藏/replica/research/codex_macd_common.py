"""Shared independent corrected ledger and indicators extracted from codex_macd16_audit.py.
No original author scripts imported. Used for new fixed-design filter study.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parents[1];END=pd.Timestamp('2026-11-10');START=pd.Timestamp('2023-01-03');COST=.001;EVENTS=[]

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

def ledger(z,st,start=START,flat=False,cost=COST):
 d=z['d'];a=max(60,d.index.searchsorted(start));cash=1.;q=0.;vals=[];dates=[];fills=[];waiting=flat
 for i in range(a,len(d)):
  want=bool(st[i-1])
  if waiting:
   # No inherited cycle: wait until next fresh MACD gold after start.
   if z['gold'][i-1]:waiting=False
   else:want=False
  D=q*z['mm'][i]*z['dv'][i]
  if q:q=q*z['mm'][i]+D/d.open.iloc[i]
  if want and q==0:q=cash*(1-cost)/d.open.iloc[i];cash=0.;fills.append((d.index[i],'buy'))
  elif not want and q:cash=q*d.open.iloc[i]*(1-cost);q=0.;fills.append((d.index[i],'sell'))
  vals.append(cash+q*d.close.iloc[i]);dates.append(d.index[i])
 return pd.Series(vals,index=dates),fills

def metric(n):
 if len(n)<2:return dict(ann=np.nan,dd=np.nan)
 return dict(ann=n.iloc[-1]**(365.25/(n.index[-1]-n.index[0]).days)-1,dd=np.min(n.to_numpy()/np.maximum.accumulate(np.r_[1,n.to_numpy()])[1:]-1))
