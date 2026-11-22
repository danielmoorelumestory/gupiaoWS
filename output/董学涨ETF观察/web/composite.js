/* 合成观察：视频19只ETF观察池 · 份额合计观察指数。读取 data/composite.json、data/status.json。
   纯函数挂 DXZC（Node 可 require 测试）；浏览器里另挂 DXZC_UI（由 app.js 在切到 #composite 时调用）。 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else { root.DXZC = api; }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const isNum = x => typeof x === "number" && isFinite(x);

  /** 区间预设：base=从基期，250=近一年(按交易日)，ytd，all。返回 [from, to]。 */
  function rangeFor(rows, key, baseDate) {
    if (!rows.length) return [null, null];
    const end = rows[rows.length - 1].d;
    if (key === "base") return [baseDate || rows[0].d, end];
    if (key === "all") return [rows[0].d, end];
    if (key === "ytd") return [end.slice(0, 4) + "-01-01", end];
    const n = Number(key);
    return [rows[Math.max(0, rows.length - n)].d, end];
  }

  /** 区间汇总：首末“完整”日的指数变化；区间内（首个完整日之后）有拆分 → 不可比。 */
  function rangeSummary(rows) {
    const full = rows.filter(r => isNum(r.idx));
    if (!full.length) return { count: 0 };
    const a = full[0], b = full[full.length - 1];
    const splitIn = rows.some(r => r.d > a.d && r.d <= b.d && r.split && r.split.length);
    const chgs = rows.filter(r => r.d > a.d && isNum(r.chg)).map(r => r.chg);
    return {
      count: full.length, first: a, last: b, splitIn,
      idxChange: splitIn ? null : b.idx - a.idx,
      chgSum: chgs.length ? chgs.reduce((x, y) => x + y, 0) : null, chgDays: chgs.length,
      incomplete: rows.filter(r => r.n < 19).map(r => r.d),
    };
  }

  /** 某日成员明细：份额、较前一交易日变化（任一端缺失或拆分日 → null）、占当日合计变化比例、占合计份额比例。 */
  function contrib(rows, i, members) {
    const r = rows[i], p = i > 0 ? rows[i - 1] : null;
    const tot = isNum(r.sum) ? r.sum : null;
    return members.map((m, k) => {
      const q = r.q[k], q0 = p ? p.q[k] : null;
      const split = (r.split || []).includes(m.code);
      const dlt = isNum(q) && isNum(q0) && !split ? q - q0 : null;
      return { ...m, q, dlt, split,
        shareOfChg: isNum(dlt) && isNum(r.chg) && r.chg !== 0 ? dlt / r.chg : null,
        weight: isNum(q) && tot ? q / tot : null };
    });
  }

  /** 价格日涨跌（相对前一行同字段；任一缺失 → null）。 */
  function pctChange(rows, i, key) {
    if (i <= 0) return null;
    const a = rows[i - 1][key], b = rows[i][key];
    return isNum(a) && isNum(b) && a > 0 ? b / a - 1 : null;
  }

  return { rangeFor, rangeSummary, contrib, pctChange, isNum };
});

