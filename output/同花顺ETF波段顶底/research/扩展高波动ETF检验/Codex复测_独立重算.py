"""离线独立复核；不导入两份红利分母实验脚本。运行：python3 -B Codex复测_独立重算.py"""
import sys, json, gzip, csv, io, math, statistics, importlib.util, re, hashlib
from pathlib import Path
from bisect import bisect_right
sys.dont_write_bytecode = True
ROOT = Path.cwd(); START='2020-01-02'; END='2026-11-10'
# 强制离线；任何新增/写入文件必须在当前目录且以规定前缀命名。
def guard(event,args):
    if event == 'socket.connect': raise RuntimeError('离线复测禁止网络')
    if event == 'open':
        p,mode,flags=args
        if isinstance(p,(str,bytes)) and ((isinstance(mode,str) and any(x in mode for x in 'wax+')) or flags & (64|512|1024|1|2)):
            q=Path(p).resolve()
            if q.parent != ROOT or not q.name.startswith('Codex复测_'): raise RuntimeError('禁止写入已有文件/外部文件: '+str(q))
sys.addaudithook(guard)
def raw(code):
    sym=('sz' if code.startswith('15') else 'sh')+code
    return {r[0]:float(r[2]) for r in json.loads(gzip.decompress((ROOT/f'data/raw/{sym}-tencent-hfq.json.gz').read_bytes())) if r[0]<=END}
def research(code):
    return {r['date']:float(r['adjusted_close']) for r in csv.DictReader(io.StringIO(gzip.decompress((ROOT/f'data/{code}.csv.gz').read_bytes()).decode())) if r['date']<=END}
SETS={'D0h':['510880'],'红利4':['510880','515080','515180','159905'],'前二':['510880','512890'],'512890':['512890'],'红利7':['510880','515080','515180','159905','512890','515100','515450']}
def denom(members, corrected=False):
    prices={c:raw(c) for c in set(members+['510880'])}
    eligible={c:sorted(prices[c])[19 if corrected else 20] for c in members}
    days=sorted(prices['510880']); nav=1.; out={days[0]:nav}
    for j in range(1,len(days)):
        prev,day=days[j-1:j+1]
        active=[c for c in members if eligible[c]<=prev and prev in prices[c] and day in prices[c]] or ['510880']
        nav*=sum(prices[c][day]/prices[c][prev] for c in active)/len(active)
        out[day]=nav
    return out
# 分子沿用研究定义；另算创业板分子也换腾讯的敏感性。
HS={r['day'][:10]:float(r['close']) for r in json.loads(gzip.decompress(Path('data/raw/sh000300-sina-index.json.gz').read_bytes())) if r['day'][:10]<=END}
def state(num,den):
    days=sorted(num.keys() & den.keys()); ratios=[num[d]/den[d] for d in days]
    return {d:(ratios[i]>sum(ratios[i-19:i+1])/20 if i>=19 else None) for i,d in enumerate(days)}
def align(s,days):
    keys=sorted(s)
    return [True if (j:=bisect_right(keys,d)-1)<0 or s[keys[j]] is None else s[keys[j]] for d in days]
D={'D0':research('510880'),**{k:denom(v) for k,v in SETS.items()}}
SIG={side:{k:state(num,den) for k,den in D.items()} for side,num in [('R2',research('159915')),('H1',HS)]}
SIGNAL=[]
for side,ss in SIG.items():
    base=ss['D0']
    for key,s in ss.items():
        days=[d for d in sorted(s) if START<=d<=END and s[d] is not None]
        flips=sum(s[a]!=s[b] for a,b in zip(days,days[1:])); same=sum(s[d]==base.get(d) for d in days)
        years={y:sum(s[a]!=s[b] for a,b in zip(days,days[1:]) if b[:4]==y) for y in sorted({d[:4] for d in days})}
        SIGNAL.append(dict(side=side,key=key,n=len(days),bull=sum(s[d] for d in days),bull_pct=100*sum(s[d] for d in days)/len(days),flips=flips,annual=flips*244/len(days),same=same,same_pct=100*same/len(days),year_flips=years))
