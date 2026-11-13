#!/usr/bin/env python3
"""Claude 独立复测：61只冻结ETF × 6套固定规则（候选A/B、USER、MACD、MA10、HOLD）。

纯 Python 标准库实现，不导入原研究目录的 engine / reference / verify / 指标函数。
只读取：inputs.json、原目录 protocol.json 等（核验哈希）、data/{code}.csv.gz。
阶段1 独立计算并写出结果；阶段2 才读取原 results/test_*.csv.gz 逐项比对。

用法：python3 -B retest61.py [--extra]
  --extra  另算成本0/10/40bp与两个子区间（仅作附加比对，不进入主表）
"""
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import sys
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path

getcontext().prec = 60

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parent
REPO = TASK_DIR.parents[3]
INPUTS = json.loads((TASK_DIR / "inputs.json").read_text())
SRC = REPO / INPUTS["source_directory"]
WIN = tuple(INPUTS["window"])
COST_RT = INPUTS["cost_bps_round_trip"]
SCHEMES = ["e6ecc034065e", "825cd1230879", "USER", "MACD", "MA10", "HOLD"]
LABEL = {"e6ecc034065e": "候选A", "825cd1230879": "候选B", "USER": "USER",
         "MACD": "纯MACD", "MA10": "MA10", "HOLD": "持有"}
WARMUP = 120
MIN_WINDOW_ROWS = 120
ANNUAL_ROWS = 244
ANNUAL_DAYS = 365
TOL = 1e-9


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_inputs():
    res = {}
    for name, exp in INPUTS["pins"].items():
        got = sha(SRC / name)
        res[name] = {"expected": exp, "actual": got, "ok": got == exp}
    for e in INPUTS["primary_etfs"]:
        got = sha(SRC / e["normalized_file"])
        res[e["normalized_file"]] = {"expected": e["normalized_sha256"], "actual": got,
                                     "ok": got == e["normalized_sha256"]}
    return res


# ---------------------------------------------------------------- data
def load(code):
    rows = []
    with gzip.open(SRC / "data" / f"{code}.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            rows.append({
                "date": r["date"],
                "open": float(r["open"]), "close": float(r["close"]),
                "s": float(r["share_factor"]), "K": float(r["cumulative_cash"]),
                "adjF": Fraction(r["adjusted_close"]),   # 精确有理数，用于MA/波段比较
                "adjD": Decimal(r["adjusted_close"]),    # Decimal60，用于MACD
            })
    for a, b in zip(rows, rows[1:]):
        assert a["date"] < b["date"], (code, a["date"])
    return rows


# ---------------------------------------------------------- indicators
def ma_state(rows, n=10):
    """返回每行 +1(C>MA)/-1(C<MA)/0(相等)/None(不足)。精确比较 n*C vs sum。"""
    out = [None] * len(rows)
    s = Fraction(0)
    for i, r in enumerate(rows):
        s += r["adjF"]
        if i >= n:
            s -= rows[i - n]["adjF"]
        if i >= n - 1:
            lhs = n * r["adjF"]
            out[i] = 1 if lhs > s else (-1 if lhs < s else 0)
    return out


def band(rows, n):
    """返回每行 (up, tot) 精确分数，V=100*up/tot；窗口不足或tot=0返回None。"""
    out = [None] * len(rows)
    for i in range(n, len(rows)):
        up = Fraction(0)
        tot = Fraction(0)
        for j in range(i - n + 1, i + 1):
            d = rows[j]["adjF"] - rows[j - 1]["adjF"]
            if d > 0:
                up += d
            tot += abs(d)
        out[i] = None if tot == 0 else (up, tot)
    return out


def v_ge(b, lvl):  # V >= lvl
    return b is not None and 100 * b[0] >= lvl * b[1]


def v_lt(b, lvl):  # V < lvl（None 不判定为低于）
    return b is not None and 100 * b[0] < lvl * b[1]


def v_value(b):
    return None if b is None else float(100 * b[0] / b[1])


