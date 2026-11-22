/* 纯逻辑（无 DOM），浏览器挂 window.DXZ，Node 用 require 测试。 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DXZ = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const YI = 1e8;

  function isNum(x) { return typeof x === "number" && isFinite(x); }

  /** 份/元 → 亿份/亿元 文本；null/undefined → “—”（未知不是 0）。 */
  function yi(x, digits) {
    if (!isNum(x)) return "—";
    const d = digits == null ? 2 : digits;
    return (x / YI).toFixed(d);
  }

  function signedYi(x, digits) {
    if (!isNum(x)) return "—";
    const s = yi(x, digits);
    return x > 0 ? "+" + s : s;
  }

  function pct(x, digits) {
    if (!isNum(x)) return "—";
    return (x * 100).toFixed(digits == null ? 1 : digits) + "%";
  }

  /** 按闭区间 [from, to] 截取（ISO 日期字符串比较）。 */
  function sliceRange(rows, from, to) {
    return rows.filter(r => (!from || r.d >= from) && (!to || r.d <= to));
  }

  /**
   * 区间统计（M1）。
   * - 区间内（首行之后）出现份额折算行时，份额单位改变：shareChange 置 null，最高/最低/分位只在
   *   “区间内最后一次折算日（含）之后”的可比段计算，并返回 comparableFrom / splitInRange。
   * - netSubSum 只累加区间第 2 行起的 net_sub_est，与“末减初”的份额变化口径一致
   *   （区间首日的净申赎是相对区间外前一交易日的，不计入）。
   */
  function rangeStats(rows) {
    const have = rows.filter(r => isNum(r.share));
    if (!have.length) return { count: 0, tradingDays: rows.length, missing: rows.map(r => r.d) };
    const splitRows = rows.slice(1).filter(r => r.split);
    const splitInRange = splitRows.length > 0;
    const compFrom = splitInRange ? splitRows[splitRows.length - 1].d : have[0].d;
    const comp = have.filter(r => r.d >= compFrom);
    const last = have[have.length - 1];
    let mx = comp[0], mn = comp[0];
    for (const r of comp) { if (r.share > mx.share) mx = r; if (r.share < mn.share) mn = r; }
    const le = comp.filter(r => r.share <= last.share).length;
    const nets = rows.slice(1).map(r => r.net_sub_est).filter(isNum);
    return {
      count: have.length,
      tradingDays: rows.length,
      missing: rows.filter(r => !isNum(r.share)).map(r => r.d),
      first: have[0], last: last, max: mx, min: mn,
      splitInRange: splitInRange, splitDays: splitRows.map(r => r.d), comparableFrom: compFrom,
      comparableCount: comp.length,
      pctRank: le / comp.length,
      shareChange: splitInRange ? null : last.share - have[0].share,
      netSubSum: nets.length ? nets.reduce((a, b) => a + b, 0) : null,
      netSubDays: nets.length,
      isAtMax: last.share === mx.share,
    };
  }

  /** 最近 n 个交易日的份额增量（来自后端 d1，缺口/折算为 null 的日子不计并单独报数）。 */
  function recentDeltas(rows, n) {
    const tail = rows.slice(-n);
    return tail.map(r => ({ d: r.d, d1: r.d1, net: r.net_sub_est }));
  }

  function csvCell(v) {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  /** CSV：原始单位（份/元/元每份），空 = 无数据（不是 0）。 */
  function toCSV(rows, meta) {
    const head = ["日期", "代码", "场内份额(份)", "单位净值(元/份)", "收盘价(元)", "规模=份额×净值(元)",
      "规模估算=份额×收盘价(元)", "较前一交易日份额变化(份)", "净申赎近似=Δ份额×当日净值(元)",
      "5日份额变化(份)", "20日份额变化(份)", "成交额(元)", "成交额/前20日均值", "份额折算标记", "分红/折算说明"];
    const lines = [head.join(",")];
    for (const r of rows) {
      lines.push([r.d, meta.code, r.share, r.nav, r.close, r.scale_nav, r.scale_close, r.d1, r.net_sub_est,
        r.chg5, r.chg20, r.amount, r.amount_ratio20, r.split ? "是" : "", r.event].map(csvCell).join(","));
    }
    return "﻿" + lines.join("\n") + "\n";
  }

  /** 预设区间：最近 n 个交易日（按行），'ytd' 今年以来，'all' 全部。 */
  function presetRange(rows, key) {
    if (!rows.length) return [null, null];
    const end = rows[rows.length - 1].d;
    if (key === "all") return [rows[0].d, end];
    if (key === "ytd") return [end.slice(0, 4) + "-01-01", end];
    const n = Number(key);
    return [rows[Math.max(0, rows.length - n)].d, end];
  }

  /** 两组数值的坐标尺度（给 SVG 用）：含 0 选项，留 5% 边距。 */
  function scale(vals, includeZero) {
    const v = vals.filter(isNum);
    if (!v.length) return null;
    let lo = Math.min.apply(null, v), hi = Math.max.apply(null, v);
    if (includeZero) lo = Math.min(lo, 0);
    if (hi === lo) { hi += Math.abs(hi) * 0.05 || 1; lo -= Math.abs(lo) * 0.05 || 1; }
    const pad = (hi - lo) * 0.05;
    return { lo: includeZero && lo === 0 ? 0 : lo - pad, hi: hi + pad };
  }

  return { yi, signedYi, pct, sliceRange, rangeStats, recentDeltas, toCSV, presetRange, scale, isNum };
});
