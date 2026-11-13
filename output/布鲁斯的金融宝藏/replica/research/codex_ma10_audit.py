"""Independent MA10 audit: cash/units event ledger, never imports strategy logic.

Run from replica, or anywhere: python research/codex_ma10_audit.py
Inputs are frozen local CSVs. Outputs: codex_ma10_{summary,trades}.csv, daily.csv.gz,
codex_ma10_diagnostics.json. Optional --verify-original executes the two audited
scripts ONLY AFTER independent simulation, to compare their daily NAVs.

legacy_open: original dividend convention, reinvest inferred cash at open.
close_cash: inferred/actual dividend credited to old units, reinvest at close.
signed_close: sensitivity to negative TR/price residuals, NOT clean dividends.
Fee haircut reproduces original; notional charges cash/(1+c) on buys.
No final forced liquidation. MDD includes initial capital 1.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import hashlib
import io
import json
import math
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import runpy
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research"


def read_prices(name):
    d = pd.read_csv(ROOT / "data" / name)
    d = d.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                          "最高": "high", "最低": "low"})
    d["date"] = pd.to_datetime(d.date)
    d = d.set_index("date").sort_index()
    assert not d.index.has_duplicates
    assert np.isfinite(d[["open", "close"]]).all().all()
    assert (d[["open", "close"]] > 0).all().all()
    return d


def targets(source, rule, length=10, extra_length=None):
    """Closing decision, generated forward with a rolling window and a streak.

    rule=0 always holds. Above means strictly >; equality counts as below.
    For rule 2: enter at streak>=2; keep holding while above; exit on below.
    """
    window, long_window = deque(), deque()
    streak, invested = 0, False
    # The always-invested benchmark can buy at the first observed open.
    result = {None: True} if rule == 0 else {}
    for date, close in source.close.items():
        window.append(float(close))
        if len(window) > length:
            window.popleft()
        long_window.append(float(close))
        if extra_length and len(long_window) > extra_length:
            long_window.popleft()
        above = len(window) == length and close > math.fsum(window) / length
        extra = (not extra_length or (len(long_window) == extra_length and
                  close > math.fsum(long_window) / extra_length))
        streak = streak + 1 if above else 0
        if rule == 0:
            invested = True
        elif not above or not extra:
            invested = False
        elif invested or streak >= rule:
            invested = True
        result[date] = invested
    return result


@dataclass
class Result:
    daily: pd.DataFrame
    trades: pd.DataFrame
    initial_inherited: bool
    open_entry: dict | None


def ledger(prices, decision, start, cost=0., dividend=None, convention="legacy_open",
           initial="fresh", fee="haircut", last=None):
    """Cash/units matching. Decisions are looked up at yesterday's close only.

    Dividend input is currency per price-index unit, not a daily return.
    On buy: use cash only; old_units=0 prevents buying ex-dividend entitlement.
    On sell: receive open proceeds plus the old units' dividend entitlement.
    """
    dates = prices.index
    active = [i for i, date in enumerate(dates)
              if date >= pd.Timestamp(start) and (last is None or date <= pd.Timestamp(last))]
    assert active
    first = active[0]
    dividend = {} if dividend is None else dividend
    signal_dates = sorted(date for date in decision if date is not None)
    held = initial == "carry" and first >= 2 and bool(decision.get(dates[first-2], False))
    inherited = held
    cash, units = (0., 1. / prices.close.iloc[first-1]) if held else (1., 0.)
    entry, trades, rows = None, [], []
    for i in active:
        date = dates[i]
        opening, closing = float(prices.open.iloc[i]), float(prices.close.iloc[i])
        if i:
            previous = dates[i-1]
        else:
            j = bisect.bisect_left(signal_dates, date)
            previous = signal_dates[j-1] if j else None
        want = bool(decision.get(previous, False))
        old_units, old_held = units, held
        entitlement = old_units * float(dividend.get(date, 0.))
        # Original convention reinvests the dividend before the open trade.
        if held and convention == "legacy_open":
            units += entitlement / opening
        action = ""
        fee_paid = 0.
        if want and not held:
            entry = {"buy_date": date, "buy_signal_date": previous,
                     "buy_open": opening, "entry_equity": cash, "buy_index": i}
            if fee == "notional":
                units = cash / (opening * (1 + cost))
                fee_paid = units * opening * cost
            else:
                fee_paid = cash * cost
                units = (cash - fee_paid) / opening
            cash, held, action = 0., True, "BUY"
        elif held and not want:
            proceeds = units * opening
            fee_paid = proceeds * cost
            cash, units, held, action = cash + proceeds - fee_paid, 0., False, "SELL"
            if convention != "legacy_open":
                cash += entitlement
            if entry is not None:
                trades.append({**entry, "sell_date": date, "sell_signal_date": previous,
                               "sell_open": opening, "return": cash / entry["entry_equity"] - 1,
                               "holding_sessions": i - entry["buy_index"]})
                entry = None
        # Cash dividend reinvestment at close: all-day hold exactly reproduces
        # the supplied TR close/close return if residuals are retained signed.
        if held and convention != "legacy_open":
            units += entitlement / closing
        nav = cash + units * closing
        rows.append({"date": date, "nav": nav, "held": held, "overnight_held": old_held,
                     "signal_date": previous, "want": want, "action": action,
                     "cash": cash, "units": units, "dividend_cash": entitlement,
                     "fee_cash": fee_paid})
    return Result(pd.DataFrame(rows).set_index("date"), pd.DataFrame(trades), inherited, entry)


def metrics(r):
    n = r.daily.nav
    peak = np.maximum.accumulate(np.r_[1., n.to_numpy()])
    years = (n.index[-1] - n.index[0]).days / 365.25
    t = r.trades
    product = float(np.prod(1 + t["return"])) if len(t) else 1.
    return {"first": str(n.index[0].date()), "last": str(n.index[-1].date()),
            "sessions": len(n), "nav": n.iloc[-1],
            "cagr_pct": 100 * (n.iloc[-1] ** (1 / years) - 1),
            "mdd_pct": 100 * np.min(np.r_[1., n.to_numpy()] / peak - 1),
            "closed_trades": len(t),
            "win_pct": 100 * (t["return"] > 0).mean() if len(t) else None,
            "mean_trade_pct": 100 * t["return"].mean() if len(t) else None,
            "median_trade_pct": 100 * t["return"].median() if len(t) else None,
            "mean_holding_sessions": t.holding_sessions.mean() if len(t) else None,
            "median_holding_sessions": t.holding_sessions.median() if len(t) else None,
            "held_pct": 100 * r.daily.held.mean(), "inherited": r.initial_inherited,
            "open_trade": r.open_entry is not None, "closed_trade_product": product,
            "tail_factor": n.iloc[-1] / product}


def dividend_residual(prices):
    tr = pd.read_csv(ROOT / "data/tr_H00300.csv", parse_dates=["date"]).set_index("date").close
    assert not tr.index.has_duplicates
    tr = tr.reindex(prices.index)
    # Deliberately no ffill: missing data must remain visible.
    residual = tr / tr.shift() - prices.close / prices.close.shift()
    return residual.fillna(0.), tr


def etf_dividends():
    cumulative = pd.read_csv(ROOT / "data/codex_etf_510300_dividends_sina.csv")
    amounts = cumulative["累计分红"].diff().fillna(cumulative["累计分红"])
    return dict(zip(pd.to_datetime(cumulative["日期"]), amounts))


def payable_etf_nav(prices, decision, start, cost, ex_div, payments):
    """ETF check with receivable on ex-date, cash on payment date, next-open DRIP.

    All price orders occur at open; commissions on purchases and reinvestment.
    Fractional units permitted. No leverage or access to unpaid dividend cash.
    This auxiliary ledger reports NAV only (no misleading round-trip attribution
    when receivables span multiple trades).
    """
    cash, units, held = 1., 0., False
    unpaid, rows = [], []
    for i, date in enumerate(prices.index):
        if date < pd.Timestamp(start):
            continue
        opening = prices.open.iloc[i]
        if units and date in ex_div:
            unpaid.append((payments[date], units * ex_div[date]))
        for pay_date, amount in unpaid:
            if pay_date <= date:
                cash += amount
        unpaid = [(p, a) for p, a in unpaid if p > date]
        if i:
            previous = prices.index[i-1]
        else:
            earlier = [d for d in decision if d is not None and d < date]
            previous = max(earlier) if earlier else None
        want = bool(decision.get(previous, False))
        if held and not want:
            cash += units * opening * (1-cost)
            units = 0.
        if want and cash > 0:
            units += cash / (opening * (1+cost))
            cash = 0.
        held = want
        rows.append({"date": date, "nav": cash + units * prices.close.iloc[i] + sum(a for _, a in unpaid),
                     "held": held})
    return Result(pd.DataFrame(rows).set_index("date"), pd.DataFrame(), False, None)


def synthetic_checks():
    idx = pd.bdate_range("2024-01-01", periods=5)
    p = pd.DataFrame({"open": [100, 110, 90, 120, 100],
                      "close": [100, 121, 99, 120, 100]}, index=idx)
    dec = dict(zip(idx, [True, True, False, False, False]))
    # Buy day ignores previous close and that day's dividend; sale receives
    # old-holder dividend and no sale-day intraday return.
    r = ledger(p, dec, idx[1], dividend={idx[1]: 50., idx[3]: 2.})
    assert math.isclose(r.daily.nav.iloc[0], 121/110, abs_tol=1e-12)
    assert math.isclose(r.daily.nav.iloc[2], 122/110, abs_tol=1e-12)
    assert r.trades.holding_sessions.iloc[0] == 2
    assert r.daily.action.tolist() == ["BUY", "", "SELL", ""]
    r2 = ledger(p, dec, idx[1], cost=.001, fee="notional")
    assert math.isclose(r2.daily.nav.iloc[2], 120/110*.999/1.001, abs_tol=1e-12)
    # Rule 2: one positive day never buys; holding does not require a new
    # two-day crossing; one below day cancels immediately after the close.
    q = pd.DataFrame({"close": [1, 1, 2, 3, .1, 4, 5]}, index=pd.bdate_range("2024-01-01", periods=7))
    assert list(targets(q, 2, length=2).values()) == [False, False, False, True, False, False, True]
    q2 = q.copy(); q2.iloc[-1, 0] = 1000
    assert list(targets(q, 2, length=2).values())[:-1] == list(targets(q2, 2, length=2).values())[:-1]


def verify_original(results, hs, sse, kc):
    """Import audited files strictly for post-hoc equality checks, never signals."""
    errors = []
    oldcwd, oldargv = Path.cwd(), sys.argv[:]
    try:
        os.chdir(ROOT)
        for start in ("2005-01-04", "2012-01-01"):
            sys.argv = ["ma10_backtest.py", start]
            with contextlib.redirect_stdout(io.StringIO()):
                original = runpy.run_path(str(OUT / "ma10_backtest.py"))
            for rule in (0, 1, 2):
                for cost in ((0.,) if rule == 0 else (0., .001)):
                    src = original["out"]["hold" if rule == 0 else "ma10", cost] if rule < 2 else original["o2"]["two", cost]
                    oldnav = (1+src).cumprod()
                    new = results[f"legacy|300|own|{start}|r{rule}|c{cost}"].daily.nav
                    error = float((oldnav-new).abs().max())
                    assert error < 2e-12, (start, rule, cost, error)
                    if rule:
                        our = results[f"legacy|300|own|{start}|r{rule}|c{cost}"].trades
                        orig_target = (original["d"].close > original["ma10"]) if rule == 1 else original["two_day"]()
                        held = orig_target.shift(1).fillna(False).astype(bool)
                        events = held != held.shift(1).fillna(False).astype(bool)
                        buys = events[events & held].loc[start:].index
                        sells = events[events & ~held].loc[start:].index
                        if len(buys) and len(sells) and sells[0] < buys[0]:
                            sells = sells[1:]
                        oldtrades = [(1+src.loc[b:s]).prod()-1 for b,s in zip(buys, sells)]
                        assert len(oldtrades) == len(our)
                        assert np.max(np.abs(oldtrades-our["return"].to_numpy())) < 1e-12
                    errors.append({"file": "ma10_backtest.py", "start": start, "rule": rule, "cost": cost, "max_abs_nav_error": error})
        with contextlib.redirect_stdout(io.StringIO()):
            cross = runpy.run_path(str(OUT / "ma10_cross_signal.py"))
        for label, p, start, dv in (("300", hs, "2005-01-04", cross["div300"]),
                                    ("300", hs, "2012-01-01", cross["div300"]),
                                    ("688", kc, "2020-01-16", None)):
            for source, name in ((p, "own"), (sse, "sse")):
                for rule in (0, 1, 2):
                    if rule == 0 and name == "sse":
                        continue
                    for cost in ((0.,) if rule == 0 else (0., .001)):
                        with contextlib.redirect_stdout(io.StringIO()):
                            old, oldtrades = cross["simulate"](p, cross["state"](source, rule) if rule else pd.Series(True, index=p.index), start, cost, dv)
                        new = results[f"cross|{label}|{name}|{start}|r{rule}|c{cost}"]
                        error = float((old-new.daily.nav).abs().max())
                        assert error < 2e-12, (label, name, rule, cost, error)
                        if len(oldtrades):
                            assert len(oldtrades) == len(new.trades)
                            assert np.max(np.abs(oldtrades - new.trades["return"].to_numpy())) < 1e-12
                        errors.append({"file": "ma10_cross_signal.py", "target": label, "source": name, "start": start, "rule": rule, "cost": cost, "max_abs_nav_error": error})
    finally:
        os.chdir(oldcwd); sys.argv = oldargv
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-original", action="store_true")
    args = parser.parse_args()
    synthetic_checks()
    hs, sse, kc = [read_prices(f"index_sh{code}_ohlc.csv") for code in ("000300", "000001", "000688")]
    residual, tr = dividend_residual(hs)
    clipped_cash = (residual.clip(lower=0) * hs.close.shift()).fillna(0).to_dict()
    signed_cash = (residual * hs.close.shift()).fillna(0).to_dict()
    results, summaries, trade_rows, daily_rows = {}, [], [], []

    def add(group, label, source_name, p, source, start, rule, cost,
            dividend=None, convention="legacy_open", initial="fresh", fee="haircut", extra=None, last=None):
        key = f"{group}|{label}|{source_name}|{start}|r{rule}|c{cost}"
        if extra:
            key += f"|ma{extra}"
        dec = targets(source, rule, extra_length=extra)
        result = ledger(p, dec, start, cost, dividend, convention, initial, fee, last)
        results[key] = result
        summaries.append({"key": key, "group": group, "target": label, "source": source_name,
                          "start": start, "rule": rule, "cost_bp": cost*10000, **metrics(result)})
        if len(result.trades):
            tt = result.trades.copy(); tt.insert(0, "key", key); trade_rows.append(tt)
        dd = result.daily.copy(); dd.insert(0, "key", key); daily_rows.append(dd.reset_index())
        return result

    for start in ("2005-01-04", "2012-01-01"):
        for rule in (0, 1, 2):
            for cost in ((0.,) if rule == 0 else (0., .001)):
                add("legacy", "300", "own", hs, hs, start, rule, cost, clipped_cash, initial="carry")
                for src, sn in ((hs, "own"), (sse, "sse")):
                    if rule == 0 and sn == "sse":
                        continue
                    add("cross", "300", sn, hs, src, start, rule, cost, clipped_cash)
                    add("close_clip", "300", sn, hs, src, start, rule, cost, clipped_cash, "close_cash", fee="notional")
                    add("signed_proxy", "300", sn, hs, src, start, rule, cost, signed_cash, "close_cash", fee="notional")
                    add("price_only", "300", sn, hs, src, start, rule, cost, fee="notional")
                if rule:
                    add("ma200", "300", "own", hs, hs, start, rule, cost, clipped_cash, initial="carry", extra=200)
    for start, group in (("2020-01-16", "cross"), ("2020-07-23", "live_index"),
                         ("2020-11-16", "etf_common_index")):
        for src, sn in ((kc, "own"), (sse, "sse")):
            for rule in (0, 1, 2):
                if rule == 0 and sn == "sse":
                    continue
                for cost in ((0.,) if rule == 0 else (0., .001)):
                    add(group, "688", sn, kc, src, start, rule, cost)

    # ETF prices are raw executable quotes, never adjusted-price opens.
    etf = read_prices("codex_etf_510300_sina_raw.csv")
    ex_div = etf_dividends()
    paytable = pd.read_csv(ROOT / "data/codex_etf_510300_dividend_payments_sina.csv", header=1)
    payments = {}
    for ex_date in ex_div:
        before = paytable[pd.to_datetime(paytable.iloc[:, 0], errors="coerce") < ex_date]
        row = before.iloc[0]
        payments[ex_date] = pd.Timestamp(row.iloc[1])
    # Start after ten real ETF closes so own/other-source signals have a common
    # executable sample. Also report first-listing common index signal run.
    for start in (str(etf.index[0].date()), str(etf.index[10].date())):
        for src, sn in ((etf, "etf_own"), (hs, "index300"), (sse, "sse")):
            for rule in (0, 1, 2):
                if rule == 0 and sn != "etf_own":
                    continue
                for cost in ((0.,) if rule == 0 else (0., .001)):
                    add("etf_ex_cash", "510300", sn, etf, src, start, rule, cost, ex_div, "close_cash", fee="notional")
                    result = payable_etf_nav(etf, targets(src, rule), start, cost, ex_div, payments)
                    pm = metrics(result)
                    for stat in ("closed_trades", "win_pct", "open_trade", "closed_trade_product", "tail_factor"):
                        pm[stat] = None  # NAV-only check; do not imply zero actual trades.
                    summaries.append({"key": f"etf_payable|510300|{sn}|{start}|r{rule}|c{cost}",
                                      "group": "etf_payable", "target": "510300", "source": sn,
                                      "start": start, "rule": rule, "cost_bp": cost*10000, **pm})
    f588 = ROOT / "data/codex_ma10_etf_588000_sina_raw.csv"
    if f588.exists():
        etf588 = read_prices(f588.name)
        for start in (str(etf588.index[0].date()), str(etf588.index[10].date())):
            for src, sn in ((etf588, "etf_own"), (kc, "index688"), (sse, "sse")):
                for rule in (0, 1, 2):
                    if rule == 0 and sn != "etf_own":
                        continue
                    for cost in ((0.,) if rule == 0 else (0., .001)):
                        add("etf_raw_no_div", "588000", sn, etf588, src, start, rule, cost, fee="notional")

    # Repeat on the second vendor's raw quotes, including ETF-derived signals.
    for code, filename, start, index_source, index_label, dv in (
        ("510300", "codex_etf_510300_em_raw.csv", "2012-06-11", hs, "index300", ex_div),
        ("588000", "codex_ma10_etf_588000_em_raw.csv", "2020-11-30", kc, "index688", None)):
        if not (ROOT / "data" / filename).exists():
            continue
        ep = read_prices(filename)
        for source, sn in ((ep, "etf_own"), (index_source, index_label), (sse, "sse")):
            for rule in (0, 1, 2):
                if rule == 0 and sn != "etf_own":
                    continue
                for cost in ((0.,) if rule == 0 else (0., .001)):
                    add("etf_em", code, sn, ep, source, start, rule, cost, dv, "close_cash", fee="notional")

    diagnostic = {"synthetic_checks": "passed", "input_hashes": {}, "data": {}, "official_checks": []}
    for name in ("index_sh000300_ohlc.csv", "index_sh000001_ohlc.csv", "index_sh000688_ohlc.csv", "tr_H00300.csv",
                 "codex_etf_510300_sina_raw.csv", "codex_etf_510300_dividends_sina.csv", "codex_etf_510300_dividend_payments_sina.csv",
                 "codex_etf_510300_em_raw.csv", "codex_ma10_etf_588000_sina_raw.csv", "codex_ma10_etf_588000_em_raw.csv"):
        f = ROOT / "data" / name
        if f.exists():
            diagnostic["input_hashes"][name] = hashlib.sha256(f.read_bytes()).hexdigest()
    for name, p in (("300", hs), ("001", sse), ("688", kc)):
        diagnostic["data"][name] = {"first": str(p.index[0].date()), "last": str(p.index[-1].date()), "rows": len(p),
            "equal_open_close_2005_on": int((p.open == p.close).loc["2005":].sum()),
            "ohlc_violations": int(((p.open < p.low) | (p.open > p.high) | (p.close < p.low) | (p.close > p.high)).sum())}
    for start in ("2005-01-04", "2012-01-01"):
        neg = residual.loc[start:]; neg = neg[neg < 0]
        diagnostic[f"negative_residual_{start}"] = {"count": len(neg), "sum": neg.sum(), "min": neg.min(),
            "largest": {str(k.date()): v for k, v in neg.nsmallest(10).items()}}
    diagnostic["tr_missing_2005_on"] = int(tr.loc["2005":].isna().sum())
    diagnostic["source_calendar_missing"] = {
        "sse_on_300_2005_on": len(hs.loc["2005":].index.difference(sse.index)),
        "sse_on_688": len(kc.index.difference(sse.index))}
    diagnostic["signal_equality_days"] = {name: int((p.close == p.close.rolling(10).mean()).sum())
                                          for name,p in (("300", hs), ("001", sse), ("688", kc))}
    diagnostic["kc_year_dependence"] = {}
    benchmark = results["cross|688|own|2020-01-16|r0|c0.0"].daily.nav
    br = benchmark / benchmark.shift().fillna(1.)
    for rule in (1, 2):
        n = results[f"cross|688|own|2020-01-16|r{rule}|c0.001"].daily.nav
        dr = n / n.shift().fillna(1.)
        ex = np.log(dr).groupby(dr.index.year).sum() - np.log(br).groupby(br.index.year).sum()
        cutoff = n.loc[:"2025"]
        diagnostic["kc_year_dependence"][str(rule)] = {
            "annual_return": (dr.groupby(dr.index.year).prod()-1).to_dict(),
            "through_2025_cagr_pct": 100*(cutoff.iloc[-1]**(365.25/(cutoff.index[-1]-cutoff.index[0]).days)-1),
            "annual_log_excess": ex.to_dict(), "share_2022_and_2026": ex.loc[[2022, 2026]].sum()/ex.sum()}
    for path in sorted(OUT.glob("codex_ma10_official_*.json")):
        j = json.loads(path.read_text()); rows = j["response"]["data"]
        code = path.stem.split("_")[-2]
        if code not in ("000300", "000688"):
            continue
        p = hs if code == "000300" else kc
        errors = []
        for row in rows:
            date = pd.Timestamp(row["tradeDate"])
            if date in p.index:
                errors.append({"date": str(date.date()), "local_open": p.loc[date, "open"],
                               "official_open": row["open"], "open_error": p.loc[date, "open"]-row["open"],
                               "close_error": p.loc[date, "close"]-row["close"]})
        diagnostic["official_checks"].append({"file": path.name, "url": j["url"], "rows": len(errors),
            "max_abs_open_error": max(abs(e["open_error"]) for e in errors) if errors else None,
            "samples": errors[:3]})
    if args.verify_original:
        diagnostic["original_daily_comparison"] = verify_original(results, hs, sse, kc)
    # Decomposition must work: cash intervals earn zero, each complete trade
    # multiplies capital; open tail and inherited head are explicitly separate.
    for key, result in results.items():
        if not result.initial_inherited and result.open_entry is None and len(result.trades):
            assert abs(metrics(result)["tail_factor"] - 1) < 1e-10, key
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT / "codex_ma10_summary.csv", index=False, float_format="%.12g")
    pd.concat(trade_rows, ignore_index=True).to_csv(OUT / "codex_ma10_trades.csv", index=False, float_format="%.12g")
    pd.concat(daily_rows, ignore_index=True).to_csv(OUT / "codex_ma10_daily.csv.gz", index=False, float_format="%.12g", compression="gzip")
    (OUT / "codex_ma10_diagnostics.json").write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2, default=str))
    print(summary[summary.group.isin(["legacy", "cross", "live_index", "etf_ex_cash", "etf_raw_no_div"])][
        ["group", "target", "source", "start", "rule", "cost_bp", "nav", "cagr_pct", "mdd_pct", "closed_trades", "win_pct"]].to_string(index=False))
    print("Synthetic checks and ledger reconciliation passed; evidence saved in research/codex_ma10_*.")


if __name__ == "__main__":
    main()
