"""Export corrected A20 entry qualification for Artifact integration.
Only exports local last completed bar; never labels it live data.
"""
import json,math
import numpy as np,pandas as pd
from codex_macd_common import P,load,indicators,wilder
O=P/'research';th=pd.read_csv(O/'codex_filter17_thresholds.csv').set_index('year');rows=[]
def num(x):return float(x) if np.isfinite(x) else None
for code,name,group in json.load(open(P/'data/page_etfs_plus.json')):
 d,dv,mm,c=load(code);f,m,gold,dead=indicators(d,c);factor=c/d.close.to_numpy();hi=d.high.to_numpy()*factor;lo=d.low.to_numpy()*factor;prev=np.r_[np.nan,c[:-1]];atr=wilder(np.maximum(hi-lo,np.maximum(abs(hi-prev),abs(lo-prev))));score=f['hist'].to_numpy()*c/atr;available=np.flatnonzero(gold&(np.arange(len(d))>=60));b=int(available[-1]) if len(available) else None
 threshold=float(th.loc[d.index[b].year,'amplitude20']) if b is not None and d.index[b].year in th.index else np.nan;qualified=bool(score[b]>=threshold) if b is not None and np.isfinite(threshold) else None
 rows.append(dict(code=code,name=name,group=group,asOf=str(d.index[-1].date()),macdBullish=bool(m[-1]),newGoldToday=bool(gold[-1]),lastGoldDate=str(d.index[b].date()) if b is not None else None,goldGapAtr=num(score[b]) if b is not None else None,goldThreshold=num(threshold),goldPassed=qualified,cycleQualified=bool(m[-1] and qualified is True),currentGapAtr=num(score[-1])))
out=dict(asOf=max(x['asOf'] for x in rows),method='A20',definition='(DIF-DEA)/ATR14 on gold-cross closing bar; entry next open; exit next open after dead cross',thresholdMethod='Previous 3 complete calendar years closed MACD cycles, 20th percentile, frozen each calendar year; entry-cycle threshold frozen at gold date',status='Research candidate; historical improvement not robustly established',rows=rows)
(O/'codex_filter17_artifact_data.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False));assert len(rows)==63;print('Exported',len(rows),'rows, asOf',out['asOf'],'bullish',sum(x['macdBullish'] for x in rows),'cycle pass',sum(x['cycleQualified'] for x in rows),'new gold',sum(x['newGoldToday'] for x in rows))