print('信号重算完成', flush=True)
# 加载允许复用的引擎，独立接入信号和配置。
spec=importlib.util.spec_from_file_location('audit_index','指数延长回测.py'); X=importlib.util.module_from_spec(spec);spec.loader.exec_module(X)
C=X.C; groups=json.loads(Path('全量逐年优秀AB_最终分组.json').read_text()); C.init()
PANEL={k[1:]:v for k,v in C.T.M.PANEL.items()}
def daily(nav):
    ds=sorted(nav);return {ds[i]:nav[ds[i]]/nav[ds[i-1]]-1 for i in range(1,len(ds))}
def portfolio(navs):
    returns=[daily(n) for n in navs];days=sorted({d for r in returns for d in r if START<=d<=END});nav=1.;out={}
    for d in days:
        vals=[r[d] for r in returns if d in r];nav*=1+sum(vals)/len(vals);out[d]=nav
    return out
def metric(nav):
    values=[nav[d] for d in sorted(nav)];peak=1.;dd=0.
    for v in values:peak=max(peak,v);dd=min(dd,v/peak-1)
    ann=values[-1]**(244/len(values))-1
    return dict(cagr=ann,mdd=dd,cal=ann/abs(dd) if dd else math.inf)
RESULT=[]; SIMPLE=[]; DETAILS={}; TRADECHECK=[]; DATA=[]
def simple(rows,sig,begin_at_2020=False):
    """独立浮点 EMA，原始成交价、拆分和分红现金账户，T+1，末日清仓。"""
    close=[float(r['adjusted_close']) for r in rows]; fast=slow=close[0]; dea=0.;prior=0.;gold=[];dead=[]
    for v in close:
        fast+=(v-fast)*2/13;slow+=(v-slow)*2/27;dif=fast-slow;dea+=(dif-dea)*2/10;h=dif-dea
        gold.append(prior<=0 and h>0);dead.append(prior>=0 and h<0);prior=h
    dates=[r['date'] for r in rows];reg=align(sig,dates)
    valid=[i for i,d in enumerate(dates) if i>=120 and (not begin_at_2020 or d>=START) and d<=END]
    cash=1.;reserve=q=0.;pending=None;bought=-1;nav={};end=valid[-1]
    for i in valid:
        r=rows[i];op=float(r['open']);cl=float(r['close'])
        if q and i>valid[0]:
            reserve+=q/float(rows[i-1]['share_factor'])*(float(r['cumulative_cash'])-float(rows[i-1]['cumulative_cash']))
            q*=float(r['share_factor'])/float(rows[i-1]['share_factor'])
        if pending=='buy':q=cash/(op*1.001);cash=0.;bought=i
        elif pending=='sell':cash=q*op*.999;q=0.
        pending=None;sold=False
        if q and ((dead[i] and bought!=i) or i==end):cash=q*cl*.999;q=0.;sold=True
        nav[dates[i]]=cash+reserve+q*cl
        if i==end or sold:continue
        if q and dead[i]:pending='sell'
        elif not q and gold[i] and reg[i]:pending='buy'
    return nav,gold,dead