if (typeof window !== "undefined" && typeof document !== "undefined") (function () {
  "use strict";
  const C = window.DXZC, D = window.DXZ;
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const YI = 1e8;
  const f2 = (v, d) => (C.isNum(v) ? v.toFixed(d == null ? 2 : d) : "—");
  const yi = (v, d) => (C.isNum(v) ? (v / YI).toFixed(d == null ? 2 : d) : "—");
  const syi = (v, d) => (C.isNum(v) ? (v > 0 ? "+" : "") + (v / YI).toFixed(d == null ? 2 : d) : "—");
  const cls = v => (C.isNum(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "mut");
  let DATA = null, STAT = null, loading = null, bound = false;
  const ui = { key: "all", from: null, to: null, bench: "sh.000300", pick: null };

  async function load() {
    const get = async p => { const r = await fetch(p + "?t=" + Date.now(), { cache: "no-store" }); if (!r.ok) throw new Error(p + " HTTP " + r.status); return r.json(); };
    loading = (async () => {
      try { DATA = await get("data/composite.json"); } catch (e) { DATA = { error: e.message }; }
      try { STAT = await get("data/status.json"); } catch (e) { STAT = null; }
    })();
    await loading;
    if ($("#tab-composite").classList.contains("on")) render();
  }

  function bench() { return (DATA.benchmarks || []).find(b => b.key === ui.bench) || DATA.benchmarks[0]; }
  const bkey = k => (k === "sh.000300" ? "hs300" : k === "sh.000001" ? "sh" : k);

  function statusHtml() {
    const st = (STAT && STAT.stages && STAT.stages.composite) || DATA.stage || {};
    let h = `数据截至 <b>${esc(DATA.data_last || "无")}</b>（19 只完整的最后交易日）· 应有最新交易日 <b>${esc(DATA.expected_latest || "无法确认")}</b> · `;
    h += DATA.stale === false ? `<span class="ok">已到应有日期</span>` : DATA.stale ? `<span class="bad">陈旧</span>` : `<span class="bad">新鲜度未知</span>`;
    h += ` · 产物生成 ${esc((DATA.generated_at || "").replace("T", " ").slice(0, 16))}`;
    if (st.ok === false) h += `<div class="bad small">最近一次 19 池更新失败/不完整（${esc((st.at || "").replace("T", " ").slice(0, 16))}）：${esc(st.error || (st.issues || []).join("；"))}。下方为保留的旧数据。</div>`;
    if (DATA.flags && DATA.flags.length) h += `<div class="bad small">${DATA.flags.map(esc).join("；")}</div>`;
    return h;
  }

  function setup() {
    if (bound) return; bound = true;
    $("#c-bench").innerHTML = DATA.benchmarks.map(b => `<option value="${b.key}">${esc(b.label)}（${esc(b.unit)}）</option>`).join("");
    $("#c-bench").value = ui.bench;
    $("#c-bench").addEventListener("change", e => { ui.bench = e.target.value; render(); });
    $("#c-from").addEventListener("change", e => { ui.from = e.target.value; ui.key = null; ui.pick = null; render(); });
    $("#c-to").addEventListener("change", e => { ui.to = e.target.value; ui.key = null; ui.pick = null; render(); });
    document.querySelectorAll("#c-presets button").forEach(b => b.addEventListener("click", () => { ui.key = b.dataset.p; ui.from = ui.to = null; ui.pick = null; render(); }));
    window.addEventListener("resize", () => { if ($("#tab-composite").classList.contains("on")) render(); });
  }

  function coverHtml(all) {
    const fc = DATA.first_complete, ei = DATA.early_incomplete || [];
    const nFull = all.filter(r => C.isNum(r.sum)).length;
    let h = `数据覆盖：取数自 ${esc(all[0].d)}，<b>首个 19 只完整日 ${esc(fc || "无")}</b>，至 ${esc(DATA.data_last || "无")} 共 ${nFull} 个完整交易日（共 ${all.length} 个交易日）。`;
    if (ei.length) {
      const miss = [...new Set(ei.flatMap(x => x.missing))];
      h += ` 之前 ${ei.length} 个交易日因 ${miss.map(c => { const m = DATA.members.find(x => x.code === c); return esc((m ? m.name : "") + " " + c) + "（份额首日 " + esc((DATA.members_first || {})[c] || "—") + "）"; }).join("、")} 尚未上市、交易所无份额，合计不计算（不补 0、不缩池）。`;
    }
    h += " 更早无法回溯：上述成员 2022-07 下旬才成立，此前不存在 19 只共同数据。";
    const pf = DATA.price_first || {};
    h += ` 价格首日：沪深300 ${esc(pf["sh.000300"] || "—")}、上证 ${esc(pf["sh.000001"] || "—")}、510300 ${esc(pf["sh.510300"] || "—")}；缺失日断线不插值。`;
    return h;
  }

  function card(k, v, s, c) { return `<div class="card"><div class="k">${k}</div><div class="v ${c || ""}">${v}</div><div class="s">${s || ""}</div></div>`; }

  function render() {
    if (!DATA) { if (!loading) load(); return; }
    if (DATA.error) { $("#c-status").innerHTML = `<span class="bad">无法加载 data/composite.json：${esc(DATA.error)}。请运行 run.py update（或 run.py composite）。</span>`; return; }
    setup();
    $("#c-status").innerHTML = statusHtml();
    const all = DATA.rows;
    if (ui.key) [ui.from, ui.to] = C.rangeFor(all, ui.key, DATA.base_date);
    $("#c-all-btn").textContent = `全部历史（${(DATA.first_complete || all[0].d).slice(0, 7).replace("-", ".")}起）`;
    $("#c-cover").innerHTML = coverHtml(all);
    $("#c-from").value = ui.from; $("#c-to").value = ui.to;
    document.querySelectorAll("#c-presets button").forEach(b => b.classList.toggle("on", b.dataset.p === ui.key));
    const rows = all.filter(r => r.d >= ui.from && r.d <= ui.to);
    const lastFull = [...all].reverse().find(r => C.isNum(r.idx));
    const lastAny = all[all.length - 1];
    const s = C.rangeSummary(rows);
    let c = "";
    c += DATA.base_ok ? card(`观察指数（${esc(lastFull ? lastFull.d : "—")}）`, f2(lastFull && lastFull.idx), `基期 ${esc(DATA.base_date)} = 100`)
                      : card("观察指数", "不可计算", esc(DATA.base_error || "基期无效"), "bad");
    c += card("当日份额变化", syi(lastFull && lastFull.chg) + " 亿份", lastFull && lastFull.split && lastFull.split.length ? "含份额折算，机械变化不计" : "19 只合计较前一交易日", cls(lastFull && lastFull.chg));
    c += card("19 只完整度", `${lastAny.n}/19`, `${esc(lastAny.d)}${lastAny.n < 19 ? "：有成员缺数据，当日合计不可算" : ""}`, lastAny.n < 19 ? "bad" : "");
    c += card("19 只份额合计", yi(lastFull && lastFull.sum) + " 亿份", `基期合计 ${yi(DATA.base_sum)} 亿份`);
    if (s.count) c += card("区间指数变化", s.splitIn ? "不可比" : (s.idxChange > 0 ? "+" : "") + f2(s.idxChange), s.splitIn ? "区间跨份额折算日" : `${esc(s.first.d)} → ${esc(s.last.d)}`, cls(s.idxChange));
    if (s.count) c += card("区间日变化合计", syi(s.chgSum) + " 亿份", `${s.chgDays} 个可算日（缺口/折算日不计）`, cls(s.chgSum));
    $("#c-cards").innerHTML = c;
    const b = bench();
    $("#c-bench-title").textContent = `${b.label}（${b.unit}，独立 Y 轴；BaoStock 不复权收盘）`;
    const pre = rows.some(r => r.pre_split);
    const allSp = [...(DATA.split_dates || [])].sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : 0));
    const sd = allSp.filter(x => x.date >= ui.from && x.date <= ui.to);
    const lastSp = allSp.length ? allSp[allSp.length - 1].date : null;
    $("#c-split").innerHTML = pre || sd.length ? `<div class="note warn small">区间含份额折算（东方财富分红送配记录，已核对与交易所份额跳变同日）：${(sd.length ? sd : allSp).map(x => esc(x.date + " " + x.code)).join("、")}。折算日的份额变化为机械变化，已置空不计；最后一次折算日 ${esc(lastSp)} 之前（灰底）的指数水平含折算前份额，与之后<b>不可直接比较</b>，跨折算区间的指数涨跌显示为“不可比”。</div>` : "";
    draw(rows, b);
    const idx = ui.pick ? all.findIndex(r => r.d === ui.pick) : all.indexOf(rows.length ? rows[rows.length - 1] : lastAny);
    renderMembers(all, idx);
  }

  // ------------------------------------------------------------ 三张联动图（各自独立 Y 轴，共享日期轴、悬浮提示与横纵虚线）
  const PADL = 52, PADR = 12, PADT = 8, PADB = 18;
  function hideTip() { // 重绘前收起旧提示并清除定位，避免视口变窄后残留的 left 撑出横向溢出
    const t = $("#c-tip"); if (!t) return;
    t.hidden = true; t.style.left = "0px"; t.style.top = "0px";
  }
  function draw(rows, b) {
    hideTip();
    const bk = bkey(b.key);
    const specs = [
      { svg: $("#c-ch-idx"), key: "idx", color: "#2f6fde", mode: "line", fmt: v => v.toFixed(1) },
      { svg: $("#c-ch-chg"), key: "chg", color: null, mode: "bar", div: YI, fmt: v => v.toFixed(0) },
      { svg: $("#c-ch-px"), key: bk, color: "#8250df", mode: "line", fmt: v => (b.unit === "元" ? v.toFixed(3) : v.toFixed(0)) },
    ];
    const geos = specs.map(sp => drawOne(sp, rows));
    const tip = $("#c-tip"), box = $("#c-chartbox");
    function at(ev) {
      const svg = ev.currentTarget, rect = svg.getBoundingClientRect();
      const cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
      const n = rows.length; if (!n) return -1;
      return Math.max(0, Math.min(n - 1, Math.round(((cx - PADL) / (rect.width - PADL - PADR)) * (n - 1))));
    }
    function move(ev) {
      const i = at(ev); if (i < 0) return;
      const r = rows[i], rect = ev.currentTarget.getBoundingClientRect();
      specs.forEach((sp, j) => {
        const g = geos[j], v = sp.svg.querySelector(".cross-v"), h = sp.svg.querySelector(".cross-h");
        if (v) { v.setAttribute("x1", g.x(i)); v.setAttribute("x2", g.x(i)); v.setAttribute("visibility", "visible"); }
        const val = r[sp.key];
        if (h && g.y && C.isNum(val)) { const py = g.y(sp.div ? val / sp.div : val); h.setAttribute("y1", py); h.setAttribute("y2", py); h.setAttribute("visibility", "visible"); }
        else if (h) h.setAttribute("visibility", "hidden");
      });
      const gi = DATA.rows.indexOf(r), pc = C.pctChange(DATA.rows, gi, bk);
      tip.hidden = false;
      tip.innerHTML = `${r.d}${r.pre_split ? "（折算前水平）" : ""}<br>观察指数 ${f2(r.idx)}<br>当日份额变化 ${syi(r.chg)} 亿份${r.split && r.split.length ? "（折算日不计）" : ""}<br>完整度 ${r.n}/19<br>${esc(b.label)} ${C.isNum(r[bk]) ? (b.unit === "元" ? r[bk].toFixed(3) : r[bk].toFixed(2)) : "—"}${pc == null ? "" : `（${pc > 0 ? "+" : ""}${(pc * 100).toFixed(2)}%）`}`;
      const br = box.getBoundingClientRect();
      const want = rect.left - br.left + geos[0].x(i) + 10, tw = tip.offsetWidth || 200;
      tip.style.left = Math.max(4, Math.min(want + tw > br.width - 4 ? want - tw - 20 : want, br.width - tw - 4)) + "px"; // 右侧放不下就放到虚线左侧，始终在框内
      tip.style.top = (rect.top - br.top + 8) + "px";
    }
    function leave() { tip.hidden = true; specs.forEach(sp => sp.svg.querySelectorAll(".cross").forEach(l => l.setAttribute("visibility", "hidden"))); }
    function click(ev) { const i = at(ev); if (i >= 0) { ui.pick = rows[i].d; renderMembers(DATA.rows, DATA.rows.indexOf(rows[i])); } }
    specs.forEach(sp => { const s = sp.svg; s.onmousemove = move; s.ontouchstart = move; s.ontouchmove = move; s.onmouseleave = leave; s.ontouchend = leave; s.ontouchcancel = leave; s.onclick = click; });
  }

  function drawOne(sp, rows) {
    const svg = sp.svg, W = svg.clientWidth || 600, H = svg.clientHeight || 180, n = rows.length;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const x = i => PADL + (n <= 1 ? 0 : (i * (W - PADL - PADR)) / (n - 1));
    const vals = rows.map(r => (C.isNum(r[sp.key]) ? (sp.div ? r[sp.key] / sp.div : r[sp.key]) : null));
    const sc = D.scale(vals, sp.mode === "bar");
    if (!sc) { svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">区间内无数据</text>`; return { x, y: null }; }
    if (sp.mode === "bar" && sc.hi < 0) sc.hi = 0;
    const y = v => PADT + (1 - (v - sc.lo) / (sc.hi - sc.lo)) * (H - PADT - PADB);
    let g = "";
    // 折算前区域灰底
    const ps = rows.map((r, i) => (r.pre_split ? i : -1)).filter(i => i >= 0);
    if (ps.length) g += `<rect x="${x(ps[0])}" y="${PADT}" width="${Math.max(1, x(ps[ps.length - 1]) - x(ps[0]))}" height="${H - PADT - PADB}" fill="#eef0f3"/>`;
    for (let k = 0; k <= 3; k++) {
      const v = sc.lo + ((sc.hi - sc.lo) * k) / 3, yy = y(v);
      g += `<line x1="${PADL}" x2="${W - PADR}" y1="${yy}" y2="${yy}" stroke="#eef0f3"/><text x="${PADL - 4}" y="${yy + 3}" text-anchor="end">${sp.fmt(v)}</text>`;
    }
    const ticks = Math.min(W < 500 ? 4 : 6, n);
    for (let k = 0; k < ticks; k++) {
      const i = Math.round((k * (n - 1)) / Math.max(1, ticks - 1));
      g += `<text x="${x(i)}" y="${H - 4}" text-anchor="${k === 0 ? "start" : k === ticks - 1 ? "end" : "middle"}">${rows[i].d.slice(2)}</text>`;
    }
    if (sp.mode === "bar") {
      const bw = Math.max(1, (W - PADL - PADR) / Math.max(n, 1) - 1), y0 = y(0);
      g += `<line x1="${PADL}" x2="${W - PADR}" y1="${y0}" y2="${y0}" stroke="#c9ced6"/>`;
      vals.forEach((v, i) => { if (C.isNum(v)) g += `<rect x="${x(i) - bw / 2}" y="${Math.min(y(v), y0)}" width="${bw}" height="${Math.max(0.5, Math.abs(y(v) - y0))}" fill="${v >= 0 ? "#d1242f" : "#1a7f37"}" opacity=".75"/>`; });
    } else {
      let d = "", seg = [];
      const flush = () => { if (seg.length) d += "M" + seg.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join("L"); seg = []; };
      vals.forEach((v, i) => { if (C.isNum(v)) seg.push([x(i), y(v)]); else flush(); }); // 缺口断线，不插值
      flush();
      g += `<path d="${d}" fill="none" stroke="${sp.color}" stroke-width="1.6"/>`;
      if (sp.key === "idx" && DATA.base_ok) { const bi = rows.findIndex(r => r.d === DATA.base_date); if (bi >= 0) g += `<circle cx="${x(bi)}" cy="${y(100)}" r="3" fill="${sp.color}"/><text x="${x(bi) + 5}" y="${y(100) - 4}">基期100</text>`; }
    }
    g += `<g fill="none" stroke="#444" stroke-width="1" stroke-dasharray="4,3" pointer-events="none"><line class="cross cross-v" x1="0" x2="0" y1="${PADT}" y2="${H - PADB}" visibility="hidden"/><line class="cross cross-h" x1="${PADL}" x2="${W - PADR}" y1="0" y2="0" visibility="hidden"/></g>`;
    svg.innerHTML = g;
    return { x, y };
  }

  function renderMembers(all, i) {
    if (i < 0 || !all[i]) { $("#c-members").innerHTML = ""; return; }
    const r = all[i], list = C.contrib(all, i, DATA.members);
    $("#c-mem-day").textContent = r.d + (r.n < 19 ? `（${r.n}/19，合计不可算）` : "");
    let h = `<tr><th class="l">ETF</th><th class="l">跟踪</th><th>场内份额(亿份)</th><th>较前一交易日(亿份)</th><th>占当日合计变化</th><th>占19只份额</th></tr>`;
    for (const m of list) {
      h += `<tr><td class="l">${esc(m.name)} <span class="mut">${m.code}</span></td><td class="l mut">${esc(m.index)}</td><td>${yi(m.q)}</td>
        <td class="${cls(m.dlt)}">${m.split ? '<span class="tag amber">折算日</span>' : syi(m.dlt)}</td>
        <td>${C.isNum(m.shareOfChg) ? (m.shareOfChg > 0 ? "+" : "") + (m.shareOfChg * 100).toFixed(1) + "%" : "—"}</td><td>${C.isNum(m.weight) ? (m.weight * 100).toFixed(1) + "%" : "—"}</td></tr>`;
    }
    h += `<tr><td class="l"><b>19 只合计</b></td><td></td><td><b>${yi(r.sum)}</b></td><td class="${cls(r.chg)}"><b>${syi(r.chg)}</b></td><td></td><td></td></tr>`;
    $("#c-members").innerHTML = h;
  }

  window.DXZC_UI = { load, render };
})();