def macd(rows, fast, slow, sig):
    af, as_, ad = (Decimal(2) / Decimal(n + 1) for n in (fast, slow, sig))
    ef = es = rows[0]["adjD"]
    dea = Decimal(0)
    dif_l, dea_l = [], []
    for i, r in enumerate(rows):
        c = r["adjD"]
        if i > 0:
            ef = ef + af * (c - ef)
            es = es + as_ * (c - es)
        dif = ef - es
        if i > 0:
            dea = dea + ad * (dif - dea)
        dif_l.append(dif)
        dea_l.append(dea)
    gold = [False] * len(rows)
    death = [False] * len(rows)
    for i in range(1, len(rows)):
        gold[i] = dif_l[i - 1] <= dea_l[i - 1] and dif_l[i] > dea_l[i]
        death[i] = dif_l[i - 1] >= dea_l[i - 1] and dif_l[i] < dea_l[i]
    return gold, death


# ---------------------------------------------------------------- engine
def window_idx(rows, start, end):
    idx = [i for i, r in enumerate(rows) if start <= r["date"] <= end and i >= WARMUP]
    return idx


def simulate(code, name, rows, ind, cfg_id, cfg, start, end, cost_rt):
    side = cost_rt / 20000.0  # 单边费率
    idx = window_idx(rows, start, end)
    if len(idx) < MIN_WINDOW_ROWS:
        return None
    w0, wl = idx[0], idx[-1]
    assert idx == list(range(w0, wl + 1))
    ma = ind["ma10"]
    entry, exit_ = cfg["entry"], cfg["exit"]
    if cfg.get("n"):
        B = ind[("band", cfg["n"])]
    if cfg.get("macd"):
        gold, death = ind[("macd",) + tuple(cfg["macd"])]
    lo, hi = cfg.get("lo"), cfg.get("hi")
    wait = cfg.get("wait")

    cash, q, reserve = 1.0, 0.0, 0.0
    pending = None  # ("buy"|"sell", signal_index)
    armed_until = None
    hi_seen = False
    trade = None
    trades, nav = [], []
    fees = 0.0
    held_sessions = 0
    cap_expo = 0.0
    for t in range(w0, wl + 1):
        r = rows[t]
        # 1) 开盘前：昨日持仓的分红入独立reserve，再按份额因子调整
        if t > w0 and q > 0:
            p = rows[t - 1]
            div = q / p["s"] * (r["K"] - p["K"])
            if div != 0.0:
                reserve += div
                trade["dividends"] += div
            q = q * r["s"] / p["s"]
        # 2) 开盘成交（昨日收盘信号）
        if pending is not None:
            kind, si = pending
            o = r["open"]
            if kind == "buy":
                assert q == 0.0
                ec = cash
                q = ec / (o * (1 + side))
                fee = ec - q * o
                fees += fee
                cash = 0.0
                hi_seen = False
                trade = {"config": cfg_id, "code": code, "entry_index": t, "entry_date": r["date"],
                         "entry_signal_index": si, "entry_signal_date": rows[si]["date"],
                         "entry_price": o, "entry_cash": ec, "entry_reserve": reserve,
                         "entry_shares": q, "entry_fee": fee, "dividends": 0.0}
            else:
                assert q > 0
                gross = q * o
                fee = gross * side
                cash = gross - fee
                fees += fee
                trade.update(exit_index=t, exit_date=r["date"], exit_signal_index=si,
                             exit_signal_date=rows[si]["date"], exit_price=o, exit_cash=cash,
                             exit_fee=fee, forced_end=False)
                trade["net_return"] = (cash + trade["dividends"]) / trade["entry_cash"] - 1
                trades.append(trade)
                trade = None
                q = 0.0
                hi_seen = False
            pending = None
        # 3) 收盘：持仓高位统计（从实际买入日收盘起）
        if q > 0 and hi is not None and v_ge(B[t], hi):
            hi_seen = True
        # 4) 收盘估值 / 末日强制估值退出
        held = q > 0
        if t == wl and q > 0:
            c = r["close"]
            gross = q * c
            fee = gross * side
            fees += fee
            cash = gross - fee
            trade.update(exit_index=t, exit_date=r["date"], exit_signal_index=None,
                         exit_signal_date=None, exit_price=c, exit_cash=cash, exit_fee=fee,
                         forced_end=True)
            trade["net_return"] = (cash + trade["dividends"]) / trade["entry_cash"] - 1
            trades.append(trade)
            trade = None
            q = 0.0
            pv = 0.0
            n_ = cash + reserve
            # 末日按清算后计算持仓暴露：清算前市值
            cap_expo += gross / (gross + reserve)
        else:
            pv = q * r["close"]
            n_ = cash + reserve + pv
            if held:
                cap_expo += pv / n_
        if held:
            held_sessions += 1
        nav.append({"config": cfg_id, "code": code, "date": r["date"], "row_index": t, "nav": n_,
                    "shares": q, "cash": cash, "reserve": reserve, "held_session": int(held)})
        # 5) 收盘信号（末日不发）
        if t == wl:
            break
        sig = None
        if q == 0:
            if entry == "HOLD":
                if t == w0:
                    sig = "buy"
            elif entry == "MA":
                if ma[t] == 1:
                    sig = "buy"
            elif entry == "MACD":
                if gold[t]:
                    sig = "buy"
            elif entry == "E1":
                if (B[t - 1] is not None and v_lt(B[t - 1], lo) and v_ge(B[t], lo)
                        and ma[t] == 1):
                    sig = "buy"
            elif entry == "E2":
                if armed_until is not None and t > armed_until:
                    armed_until = None
                if armed_until is not None and v_lt(B[t], lo):
                    armed_until = None
                if B[t - 1] is not None and v_lt(B[t - 1], lo) and v_ge(B[t], lo):
                    armed_until = t + wait - 1
                if armed_until is not None and ma[t] == 1 and v_ge(B[t], lo):
                    sig = "buy"
                    armed_until = None
            else:
                raise ValueError(entry)
        else:
            armed_until = None
            if exit_ == "HOLD":
                pass
            elif exit_ == "X1":
                if ma[t] == -1:
                    sig = "sell"
            elif exit_ == "X2":
                if death[t]:
                    sig = "sell"
            elif exit_ == "X3":
                if death[t] and (ma[t] == -1 or (hi_seen and v_lt(B[t], hi))):
                    sig = "sell"
            else:
                raise ValueError(exit_)
        if sig:
            pending = (sig, t)

    # ------- metrics
    first, last = rows[w0]["date"], rows[wl]["date"]
    days = (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days
    sessions = len(idx)
    final = nav[-1]["nav"]
    peak, mdd = 1.0, 0.0
    for x in nav:
        peak = max(peak, x["nav"])
        mdd = min(mdd, x["nav"] / peak - 1)
    nat = [t_ for t_ in trades if not t_["forced_end"]]
    wins = sum(1 for t_ in nat if t_["net_return"] > 0)
    annual_ok = sessions >= ANNUAL_ROWS and days >= ANNUAL_DAYS
    cagr = final ** (365.25 / days) - 1 if annual_ok else None
    return {
        "metrics": {
            "config": cfg_id, "code": code, "name": name, "first": first, "last": last,
            "sessions": sessions, "calendar_days": days, "years": days / 365.25,
            "final_nav": final, "total_return": final - 1, "cagr": cagr, "mdd": mdd,
            "entries": len(trades), "natural": len(nat), "forced": len(trades) - len(nat),
            "wins": wins, "wr": wins / len(nat) if len(nat) >= 3 else None,
            "pooled_wr": wins / len(nat) if nat else None,
            "natural_fraction": len(nat) / len(trades) if trades else 0.0,
            "time_exposure": held_sessions / sessions, "capital_exposure": cap_expo / sessions,
            "dividend_reserve": reserve, "fees": fees,
            "late": first > start,
        },
        "trades": trades, "nav": nav,
    }


def indicators(rows, needed):
    ind = {"ma10": ma_state(rows, 10)}
    for k in needed:
        if k[0] == "band":
            ind[k] = band(rows, k[1])
        else:
            ind[k] = macd(rows, *k[1:])
    return ind


def run_all(etfs, windows, costs):
    cfgs = INPUTS["configs"]
    needed = set()
    for c in SCHEMES:
        if cfgs[c].get("n"):
            needed.add(("band", cfgs[c]["n"]))
        if cfgs[c].get("macd"):
            needed.add(("macd",) + tuple(cfgs[c]["macd"]))
    out = {}
    for e in etfs:
        rows = load(e["code"])
        ind = indicators(rows, needed)
        for wname, (s, en) in windows.items():
            for cost in costs:
                for c in SCHEMES:
                    r = simulate(e["code"], e["name"], rows, ind, c, cfgs[c], s, en, cost)
                    if r is not None:
                        out[(wname, cost, c, e["code"])] = r
        print(f"  {e['code']} {e['name']} done", flush=True)
    return out


# ---------------------------------------------------------------- output
def fmt(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        return repr(x)
    return str(x)


def write_csv(path, rows, fields, gz=False):
    op = gzip.open if gz else open
    with op(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in rows:
            w.writerow([fmt(r.get(k)) for k in fields])


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


# ------------------------------------------------------------ comparison
def num_eq(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def parse(v):
    if v == "" or v is None:
        return None
    if v in ("True", "False"):
        return v == "True"
    try:
        if any(ch in v for ch in ".eE") or v.lstrip("-").isdigit():
            return float(v) if not v.lstrip("-").isdigit() else int(v)
    except ValueError:
        pass
    return v


def read_gz(name):
    with gzip.open(SRC / "results" / name, "rt") as f:
        return list(csv.DictReader(f))


def compare(res, phase_map):
    diffs = []
    stats = {"per_etf_groups": 0, "per_etf_fields": 0, "trades": 0, "trade_fields": 0,
             "nav_rows": 0, "nav_fields": 0}
    PF = ["first", "last", "sessions", "years", "final_nav", "total_return", "cagr", "mdd",
          "entries", "natural", "wins", "wr", "pooled_wr", "natural_fraction", "time_exposure",
          "capital_exposure", "dividend_reserve", "fees"]
    orig = read_gz("test_per_etf.csv.gz")
    seen = set()
    for o in orig:
        if o["config"] not in SCHEMES:
            continue
        key = (phase_map.get(o["phase"]), int(o["cost"]), o["config"], o["code"])
        if key[0] is None or key not in res:
            if key[0] is not None and (key[0], key[1]) in {(k[0], k[1]) for k in res}:
                diffs.append({"kind": "per_etf_missing_in_retest", "key": "|".join(map(str, key))})
            continue
        seen.add(key)
        m = res[key]["metrics"]
        stats["per_etf_groups"] += 1
        for f in PF:
            a, b = m[f], parse(o[f])
            stats["per_etf_fields"] += 1
            ok = (a == b) if isinstance(a, str) or isinstance(b, str) or f in (
                "sessions", "entries", "natural", "wins") else num_eq(
                None if a is None else float(a), None if b is None else float(b))
            if not ok:
                diffs.append({"kind": "per_etf", "key": "|".join(map(str, key)), "field": f,
                              "retest": fmt(a), "original": o[f]})
    for k in res:
        if k not in seen and (k[0], k[1]) in {(x[0], x[1]) for x in seen}:
            diffs.append({"kind": "per_etf_missing_in_original", "key": "|".join(map(str, k))})

    main = {k: v for k, v in res.items() if k[0] == "test" and k[1] == COST_RT}
    # trades（原文件仅含主口径 test/20bp）
    TF = ["entry_index", "entry_date", "entry_signal_index", "entry_signal_date", "entry_price",
          "entry_cash", "entry_reserve", "entry_shares", "entry_fee", "exit_index", "exit_date",
          "exit_signal_index", "exit_signal_date", "exit_price", "exit_cash", "dividends",
          "exit_fee", "net_return", "forced_end"]
    ot = {}
    for o in read_gz("test_trades.csv.gz"):
        if o["config"] in SCHEMES:
            ot.setdefault((o["config"], o["code"]), []).append(o)
    for (w, cost, c, code), r in main.items():
        mine, theirs = r["trades"], ot.get((c, code), [])
        if len(mine) != len(theirs):
            diffs.append({"kind": "trade_count", "key": f"{c}|{code}", "retest": len(mine),
                          "original": len(theirs)})
        for i, (a, o) in enumerate(zip(mine, theirs)):
            stats["trades"] += 1
            for f in TF:
                stats["trade_fields"] += 1
                av, bv = a.get(f), parse(o[f])
                if f.endswith("_date") or f.endswith("_index") or f == "forced_end":
                    ok = (av == bv)
                else:
                    ok = num_eq(av, None if bv is None else float(bv))
                if not ok:
                    diffs.append({"kind": "trade", "key": f"{c}|{code}|#{i}", "field": f,
                                  "retest": fmt(av), "original": o[f]})
    # NAV 全量逐日
    on = {}
    for o in read_gz("test_nav.csv.gz"):
        if o["config"] in SCHEMES:
            on.setdefault((o["config"], o["code"]), []).append(o)
    NF = ["date", "row_index", "nav", "shares", "cash", "reserve", "held_session"]
    for (w, cost, c, code), r in main.items():
        mine, theirs = r["nav"], on.get((c, code), [])
        if len(mine) != len(theirs):
            diffs.append({"kind": "nav_count", "key": f"{c}|{code}", "retest": len(mine),
                          "original": len(theirs)})
        for a, o in zip(mine, theirs):
            stats["nav_rows"] += 1
            for f in NF:
                stats["nav_fields"] += 1
                av, bv = a[f], parse(o[f])
                ok = (av == bv) if f in ("date", "row_index", "held_session") else num_eq(
                    av, float(bv))
                if not ok:
                    diffs.append({"kind": "nav", "key": f"{c}|{code}|{a['date']}", "field": f,
                                  "retest": fmt(av), "original": o[f]})
    return diffs, stats


# ------------------------------------------------------------------ main
def main():
    extra = "--extra" in sys.argv[1:]
    log = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "argv": sys.argv}
    print("[1] 输入哈希核验（开始）")
    pins0 = check_inputs()
    bad = [k for k, v in pins0.items() if not v["ok"]]
    if bad:
        print("输入哈希不符：", bad)
        (HERE / "verification.json").write_text(json.dumps(
            {"status": "FAILED_INPUT_HASH", "bad": bad, "pins": pins0}, ensure_ascii=False,
            indent=2))
        sys.exit(2)
    etfs = INPUTS["primary_etfs"]
    assert len(etfs) == 61 and len({e["code"] for e in etfs}) == 61
    windows = {"test": WIN}
    costs = [COST_RT]
    if extra:
        proto = json.loads((SRC / "protocol.json").read_text())
        p1, p2 = proto["test_subperiods"]
        windows.update({"test_part1": tuple(p1), "test_part2": tuple(p2)})
        costs = [0, 10, COST_RT, 40]
    print(f"[2] 独立计算：{len(etfs)} ETF × {len(SCHEMES)} 方案，窗口{list(windows)}，成本{costs}")
    res = run_all(etfs, windows, costs)
    # 子区间只算20bp
    res = {k: v for k, v in res.items() if k[0] == "test" or k[1] == COST_RT}
    main_keys = [k for k in res if k[0] == "test" and k[1] == COST_RT]
    assert len(main_keys) == 366, len(main_keys)

    # ---- 写出主结果（比对前）
    MF = ["config", "role", "code", "name", "good", "first", "last", "sessions", "calendar_days",
          "years", "final_nav", "total_return", "cagr", "mdd", "entries", "natural", "forced",
          "wins", "wr", "pooled_wr", "natural_fraction", "time_exposure", "capital_exposure",
          "dividend_reserve", "fees", "late"]
    good = {e["code"]: ("MACD优秀" in e["groups"]) for e in etfs}
    roles = INPUTS["display_roles"]
    long_rows = []
    for c in SCHEMES:
        for e in etfs:
            m = dict(res[("test", COST_RT, c, e["code"])]["metrics"])
            m["role"] = roles[c]
            m["good"] = good[e["code"]]
            long_rows.append(m)
    write_csv(HERE / "retest_long_366.csv", long_rows, MF)
    if extra:
        ext = []
        for (w, cost, c, code), r in sorted(res.items()):
            if (w, cost) == ("test", COST_RT):
                continue
            m = dict(r["metrics"])
            m.update(window=w, cost=cost, role=roles[c], good=good[code])
            ext.append(m)
        write_csv(HERE / "retest_extra_cost_subperiod.csv", ext, ["window", "cost"] + MF)
    TF = ["config", "code", "entry_index", "entry_date", "entry_signal_index", "entry_signal_date",
          "entry_price", "entry_cash", "entry_reserve", "entry_shares", "entry_fee", "exit_index",
          "exit_date", "exit_signal_index", "exit_signal_date", "exit_price", "exit_cash",
          "dividends", "exit_fee", "net_return", "forced_end"]
    write_csv(HERE / "retest_trades.csv", [t for c in SCHEMES for e in etfs for t in
                                           res[("test", COST_RT, c, e["code"])]["trades"]], TF)
    write_csv(HERE / "retest_nav.csv.gz", [x for c in SCHEMES for e in etfs for x in
                                           res[("test", COST_RT, c, e["code"])]["nav"]],
              ["config", "code", "date", "row_index", "nav", "shares", "cash", "reserve",
               "held_session"], gz=True)
    # 61 行宽表
    wide = []
    for e in etfs:
        row = {"code": e["code"], "name": e["name"], "good": good[e["code"]],
               "groups": "/".join(e["groups"])}
        m0 = res[("test", COST_RT, "HOLD", e["code"])]["metrics"]
        row.update(first=m0["first"], last=m0["last"], sessions=m0["sessions"],
                   calendar_days=m0["calendar_days"], annual_supported=m0["cagr"] is not None)
        for c in SCHEMES:
            m = res[("test", COST_RT, c, e["code"])]["metrics"]
            p = LABEL[c]
            row.update({f"{p}_累计收益": m["total_return"], f"{p}_年化": m["cagr"],
                        f"{p}_自然胜率": m["wr"], f"{p}_交易数": m["entries"],
                        f"{p}_自然退出": m["natural"], f"{p}_盈利笔": m["wins"],
                        f"{p}_MDD": m["mdd"]})
        wide.append(row)
    wf = list(wide[0].keys())
    write_csv(HERE / "per_etf_61_wide.csv", wide, wf)
    # 简洁展示表
    brief = [{"代码": r["code"], "名称": r["name"], "优秀": "★" if r["good"] else "",
              "候选A胜率": pct(r["候选A_自然胜率"]), "候选A年化": pct(r["候选A_年化"]),
              "候选B胜率": pct(r["候选B_自然胜率"]), "候选B年化": pct(r["候选B_年化"]),
              "纯MACD年化": pct(r["纯MACD_年化"]), "持有年化": pct(r["持有_年化"]),
              "持有累计": pct(r["持有_累计收益"])} for r in wide]
    write_csv(HERE / "per_etf_61_brief.csv", brief, list(brief[0].keys()))

    # ---- 阶段2：与原结果比对
    print("[3] 读取原 results 并比对")
    phase_map = {"test": "test"}
    if extra:
        phase_map.update(test_part1="test_part1", test_part2="test_part2")
    diffs, cstats = compare(res, phase_map)
    write_csv(HERE / "diffs.csv", diffs, ["kind", "key", "field", "retest", "original"])
    by_kind = {}
    for d in diffs:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    main_prefix = f"test|{COST_RT}|"
    main_trade_keys = {f"{c}|{e['code']}" for c in SCHEMES for e in etfs}
    main_diffs = [d for d in diffs if d["key"].startswith(main_prefix) or (
        d["kind"] != "per_etf" and "|".join(d["key"].split("|")[:2]) in main_trade_keys)]
    main_groups_with_diff = sorted({d["key"] for d in diffs if d["key"].startswith(main_prefix)})
    (HERE / "diffs.json").write_text(json.dumps(
        {"total": len(diffs), "main_scope_total": len(main_diffs), "by_kind": by_kind, "main_groups_with_per_etf_diff":
         main_groups_with_diff, "first_200": diffs[:200]}, ensure_ascii=False, indent=2))

    print("[4] 输入哈希核验（结束）")
    pins1 = check_inputs()
    ver = {
        "status": "PASS" if not diffs and all(v["ok"] for v in pins1.values()) else
        ("DIFFS_FOUND" if all(v["ok"] for v in pins1.values()) else "INPUT_CHANGED"),
        "started_utc": log["started_utc"],
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "argv": sys.argv, "python": sys.version,
        "window": WIN, "cost_bps_round_trip": COST_RT, "schemes": SCHEMES,
        "etfs": len(etfs), "main_groups": len(main_keys),
        "extra_groups": len(res) - len(main_keys),
        "comparison": cstats, "tolerance": "abs/rel 1e-9; 日期、index、forced、计数精确相等",
        "diff_total": len(diffs), "diff_main_scope_366": len(main_diffs),
        "diff_extra_scope": len(diffs) - len(main_diffs), "diff_by_kind": by_kind,
        "inputs_ok_start": all(v["ok"] for v in pins0.values()),
        "inputs_ok_end": all(v["ok"] for v in pins1.values()),
        "input_hashes_end": {k: v["actual"] for k, v in pins1.items()},
        "independence": "仅导入标准库；未导入原 engine/reference/verify/search；原results仅在全部结果写出后读取比对",
        "script_sha256": sha(__file__),
    }
    (HERE / "verification.json").write_text(json.dumps(ver, ensure_ascii=False, indent=2))
    print(json.dumps({k: ver[k] for k in ("status", "main_groups", "extra_groups", "comparison",
                                           "diff_total", "diff_main_scope_366", "diff_by_kind")}, ensure_ascii=False))
    return res, wide


if __name__ == "__main__":
    main()
