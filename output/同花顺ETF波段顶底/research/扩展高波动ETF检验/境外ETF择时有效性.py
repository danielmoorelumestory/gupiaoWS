"""用户观点（2026-11-18）：与 A 股无关的（美股、港股、商品）不应套用 A/B 策略的 A 股择时。事前写定（跑之前）：
对面板中的境外/商品 ETF，比较：策略A（Y1+创业板÷510880 择时）、策略B（只认金叉+沪深300÷510880 择时）、
以及去掉择时的同一买卖规则（Y1·不择时、只认金叉·不择时：择时恒为牛）。
另把 A 股 ETF 作为对照组做同样比较，看择时对 A 股是否有效、对境外是否无效。
判断（事先定）：若境外 ETF 上「带择时」相对「不择时」的卡玛提升中位数 ≤0，而 A 股上明显 >0，则认为 A 股择时对境外无效，应把境外 ETF 单独处理。
窗口 2020-01-02 起与全历史，单只用 C.window_metrics。历史统计，不构成投资建议。"""
import importlib.util, statistics
from multiprocessing import Pool
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
import json
FG = json.load(open("全量逐年优秀AB_最终分组.json")); AB = set(FG["A"]) | set(FG["B"])
OVER = {"159509": "纳指科技", "513100": "纳指", "513290": "纳指生物科技", "159529": "标普消费", "159518": "标普油气", "513310": "中韩半导体",
        "513090": "香港证券", "513130": "恒生科技", "159792": "港股通互联网", "159636": "港股通科技30", "159131": "港股通信息技术", "513050": "中概互联网",
        "159892": "恒生医药", "513120": "港股创新药", "513190": "港股通金融", "513750": "港股通非银", "513630": "港股低波红利", "159920": "恒生", "518880": "黄金"}
def job(key):
    C.init(); d = C.T.M.PANEL[key]; d["reg"]["恒牛"] = [True]*len(d["dates"]); out = {}
    for n, f in {"A择时": lambda: C.Y.simulate_y(d, C.Y.VAR["Y1"], C.FULL, 20, retain=True), "A不择时": lambda: C.Y.simulate_y(d, {**C.Y.VAR["Y1"], "N": "恒牛"}, C.FULL, 20, retain=True),
                 "B择时": lambda: C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True), "B不择时": lambda: C.K.simulate_kd(d, {**C.T.BASE, "N": "恒牛"}, C.FULL, 20, retain=True)}.items():
        r = f(); out[n] = {p["date"]: p["nav"] for p in r["nav"]} if r else {}
    return key[1:], out
if __name__ == "__main__":
    C.init(); P = {k[1:]: v for k, v in C.T.M.PANEL.items()}
    with Pool(8) as p: res = dict(p.map(job, list(C.T.M.PANEL)))
    for W in (("2020-01-02", X.END), ("1900-01-01", X.END)):
        print(f"\n######## 窗口 {W[0]} 起")
        for title, codes in (("境外/商品", [c for c in OVER if c in res]), ("A 股", [c for c in res if c not in OVER])):
            dA, dB = [], []
            if title == "境外/商品": print(f"## 境外/商品逐只（卡玛）  A择时 / A不择时 ｜ B择时 / B不择时")
            for c in codes:
                m = {k: C.window_metrics(res[c][k], W) for k in res[c]}
                if not all(m.values()) or sum(1 for t in res[c]["A择时"] if t >= W[0]) < 244: continue
                dA.append(m["A择时"]["cal"] - m["A不择时"]["cal"]); dB.append(m["B择时"]["cal"] - m["B不择时"]["cal"])
                if title == "境外/商品":
                    tag = "（现行A/B成员）" if c in AB else ""
                    print(f"  {c} {OVER[c]:<10}{tag:<10} A: {m['A择时']['cal']:5.2f} / {m['A不择时']['cal']:5.2f} (年化 {m['A择时']['cagr']*100:5.1f}% / {m['A不择时']['cagr']*100:5.1f}%) ｜ B: {m['B择时']['cal']:5.2f} / {m['B不择时']['cal']:5.2f} (年化 {m['B择时']['cagr']*100:5.1f}% / {m['B不择时']['cagr']*100:5.1f}%)")
            if dA:
                print(f"## {title}（{len(dA)} 只）择时带来的卡玛提升：A 中位数 {statistics.median(dA):+.2f}、提升占比 {sum(x>0 for x in dA)/len(dA)*100:.0f}% ｜ B 中位数 {statistics.median(dB):+.2f}、提升占比 {sum(x>0 for x in dB)/len(dB)*100:.0f}%")
