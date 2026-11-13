"""命令行入口：python -m bruce_replica <命令>

  today     取当日全市场截面，算红盘率、阿姆士（量/额两种口径），入库，并与他的案例比对
  tech      取指数日线，输出周线和日线上的技术面读数
  pcr       回补中金所股指期权数据，输出 50、300 的持仓量 PCR 通道信号（与他画面数值一致的口径）
  backfill  下载全市场个股日线，回补历史上每天的涨跌家数和阿姆士，让 MCL 立刻可用（约半小时，可续跑）
  spread    沪深300 股债利差的标准差通道：当前位置、历史上触上轨和破下轨的时段
  valuation 估值旁证：总市值/GDP、市盈率与市净率的历史位置、三只宽基 ETF 成交额
  chart     生成股债息差通道的图表页面（HTML）
  backtest  把他明说的规则写死，在历史上检验（需先回补好期权和个股日线数据）
  combine   资金面与技术面合成结论，例如：combine 空 多
  journal   新建空的交易记录表
  uptrend   同花顺 ETF 主升浪：每日采集名单快照、历史上涨区间与 AI 原因，生成页面，管理每日定时（详见 uptrend -h）
"""
from __future__ import annotations

import sys

if __name__ == "__main__" and sys.argv[1:2] == ["uptrend"]:
    # 主升浪采集只用标准库；在导入 pandas 等依赖之前分流，定时任务用系统 Python 即可运行。
    from bruce_replica.uptrend import cli as _uptrend_cli

    sys.exit(_uptrend_cli(sys.argv[2:]))

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import backtest, breadth, data, journal, midterm, pcr, rules, technical


def _today(a: argparse.Namespace) -> None:
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else date.today()
    if a.snapshot:
        df = data.load_snapshot(a.snapshot)
    else:
        print("正在取全市场截面（约需数分钟）……")
        df = data.fetch_snapshot()
        print("已保存截面：", data.save_snapshot(df, day))
    df = data.filter_pool(df, include_bj=not a.no_bj)
    r = breadth.breadth_reading(df, exclude_st=a.exclude_st, flat_as_down=a.flat_as_down)
    share5 = midterm.high_turnover_share(df)
    hist = data.upsert_daily(day, {**r.to_dict(), "turnover_gt5_share": share5})

    print(f"\n{day}  股票池 {len(df)} 只（{'不含' if a.no_bj else '含'}北交所，"
          f"{'剔除' if a.exclude_st else '含'}ST，平盘{'并入下跌' if a.flat_as_down else '不计入涨跌'}）")
    print(f"  上涨 {r.n_up}  下跌 {r.n_down}  平盘 {r.n_flat}   红盘率 {r.up_ratio:.1%}   涨跌家数比 {r.ad_ratio:.2f}")
    print(f"  阿姆士（成交额口径） {r.trin_amount:.2f}    阿姆士（成交量口径） {r.trin_volume:.2f}")
    print(f"  下跌股占涨跌总成交额 {r.down_amount_share:.1%}    换手率高于5%的个股占比 {share5:.1%}")

    res = rules.read_short_term(r.up_ratio, r.trin_amount, stage=a.stage)
    print(f"\n  参考档：{res['tier']}")
    c = res["nearest"]
    if c:
        tag = "相近" if res["similar"] else "差距较大，仅供参考"
        print(f"  最接近的案例（{tag}，距离 {res['distance']}）：{c.date} 红盘率 {c.up_ratio:.1%}、阿姆士 {c.trin}")
        print(f"    他的解读：{c.reading}（{c.source}）")
    print(f"  {res['note']}")
    if rules.shrinking_rally(r.up_ratio, r.trin_amount):
        print("  缩量普涨（红盘率≥80% 且阿姆士>1）：他多次据此判定为反弹而不是反转。")

    n = len(hist)
    if n >= 40:
        mcl = breadth.mcclellan(hist["n_up"] - hist["n_down"])["mcl"].iloc[-1]
        print(f"\n  MCL（19/39）：{mcl:+.0f}（已积累 {n} 个交易日）")
    else:
        print(f"\n  MCL 暂不可用：已积累 {n} 个交易日，约需 40 个。请每个交易日收盘后运行一次。")


def _tech(a: argparse.Namespace) -> None:
    d = data.fetch_index_daily(a.symbol)
    for label, frame in (("周线（定中线趋势）", technical.to_weekly(d)), ("日线（找入场点）", d)):
        print(f"\n{a.symbol} {label}")
        for k, v in technical.snapshot(frame).items():
            print(f"  {k}: {v}")
    print("\n这些是指标读数，不是多空结论；背离、出云失败等形态需要人工看图判断。")