for mode in ['ETF','指数']:
    navs={}
    for group in ['A','B']:
        for code in groups[group]:
            d=PANEL[code] if mode=='ETF' or code not in X.INDEX else X.entry(code,X.index_rows(X.INDEX[code]),SIG['R2']['D0'],SIG['H1']['D0'])
            DATA.append(dict(mode=mode,group=group,code=code,index=X.INDEX.get(code) if mode=='指数' else None,first=d['dates'][0],last=d['dates'][-1]))
            side='R2' if group=='A' else 'H1'
            for key,s in SIG[side].items():
                name='Codex:'+side+':'+key;d['reg'][name]=align(s,d['dates'])
                if group=='A':
                    cfg={**C.Y.VAR['Y1'],'N':name}; r=C.Y.simulate_y(d,cfg,C.FULL,20,retain=True)
                else:
                    cfg={**C.T.BASE,'N':name};r=C.K.simulate_kd(d,cfg,C.FULL,20,retain=True)
                nav={p['date']:p['nav'] for p in r['nav']};navs[(code,key)]=nav
                for t in r['trades']:
                    if t['forced_end']:continue
                    assert t['entry_index']==t['entry_signal_index']+1
                    assert d['reg'][name][t['entry_signal_index']]
                    assert t['exit_index']==t['exit_signal_index'] or (t['exit_signal_index']==t['entry_index'] and t['exit_index']==t['entry_index']+1)
                if mode=='ETF' and group=='B' and key in ['D0','前二','红利7']:
                    sn,g,x=simple(d['rows'],s); refg,refx=d['macds'][(12,26,9)]
                    maxdiff=max(abs(sn[day]-nav[day]) for day in nav)
                    sn0,_,_=simple(d['rows'],s,True)
                    SIMPLE.append(dict(code=code,key=key,max_nav_diff=maxdiff,macd_diff=sum(a!=b for a,b in zip(g,refg))+sum(a!=b for a,b in zip(x,refx))))
                    DETAILS[(code,key)]=(sn,sn0)
            print(mode,group,code,'完成',flush=True)
        for key in D:
            ns=[navs[(code,key)] for code in groups[group]]
            m=metric(portfolio(ns)); wrong=statistics.mean(C.metrics({d:v for d,v in n.items() if START<=d<=END})['cal'] for n in ns)
            fixed=statistics.mean(metric(portfolio([n]))['cal'] for n in ns)
            RESULT.append(dict(mode=mode,group=group,key=key,**m,single_original=wrong,single_fixed=fixed))
CROSS=[]
for key in ['D0','前二','红利7']:
    for fresh in [False,True]:
        CROSS.append(dict(key=key,fresh=fresh,**metric(portfolio([DETAILS[(code,key)][int(fresh)] for code in groups['B']]))))
# 额外敏感性：第20日收盘后准入，以及创业板分子全腾讯。
SENS=[]
for side,num in [('R2',research('159915')),('H1',HS)]:
    for key,members in SETS.items():
        corrected=state(num,denom(members,True));old=SIG[side][key]
        dif=[d for d in old if START<=d<=END and old[d]!=corrected.get(d)]
        SENS.append(dict(side=side,key=key,admission_diff_dates=dif))
for key,den in D.items():
    alt=state(raw('159915'),den);old=SIG['R2'][key]
    SENS.append(dict(side='R2腾讯分子',key=key,diff_dates=[d for d in old if START<=d<=END and old[d]!=alt.get(d)]))
# 自动逐项对比两份历史输出的显示精度。
COMPARE=[]
labels={'现行 510880':'D0','510880 后复权':'D0h','红利4只均值':'红利4','红利+红利低波':'前二','红利7只均值':'红利7','只用红利低波':'512890','510880+512890':'前二'}
for fn in ['红利均值分母择时对照输出.txt','红利成交前二分母择时对照输出.txt']:
    mode=group=None;section='signal'
    for line in Path(fn).read_text().splitlines():
        if line.startswith('## '):
            section='2020' if line.startswith(('## 1)','## 2)')) else 'other';mode='ETF' if line.startswith('## 1)') else '指数'
        if '[A 组' in line:group='A'
        if '[B 组' in line:group='B'
        if '牛市天数' in line:
            side='R2' if '创业板' in line else 'H1';label=line.split('÷')[1].split('牛市天数')[0].strip();key=labels[label]
            orig=[float(x) for x in re.findall(r'牛市天数\s*([\d.]+)|每年切换\s*([\d.]+)|与现行同向\s*([\d.]+)',line) for x in x if x]
            r=next(r for r in SIGNAL if r['side']==side and r['key']==key);vals=[r['bull_pct'],r['annual'],r['same_pct']]
            COMPARE.append(dict(file=fn,type='signal',side=side,key=key,original=orig,computed=vals,match=[round(a,1)==b for a,b in zip(vals,orig)]))
        if section=='2020' and '组合 年化' in line:
            label=line.split('组合 年化')[0].strip();key=labels[label]
            orig=[float(x) for x in re.findall(r'年化\s*([-\d.]+)%|回撤\s*([-\d.]+)%|卡玛\s*([-\d.]+)',line) for x in x if x]
            r=next(r for r in RESULT if r['mode']==mode and r['group']==group and r['key']==key);vals=[r['cagr']*100,r['mdd']*100,r['cal'],r['single_original']]
            COMPARE.append(dict(file=fn,type='backtest',mode=mode,group=group,key=key,original=orig,computed=vals,match=[round(a,p)==b for a,b,p in zip(vals,orig,[1,1,2,2])]))
