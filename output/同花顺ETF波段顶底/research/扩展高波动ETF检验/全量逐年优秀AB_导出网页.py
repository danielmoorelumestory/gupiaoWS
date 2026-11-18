"""把 全量逐年优秀AB_最终分组.json 导出为 BusinessWeb 两个回测分组的数据文件（创业板择时优选 = A 组；沪深300择时优选 = B 组）。
【2026-11-18 起不再使用】现行分组见 网页口径重新分组.py（网页回测口径、只算已平仓、归组按逐年平均→年化→盈利年份/波动→回撤）。本文件保留作历史记录。"""
import json, sys, importlib.util
from multiprocessing import Pool
spec = importlib.util.spec_from_file_location("S", "全量逐年优秀AB筛选.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
OUT = "/Users/train/work/gupiaoWS/BusinessWeb/.worktrees/band-indicator/src/data/"
NAMES = {"513310": "中韩半导体ETF华泰柏瑞", "588200": "科创芯片ETF嘉实", "159869": "游戏ETF华夏", "159851": "金融科技ETF华宝", "512760": "芯片ETF国泰",
         "159819": "人工智能ETF易方达", "562500": "机器人ETF华夏", "159667": "工业母机ETF国泰", "516510": "云计算ETF易方达", "159939": "信息技术ETF广发",
         "159998": "计算机ETF天弘", "159852": "软件ETF嘉实", "159967": "创业板成长ETF华夏", "512720": "计算机ETF国泰", "512480": "半导体ETF国联安",
         "588000": "科创50ETF华夏", "512670": "国防ETF鹏华", "159509": "纳指科技ETF景顺", "516150": "稀土ETF嘉实", "159732": "消费电子ETF华夏",
         "515000": "科技ETF华宝", "515980": "人工智能ETF华富", "159755": "电池ETF广发", "513090": "香港证券ETF易方达"}
COMMON = ("研究面板 79 只 ETF（不限波动率），每个自然年单独回测（年初空仓、年末平仓，当年不足 120 个交易日不计，2026 年截至 11-10），"
          "另做全历史回测（上市后第 121 根日线起，单边 0.1% 成本）。入选需同时满足：计入年份≥3；逐年收益平均≥10%；正收益年份≥75%；最差一年≥−10%；全历史卡玛（年化÷最大回撤）≥0.5。"
          "两种方案都合格的归到卡玛更高的一组；另补入只差一项、逐年均≥10% 且卡玛≥0.7、与本组每只日收益相关都<0.80 的标的。按卡玛从高到低排序。"
          "名单用同一段历史挑出，结果偏乐观。历史统计，不构成投资建议。")
RULE = {"A": "创业板择时优选：Y1 方案——择时（创业板ETF÷红利ETF 高于 20 日均线为牛）牛市 MACD(12/26/9) 金叉或站上 10 日线且 K−D≥5.3 次日开盘买，熊市不开新仓；死叉，或择时熊市收盘跌破 10 日线，当天收盘卖。" + COMMON,
        "B": "沪深300择时优选：只认金叉方案——择时（沪深300÷红利ETF 高于 20 日均线为牛）牛市 MACD(12/26/9) 金叉次日开盘买，熊市不开新仓；死叉当天收盘卖。" + COMMON}
def _init(): S.init()
def _work(c): return S.work(c)
if __name__ == "__main__":
    G = json.load(open("全量逐年优秀AB_最终分组.json")); added = {c for g in G["added"].values() for c in g}
    S.init(); keys = [k for k in S.T.M.PANEL if k[1:] in set(G["A"]) | set(G["B"])]
    with Pool(8, initializer=_init) as p: R = {o["code"][1:]: o for o in p.map(_work, keys)}
    for g, fn in (("A", "etfMacdGood.json"), ("B", "etfHs300Timing.json")):
        items = []
        for c in G[g]:
            o = R[c]; s = S.judge(o, g); full = o[g+"_full"]
            items.append({"code": c, "name": NAMES[c], "start": full["first"], "years": round(full["years"], 1),
                          "annual": round(s["cagr"]*100, 2), "drawdown": round(s["mdd"]*100, 2), "calmar": round(s["cal"], 2),
                          "yearAvg": round(s["avg"]*100, 2), "worstYear": round(s["worst"]*100, 2), "positiveYears": sum(v > 0 for v in o[g+"_yr"].values()), "countedYears": s["n"],
                          "yearly": {str(y): round(v*100, 1) for y, v in sorted(o[g+"_yr"].items())}, "supplement": c in added})
        items.sort(key=lambda x: -x["calmar"])
        json.dump({"asOf": "2026-11-10", "rule": RULE[g], "items": items}, open(OUT+fn, "w"), ensure_ascii=False, indent=2); open(OUT+fn, "a").write("\n")
        print(g, len(items), [(x["code"], x["calmar"], x["supplement"]) for x in items])