def _pcr(a: argparse.Namespace) -> None:
    end = date.today()
    start = end - timedelta(days=a.days)
    if a.source == "cffex":
        stats, k50, k300 = data.backfill_cffex_options(start, end), pcr.HO, pcr.IO
        rows = (("上证50 股指期权 HO", pcr.HO), ("沪深300 股指期权 IO", pcr.IO), ("中证1000 股指期权 MO", pcr.MO), ("三者合计", None))
        print(f"中金所股指期权，{a.basis} 口径，通道 {a.window} 日 ±{a.k}σ，数据截至 {stats['date'].max()}")
    else:
        stats, k50, k300 = data.backfill_sse_options(start, end), pcr.ETF50, pcr.ETF300
        rows = (("上证50ETF", pcr.ETF50), ("沪深300ETF", pcr.ETF300), ("全部标的合计", None))
        print(f"上交所 ETF 期权，{a.basis} 口径，通道 {a.window} 日 ±{a.k}σ，数据截至 {stats['date'].max()}")
    sigs = {}
    for label, und in rows:
        band = pcr.pcr_band(pcr.pcr_series(stats, und, a.basis), a.window, a.k)
        last = band.iloc[-1]
        sigs[und] = pcr.recent_signal(band)
        print(f"  {label}: PCR {last.pcr:.3f}  下轨 {last.lower:.3f}  中轨 {last.mid:.3f}  上轨 {last.upper:.3f}"
              f"  近3日信号：{sigs[und]}")
    print("  判读：", pcr.interpret(sigs[k50], sigs[k300], a.trend))
    if a.source == "cffex" and a.basis == "oi":
        print("  HO、IO 的持仓量 PCR 与他 9/30 画面上的数值一致；「合计」不是他的全市场加权算法。")
    else:
        print("  这个口径对不上他画面上的数值，仅供对照。")


def _backfill(a: argparse.Namespace) -> None:
    import glob

    snaps = sorted(glob.glob(str(Path(data.DATA_DIR) / "snapshots" / "*.csv.gz")))
    if not snaps:
        raise SystemExit("还没有全市场截面，先运行一次 today 以取得股票代码表。")
    codes = data.load_snapshot(snaps[-1])["code"].tolist()
    end = date.today()
    n, fail = data.backfill_stock_hist(codes, end - timedelta(days=a.days), end)
    print(f"新下载 {n} 只，失败 {len(fail)} 只" + ("（再运行一次可续跑）" if fail else ""))
    hist = data.merge_breadth_history(data.breadth_from_hist())
    mcl = breadth.mcclellan(hist["n_up"] - hist["n_down"])["mcl"]
    print(f"每日汇总表现有 {len(hist)} 个交易日（{hist['date'].iloc[0]} 至 {hist['date'].iloc[-1]}），最新 MCL {mcl.iloc[-1]:+.0f}")


# 他点名的时点（研判第1集、金融宝藏第11集）及其说法，用于和通道对照。
_SPREAD_CLAIMS = (("2020-12-31", "跌破下轨，股市顶"), ("2024-09-18", "上穿上轨，底"),
                  ("2025-04-07", "上穿上轨，底"), ("2026-09-16", "在中轨，往上轨走"))


def _spread(a: argparse.Namespace) -> None:
    df = data.fetch_equity_bond_spread()
    band = midterm.std_band(df["spread"], a.window, a.k)
    sd = (band["upper"] - band["mid"]) / a.k
    last = band.iloc[-1]
    print(f"沪深300 股债利差，通道 {a.window} 日 ±{a.k}σ，数据截至 {band.index[-1].date()}")
    print(f"  息差 {last.value:.2f}  下轨 {last.lower:.2f}  中轨 {last.mid:.2f}  上轨 {last.upper:.2f}"
          f"  偏离 {(last.value - last.mid) / sd.iloc[-1]:+.2f}σ")
    print(f"  判读：{midterm.spread_reading(last.zone)}")
    recent = band[band.index >= a.since]
    for zone, label in (("触及上轨", "触上轨（他的底部信号）"), ("跌破下轨", "破下轨（他的顶部信号）")):
        print(f"\n  {a.since} 年以来{label}：")
        for s, e in midterm.band_episodes(recent, zone):
            seg = df.loc[s:e, "index"]
            print(f"    {s.date()} ~ {e.date()}  沪深300 区间 {seg.min():.0f}–{seg.max():.0f}")
    print("\n  他点名的时点：")
    for d, claim in _SPREAD_CLAIMS:
        t = pd.Timestamp(d)
        if t < band.index[0] or t > band.index[-1]:
            continue
        i = band.index.get_indexer([t], method="nearest")[0]
        row = band.iloc[i]
        print(f"    {band.index[i].date()}  他说：{claim}  |  通道读数 {(row.value - row.mid) / sd.iloc[i]:+.2f}σ（{row.zone}）")
    print("\n  口径是沪深300、窗口和倍数是我们选的；他说的是全市场口径，参数没给。")