# 成员准入修正后完整复跑红利7 B组，量化那一天的影响。
ADMISSION=[]
corrected_h1=state(HS,denom(SETS['红利7'],True))
for mode in ['ETF','指数']:
    ns=[]
    for code in groups['B']:
        d=PANEL[code] if mode=='ETF' or code not in X.INDEX else X.entry(code,X.index_rows(X.INDEX[code]),SIG['R2']['D0'],SIG['H1']['D0'])
        d['reg']['Codex:admission']=align(corrected_h1,d['dates'])
        r=C.K.simulate_kd(d,{**C.T.BASE,'N':'Codex:admission'},C.FULL,20,retain=True)
        ns.append({p['date']:p['nav'] for p in r['nav']})
    ADMISSION.append(dict(mode=mode,**metric(portfolio(ns))))
# last_known 的具体因果反例测试；未形成信号时按牛也是预设行为。
TESTS=[]
for sm,ds in [({'2020-01-03':False},['2020-01-01','2020-01-03','2020-01-06']),
              ({'2020-01-01':False,'2020-01-06':True},['2020-01-02','2020-01-03','2020-01-06']),
              ({'2020-01-01':None,'2020-01-06':False},['2020-01-01','2020-01-02','2020-01-06'])]:
    actual=X.RM.last_known(sm,ds); expected=align(sm,ds);assert actual==expected
    TESTS.append(dict(signal=sm,dates=ds,actual=actual))
CACHE=[]
for c in sorted({X.INDEX[c] for c in groups['A']+groups['B'] if c in X.INDEX}):
    rows=json.loads(gzip.decompress(Path(f'data/index_raw/{c}.json.gz').read_bytes()))['data']
    rows=[r for r in rows if '20200102'<=r['tradeDate']<='20261110' and r.get('close') and float(r['close'])>0]
    CACHE.append(dict(index=c,rows=len(rows),missing_open=sum(not r.get('open') or float(r['open'])<=0 for r in rows)))
MEMBERS=[dict(code=c,first=sorted(raw(c))[0],twentieth=sorted(raw(c))[19],claude_threshold=sorted(raw(c))[20]) for c in SETS['红利7']]
CALENDAR=dict(r2_missing_vs_h1=sorted(set(d for d in SIG['H1']['D0'] if START<=d<=END)-set(SIG['R2']['D0'])),h1_d0_vs_d0h=[d for d in SIG['H1']['D0'] if START<=d<=END and SIG['H1']['D0'][d]!=SIG['H1']['D0h'].get(d)])
OUT=dict(admission_backtests=ADMISSION,causal_tests=TESTS,index_cache=CACHE,members=MEMBERS,calendar=CALENDAR,signals=SIGNAL,backtests=RESULT,simple=CROSS,simple_checks=SIMPLE,data=DATA,sensitivity=SENS,comparison=COMPARE,groups=groups)
Path('Codex复测_重算结果.json').write_text(json.dumps(OUT,ensure_ascii=False,indent=2))
print('全部完成；比较项',len(COMPARE),'不一致',sum(not all(x['match']) for x in COMPARE),flush=True)
