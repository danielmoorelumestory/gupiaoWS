"""「只认金叉 + 沪深300÷红利」年化明显提升且收益高的 ETF 筛选。事前写定（跑之前）：
样本：研究面板全部 ETF（原主池 61 只 + 池外 10 只）。全历史（上市后第 121 根起至 2026-11-10）。
规则：现行（择时牛市金叉次日开盘买、熊市不开新仓、死叉尾盘卖），择时分别为 R2（创业板÷红利）与 H1（沪深300÷红利），均高于 20 日均线为牛。
入选（全部满足）：回测期 ≥3 年；H1 年化 − R2 年化 ≥ 3 个百分点；H1 年化 ≥ 10%。按年化提升从高到低排序。
【2026-11-18 起不再使用】现行分组见 网页口径重新分组.py（网页回测口径、只算已平仓、归组按逐年平均→年化→盈利年份/波动→回撤）。本文件保留作历史记录。"""
import json, csv, importlib.util
sp = importlib.util.spec_from_file_location("Z", "低波动沪深300择时对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
if __name__ == "__main__":
    names = {r["代码"]: r["名称"] for r in csv.DictReader(open("../Claude逐只复测61ETF/claude/per_etf_61_brief.csv"))}
    names.update({i["code"]: i["name"] for i in json.load(open("MACD优秀清单_20只.json"))["items"]})
    extra = {"159915": "创业板ETF易方达", "159949": "创业板50ETF华安", "159939": "信息技术ETF广发", "515030": "新能源车ETF华夏", "515050": "5G通信ETF华夏", "515980": "人工智能ETF华富", "159967": "创业板成长ETF华夏", "512670": "国防ETF鹏华"}
    for k, v in extra.items(): names.setdefault(k, v)
    Z.init(); rows = []
    for key, d in Z.T.M.PANEL.items():
        r2 = Z.K.simulate_kd(d, Z.VAR["现行·R2"], Z.FULL, 20); h1 = Z.K.simulate_kd(d, Z.VAR["现行·H1"], Z.FULL, 20); pm = Z.K.simulate_kd(d, Z.VAR["纯MACD"], Z.FULL, 20)
        if not r2 or r2["metric"]["cagr"] is None: continue
        a, b = r2["metric"], h1["metric"]; code = key[1:]
        ok = a["years"] >= 3 and b["cagr"] - a["cagr"] >= .03 and b["cagr"] >= .10
        rows.append(dict(code=code, name=names.get(code, ""), start=a["first"], years=round(a["years"], 1), r2Annual=round(a["cagr"]*100, 2), hs300Annual=round(b["cagr"]*100, 2),
                         liftAnnual=round((b["cagr"]-a["cagr"])*100, 2), r2Drawdown=round(a["mdd"]*100, 2), hs300Drawdown=round(b["mdd"]*100, 2), macdAnnual=round(pm["metric"]["cagr"]*100, 2), trades=b["entries"] if "entries" in b else None, good=ok))
    rows.sort(key=lambda r: -r["liftAnnual"])
    print(f"样本 {len(rows)} 只（有年化）；回测≥3年 {sum(r['years']>=3 for r in rows)}；提升≥3pp {sum(r['liftAnnual']>=3 for r in rows)}；H1≥10% {sum(r['hs300Annual']>=10 for r in rows)}；入选 {sum(r['good'] for r in rows)}")
    for r in rows:
        if r["good"] or r["liftAnnual"] >= 3: print(f"{'★' if r['good'] else ' '} {r['code']} {r['name']:<14} {r['start']} {r['years']:4.1f}年  创业板 {r['r2Annual']:6.2f}%/{r['r2Drawdown']:6.1f}%  沪深300 {r['hs300Annual']:6.2f}%/{r['hs300Drawdown']:6.1f}%  提升 {r['liftAnnual']:+6.2f}  纯MACD {r['macdAnnual']:6.2f}%")
    json.dump(rows, open("沪深300择时优选_全部结果.json", "w"), ensure_ascii=False, indent=1)