def _valuation(a: argparse.Namespace) -> None:
    g = data.fetch_mktcap_gdp()
    last = g.iloc[-1]
    print(f"总市值/GDP（截至 {g.index[-1].date()}）：{last.ratio:.3f}  →  {midterm.mktcap_gdp_zone(last.ratio)}")
    print("  他画面上的线：1.00 高估、0.70 低估、0.50 极低估（金融宝藏第11集）")
    for d, note in (("2021-02-18", "2021 年顶部，他说接近高估线"), ("2024-09-18", "「924」前，他说偏低"),
                    ("2026-09-23", "他说偏高的那天")):
        print(f"    {d}  {g['ratio'].asof(pd.Timestamp(d)):.3f}  {note}")

    pe = data.fetch_index_pe("沪深300")
    print(f"\n沪深300 市盈率（截至 {pe.index[-1].date()}），近 10 年的位置：")
    for col in ("静态市盈率", "滚动市盈率", "等权滚动市盈率"):
        b = midterm.percentile_band(pe[col])
        print(f"  {col}: {b['value']:.2f}  处于 {b['pct']:.0%} 分位   20%/80% 分位值 {b['low']:.2f} / {b['high']:.2f}")
    print("  他第14集画面：PE 13，机会值 11.61、危险值 14.18。最接近的是静态市盈率的 20%/80% 分位，但没有完全对上。")

    v = data.fetch_all_a_valuation()
    print(f"\n全部 A 股（截至 {v.index[-1].date()}），近 10 年的位置：")
    for col, label in (("pe_equal", "等权平均市盈率"), ("pe_median", "市盈率中位数"), ("pb_equal", "等权平均市净率"), ("pb_median", "市净率中位数")):
        b = midterm.percentile_band(v[col])
        print(f"  {label}: {b['value']:.2f}  处于 {b['pct']:.0%} 分位")
    for d in ("2024-08-31", "2026-09-30"):
        print(f"    {d} 等权平均市净率 {v['pb_equal'].asof(pd.Timestamp(d)):.2f}")
    print("  他在研判第2集用等权市净率对比「924」前（很低）与 2026 年 9 月（很高），没给阈值。")

    e = midterm.etf_amount_ma(data.fetch_etf_amount())
    print(f"\n三只宽基 ETF（510300、510050、588000）成交额合计（截至 {e.index[-1].date()}）："
          f"{e['total'].iloc[-1]:.1f} 亿，20 日均 {e['ma'].iloc[-1]:.1f} 亿")
    print("  他拿这张图当反例，说明 ETF 成交额看不出国家队进场，不是择时信号。")


def _fmt(t: pd.DataFrame) -> str:
    t = t.copy()
    for c in t.columns[1:]:
        t[c] = t[c].map(lambda v: "—" if pd.isna(v) else f"{v:+.1%}" if "涨跌" in c else f"{v:.0%}")
    return "    " + t.to_string().replace("\n", "\n    ")


