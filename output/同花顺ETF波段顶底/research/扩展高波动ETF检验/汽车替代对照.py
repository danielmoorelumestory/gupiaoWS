"""用户要求（2026-11-18）：观察池里「汽车 516110」改成汽车零部件等 ETF 试一下。事前写定：
候选：汽车零部件 562700/159565/512740/159306，智能汽车 515250/159888，对照 汽车 516110、智能驾驶 516520（已在观察池）。腾讯后复权数据，指数延长回测.entry 构建。
每只报：上市日、当前成交额、年化波动、A/B 两套全历史与 2020 年起（上市后）年化/回撤/卡玛、逐年；按 2021 年前规则选的方案；
与 机器人 562500、智能驾驶 516520、电池 159755 的日收益相关（看是否重复）。历史统计，不构成投资建议。"""
import importlib.util, json, gzip, math, statistics, urllib.request
sp = importlib.util.spec_from_file_location("W", "行业观察池导出网页.py"); W = importlib.util.module_from_spec(sp); sp.loader.exec_module(W)
C, X = W.C, W.X
CANDS = ["562700", "159565", "512740", "159306", "515250", "159888", "516110", "516520"]
def amt(c):
    try: return float(urllib.request.urlopen(f"https://qt.gtimg.cn/q={'sh' if c[0]=='5' else 'sz'}{c}", timeout=8).read().decode("gbk").split("~")[37])
    except Exception: return -1
def lr(d):
    a = [float(r["adjusted_close"]) for r in d["rows"]]; return {d["dates"][i]: math.log(a[i]/a[i-1]) for i in range(1, len(a)) if a[i-1] > 0}
if __name__ == "__main__":
    C.init(); ref = {c: lr(W.data_of(c)) for c in ("562500", "516520", "159755")}
    for c in CANDS:
        d = W.data_of(c)
        if W.run(d, 'A') is None: print(f'\n{c} 上市 {d["dates"][0]}，不足 121 根日线，跳过'); continue
        R = lr(d); vol = statistics.pstdev(list(R.values()))*math.sqrt(244); pl = W.choose(d)
        cor = " ".join(f"{k}:{statistics.correlation([R[t] for t in R if t in v], [v[t] for t in R if t in v]):.2f}" for k, v in ref.items() if k != c and sum(1 for t in R if t in v) > 120)
        print(f"\n{c} 上市 {d['dates'][0]} 成交额 {amt(c)/10000:.2f} 亿 波动 {vol*100:.0f}% 规则选 {pl} ｜相关 {cor}")
        for p in "AB":
            nav = {x["date"]: x["nav"] for x in W.run(d, p)["nav"]}; m = C.window_metrics(nav, ("1900-01-01", X.END))
            print(f"   {p}: 年化 {m['cagr']*100:6.1f}% 回撤 {m['mdd']*100:6.1f}% 卡玛 {m['cal']:5.2f} ｜ " + " ".join(f"{y[2:]}:{v*100:+.0f}" for y, v in m["years"].items()))
