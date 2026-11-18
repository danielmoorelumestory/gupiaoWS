"""用户同意（2026-11-18）：把「行业观察池」加到网页（只显示信号，不纳入主组合、不进 Telegram 提醒）。
名单来自 行业扩充名单.py 的「只加高波动」规则，并按 境外ETF择时有效性 的结论去掉美股/港股（标普消费、标普油气、恒生医药、港股通信息技术），剩 7 只 A 股行业 ETF。
策略按事先规则「2021 年底前卡玛选 A/B，不足 2 年数据用 A」，7 只均为 A（Y1·创业板择时）。
导出每只全历史连续回测（上市第 121 根起，单边 0.1%）：年化、最大回撤、卡玛、逐年收益、上市日。2026-11-18 追加（用户指定）：A 股券商 512880、煤炭 515220、汽车 516110、医药（创新药）159992、消费 159928、自动驾驶（智能驾驶）516520。
这些不满足波动≥31%，但用户认为是活跃行业、需要覆盖；面板外的（煤炭、汽车、智能驾驶）用腾讯后复权数据按 指数延长回测.entry 构建。
策略统一按事先规则：2021 年底以前卡玛选 A/B，2021 年前不足 2 年（488 根）数据的用 A。核聚变/核电未找到对应 ETF，不加。
2026-11-18 再改（用户选择）：汽车 516110 换成汽车零部件 159565（汽车零部件替代对照见 汽车替代对照.py；注意它与机器人 562500 日收益相关 0.90）。
2026-11-18 再改（用户决定）：去掉黄金股 517520（年化 −2.0%、回撤 −45.3%）。
2026-11-18 再改（用户决定）：与 A/B 两组口径统一，方案改按全历史卡玛选（A/B 卡玛高者），不再用 2021 年底以前的数据。
历史统计，不构成投资建议。
【2026-11-18 起不再使用】现行分组见 网页口径重新分组.py（网页回测口径、只算已平仓、归组按逐年平均→年化→盈利年份/波动→回撤）。本文件保留作历史记录。"""
import importlib.util, json, sys
sp = importlib.util.spec_from_file_location("X", "指数延长回测.py"); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
C = X.C
POOL = [("512400", "有色金属ETF南方", "有色"), ("515880", "通信ETF国泰", "通信"), ("159566", "储能电池ETF易方达", "储能"), ("159206", "卫星ETF永赢", "卫星"),
        ("588170", "科创半导体ETF华夏", "半导体设备材料"), ("515790", "光伏ETF华泰柏瑞", "光伏"),
        ("512880", "证券ETF国泰", "A股券商"), ("515220", "煤炭ETF国泰", "煤炭"), ("159565", "汽车零部件ETF易方达", "汽车零部件"),
        ("159992", "创新药ETF银华", "医药（创新药）"), ("159928", "消费ETF汇添富", "消费"), ("516520", "智能驾驶ETF华泰柏瑞", "自动驾驶")]
import gzip, regime_multi as RM, tencent_hfq as T
def data_of(code):
    if "P" + code in C.T.M.PANEL: return C.T.M.PANEL["P" + code]
    sym = ("sh" if code[0] == "5" else "sz") + code; T.load(sym)
    raw = json.loads(gzip.decompress((T.RAW / f"{sym}-tencent-hfq.json.gz").read_bytes()))
    rows = [{"date": x[0], "open": x[1], "high": x[3], "low": x[4], "close": x[2], "adjusted_close": x[2], "share_factor": "1", "cumulative_cash": "0"} for x in raw if x[0] <= X.END]
    p880 = RM.ratio_leg("510880"); r2 = RM.ma_state(RM.ratio(RM.ratio_leg("159915"), p880), 20); h1 = RM.ma_state(RM.ratio(RM.index_series("sh000300"), p880), 20)
    return X.entry(code, rows, r2, h1)
def run(d, pl):
    return C.Y.simulate_y(d, C.Y.VAR["Y1"], C.FULL, 20, retain=True) if pl == "A" else C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True)
def choose(d):
    navs = {pl: {p["date"]: p["nav"] for p in run(d, pl)["nav"]} for pl in "AB"}
    full = ("1900-01-01", X.END)
    ma, mb = C.window_metrics(navs["A"], full), C.window_metrics(navs["B"], full)
    return "A" if ma["cal"] >= mb["cal"] else "B"
if __name__ == "__main__":
    C.init(); items = []
    for code, name, ind in POOL:
        d = data_of(code); pl = choose(d); r = run(d, pl)
        nav = {p["date"]: p["nav"] for p in r["nav"]}; m = C.window_metrics(nav, ("1900-01-01", X.END))
        ys = {y: round(v*100, 1) for y, v in m["years"].items()}
        items.append({"code": code, "name": name, "industry": ind, "plan": "cyb" if pl == "A" else "hs", "start": r["metric"]["first"], "years": round(r["metric"]["years"], 1),
                      "annual": round(m["cagr"]*100, 2), "drawdown": round(m["mdd"]*100, 2), "calmar": round(m["cal"], 2), "yearly": ys})
        print(code, name, pl, items[-1]["start"], items[-1]["annual"], items[-1]["drawdown"], items[-1]["calmar"], ys)
    rule = ("行业观察池：现行两组优选几乎全是科技，为了不错过以后突然活跃的行业，放两类 A 股行业 ETF 观察：一是研究面板里不在两组、年化波动≥31%、与两组成员日收益相关<0.93 的"
            "（有色、通信、储能、卫星、科创半导体、光伏）；二是活跃但波动较低的大行业（A股券商、煤炭、汽车零部件、创新药、消费、智能驾驶；汽车零部件这两年与机器人走势高度一致）。美股、港股与 A 股择时没有逻辑关联，不放；"
            "核聚变/核电暂无对应 ETF。每只用哪套买卖点按全历史卡玛选（两套中卡玛高者，与两组优选同一口径，结果偏乐观），这套趋势+风格择时在低波动行业上历史表现普遍偏弱。"
            "只看信号，与两组优选一起发 Telegram 择时提醒（标［观察］）；先观察半年到一年的实际信号表现再决定去留。部分 ETF 上市不足 3 年，数字参考意义有限。历史统计，不构成投资建议。")
    _old = ("行业观察池：现行两组优选几乎全是科技，为了不错过以后突然活跃的行业，把研究面板里不在两组、年化波动≥31%、与两组成员日收益相关<0.93 的 A 股行业 ETF 放进来观察"
            "（美股、港股与 A 股择时没有逻辑关联，不放）。策略按 2021 年底以前的数据选（不足 2 年用创业板择时），7 只都用创业板择时买卖点（Y1）。"
            "只看信号，与两组优选一起发 Telegram 择时提醒（标［观察］）；先观察半年到一年的实际信号表现再决定去留。回测：7 只等权 2020 年起表现明显弱于两组优选，"
            "且储能、卫星、科创半导体上市不足 3 年，数字参考意义有限。历史统计，不构成投资建议。")
    out = {"asOf": X.END, "rule": rule, "items": items}
    open(sys.argv[1], "w").write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