def _backtest(a: argparse.Namespace) -> None:
    dd = Path(data.DATA_DIR)
    print("== 一、股债息差通道（沪深300，750 日 2 倍）==")
    sp = data.fetch_equity_bond_spread()
    band = midterm.std_band(sp["spread"], 750, 2.0)
    start = band.index[band["zone"].notna()][0]
    for zone, exp, label in (("触及上轨", 1, "触上轨，他说是底"), ("跌破下轨", -1, "破下轨，他说是顶")):
        ev = backtest.events(band["zone"] == zone, gap=20)
        print(f"  {label}：{[d.strftime('%Y-%m-%d') for d in ev]}")
        print(_fmt(backtest.summarize(sp["index"], ev, (20, 60, 120, 250), exp, start)))
    p2, b2 = sp["index"][sp.index >= start], band[band.index >= start]
    st = backtest.state_strategy(p2, b2["zone"] == "触及上轨", b2["zone"] == "跌破下轨")
    print(f"  触上轨进、破下轨出：年化 {st['策略']['年化']:.1%}，最大回撤 {st['策略']['最大回撤']:.0%}，持仓时间 {st['持仓时间占比']:.0%}；"
          f"一直持有：年化 {st['买入持有']['年化']:.1%}，最大回撤 {st['买入持有']['最大回撤']:.0%}")

    print("\n== 二、期权 PCR 通道（中金所持仓量，20 日 2 倍）==")
    opt = pd.read_csv(dd / "option_cffex_daily.csv", dtype={"date": str})
    bands = {}
    for u, px, name in ((pcr.IO, sp["index"], "沪深300"), (pcr.HO, data.fetch_index_daily("sh000016")["close"], "上证50")):
        b = pcr.pcr_band(pcr.pcr_series(opt, u), 20, 2.0)
        b.index = pd.to_datetime(b.index)
        b = bands[u] = b[b["signal"].notna()]
        p = px.reindex(b.index).ffill()
        for sig, exp, label in ((pcr.TOP, -1, "击穿上轨，他说是顶"), (pcr.BOTTOM, 1, "击穿下轨，他说是底")):
            ev = backtest.events(b["signal"] == sig, gap=5)
            print(f"  {name} {label}（{b.index[0].date()} 起）")
            print(_fmt(backtest.summarize(p, ev, (5, 10, 20, 60), exp, b.index[0])))
    idx = bands[pcr.IO].index.intersection(bands[pcr.HO].index)
    io_bot = bands[pcr.IO].loc[idx, "signal"] == pcr.BOTTOM
    ho_bot = (bands[pcr.HO].loc[idx, "signal"] == pcr.BOTTOM).rolling(3, min_periods=1).max().astype(bool)
    p = sp["index"].reindex(idx).ffill()
    for flag, exp, label in ((io_bot & ~ho_bot, -1, "300 破下轨而 50 近 3 日没破，他说下跌没结束"), (io_bot & ho_bot, 1, "300 与 50 同破下轨，他说是底")):
        print(f"  {label}（{idx[0].date()} 起）")
        print(_fmt(backtest.summarize(p, backtest.events(flag, gap=5), (5, 10, 20, 60), exp, idx[0])))

    print("\n== 三、宽广度与阿姆士（成交额口径，对上证指数）==")
    parts = [data.breadth_from_hist(subdir=sd) for sd in ("hist_long", "hist") if (dd / sd).exists()]
    br = pd.concat(parts).drop_duplicates("date").sort_values("date")
    br.index = pd.to_datetime(br["date"])
    sh = data.fetch_index_daily()["close"].reindex(br.index).ffill()
    print(f"  样本 {br.index[0].date()} 至 {br.index[-1].date()}，{len(br)} 个交易日")
    rules_ = (
        ((br["up_ratio"] >= 0.8) & (br["trin_amount"] > 1.0), -1, "缩量普涨（红盘率≥80% 且阿姆士>1），他说是反弹不是反转"),
        ((br["up_ratio"] >= 0.8) & (br["trin_amount"] <= 1.0), 1, "对照：放量普涨（红盘率≥80% 且阿姆士≤1）"),
        ((br["up_ratio"] <= 0.12) & (br["trin_amount"] < 0.5), 1, "冰点（红盘率≤12% 且阿姆士<0.5），他说大资金在买"),
        ((br["up_ratio"] <= 0.12) & (br["trin_amount"] >= 0.5), 1, "对照：普跌但没有放量承接（红盘率≤12% 且阿姆士≥0.5）"),
        (br["trin_amount"] < 0.35, 1, "阿姆士低于 0.35（他举的 3/23、7/21 都在 0.30 左右），他说大资金扫货"),
    )
    for flag, exp, label in rules_:
        print(f"  {label}")
        print(_fmt(backtest.summarize(sh, backtest.events(flag, gap=5), (1, 5, 10, 20, 60), exp, br.index[0])))
    print("\n  阈值里的 12%、0.35、合并间隔、观察天数都是研究者设定；他要求只在「趋势中后段」用，这一条无法编码，没有施加。")


def _chart(a: argparse.Namespace) -> None:
    import json

    df = data.fetch_equity_bond_spread()
    band = midterm.std_band(df["spread"], a.window, a.k)
    start = band.index[band["zone"].notna()][0]
    hs = (20, 60, 120, 250)
    pos = {d: i for i, d in enumerate(df.index)}

    def evs(zone: str) -> list:
        ev = backtest.events(band["zone"] == zone, gap=20)
        fr = backtest.forward_returns(df["index"], ev, hs)
        return [{"d": f"{d:%Y%m%d}", "i": pos[d], "r": [None if pd.isna(v) else round(float(v), 4) for v in fr.loc[d]]} for d in ev]

    base_px = df["index"][df.index >= start]
    num = lambda s, n: [None if pd.isna(v) else round(float(v), n) for v in s]
    payload = {"d": [f"{d:%Y%m%d}" for d in df.index], "s": num(df["spread"], 3), "p": num(df["index"], 1),
               "m": num(band["mid"], 3), "u": num(band["upper"], 3), "l": num(band["lower"], 3),
               "up": evs("触及上轨"), "dn": evs("跌破下轨"),
               "base": [round(float((base_px.shift(-h) / base_px - 1).mean()), 4) for h in hs]}
    tpl = (Path(__file__).parent / "templates" / "spread.html").read_text(encoding="utf-8")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace("__DATA__", json.dumps(payload, separators=(",", ":"))), encoding="utf-8")
    print(f"已生成 {out}（数据截至 {df.index[-1].date()}，{out.stat().st_size // 1024} KB）")


def main() -> None:
    p = argparse.ArgumentParser(prog="bruce_replica", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("today", help="当日宽广度与阿姆士")
    t.add_argument("--date", help="读数归属日期 YYYY-MM-DD，默认今天")
    t.add_argument("--snapshot", help="用已保存的截面文件，不联网")
    t.add_argument("--stage", default="未知", choices=["未知", "初段", "中后段"], help="趋势阶段，人工判断")
    t.add_argument("--no-bj", action="store_true", help="不含北交所")
    t.add_argument("--exclude-st", action="store_true", help="剔除 ST")
    t.add_argument("--flat-as-down", action="store_true", help="平盘并入下跌")
    t.set_defaults(func=_today)

    k = sub.add_parser("tech", help="指数技术面读数")
    k.add_argument("--symbol", default="sh000001")
    k.set_defaults(func=_tech)

    o = sub.add_parser("pcr", help="期权 PCR 通道信号")
    o.add_argument("--source", default="cffex", choices=["cffex", "sse"], help="中金所股指期权（他用的）或上交所 ETF 期权")
    o.add_argument("--days", type=int, default=120, help="回补的自然日数")
    o.add_argument("--basis", default="oi", choices=["oi", "vol"], help="持仓量或成交量口径")
    o.add_argument("--window", type=int, default=20)
    o.add_argument("--k", type=float, default=2.0)
    o.add_argument("--trend", default="未知", choices=["未知", "上行", "下行"], help="单边趋势方向，人工判断")
    o.set_defaults(func=_pcr)

    b = sub.add_parser("backfill", help="回补历史宽广度")
    b.add_argument("--days", type=int, default=530, help="回补的自然日数")
    b.set_defaults(func=_backfill)

    s = sub.add_parser("spread", help="股债利差通道")
    s.add_argument("--window", type=int, default=750)
    s.add_argument("--k", type=float, default=2.0)
    s.add_argument("--since", default="2019", help="列出该年以来的触轨时段")
    s.set_defaults(func=_spread)

    v = sub.add_parser("valuation", help="估值旁证")
    v.set_defaults(func=_valuation)

    ch = sub.add_parser("chart", help="生成股债息差通道图表页面")
    ch.add_argument("--out", default=str(Path(data.DATA_DIR).parent.parent / "charts" / "spread-channel.html"))
    ch.add_argument("--window", type=int, default=750)
    ch.add_argument("--k", type=float, default=2.0)
    ch.set_defaults(func=_chart)

    bt = sub.add_parser("backtest", help="规则回测")
    bt.set_defaults(func=_backtest)

    c = sub.add_parser("combine", help="资金面与技术面合成结论")
    c.add_argument("capital", choices=["多", "空", "中"])
    c.add_argument("technical", choices=["多", "空", "中"])
    c.set_defaults(func=lambda a: print(rules.combine(a.capital, a.technical)))

    j = sub.add_parser("journal", help="新建空的交易记录表")
    j.add_argument("--path", default=str(Path(data.DATA_DIR) / "交易记录表.csv"))
    j.set_defaults(func=lambda a: print("记录表：", journal.init(a.path)))

    u = sub.add_parser("uptrend", help="同花顺 ETF 主升浪采集、页面与每日定时", add_help=False)
    u.add_argument("rest", nargs=argparse.REMAINDER)
    u.set_defaults(func=lambda a: sys.exit(__import__("bruce_replica.uptrend", fromlist=["cli"]).cli(a.rest)))

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
