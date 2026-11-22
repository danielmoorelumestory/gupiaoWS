/* 页面逻辑：读取 data/etf.json、data/holdings.json、data/status.json 渲染。 */
(function () {
  "use strict";
  const D = window.DXZ;
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const cls = x => (D.isNum(x) ? (x > 0 ? "pos" : x < 0 ? "neg" : "") : "mut");
  let ETF = null, HOLD = null, STATUS = null, cur = { code: null, from: null, to: null, basis: "scale_nav" };

  async function load(path) {
    const r = await fetch(path + "?t=" + Date.now());
    if (!r.ok) throw new Error(path + " HTTP " + r.status);
    return r.json();
  }

  // ---------------------------------------------------------------- tabs
  // 路由：#rank / #detail/510310 / #hold / #about。点 tab 写入 hash（进入浏览器历史），
  // 前进/后退或外部改 hash 时由 hashchange 统一渲染。
  const TABS = ["rank", "detail", "hold", "composite", "about"];
  document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
  function tabHash(t) { return "#" + t + (t === "detail" && cur.code ? "/" + cur.code : ""); }
  function renderTab(t) {
    document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x.dataset.tab === t));
    document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x.id === "tab-" + t));
    if (t === "detail") renderDetail();
    if (t === "composite" && window.DXZC_UI) window.DXZC_UI.render(); // 合成观察（composite.js，独立数据 composite.json）
  }
  function showTab(t) {
    const h = tabHash(t);
    if (location.hash !== h) location.hash = h; // 触发 hashchange → route()
    else renderTab(t);
  }
  function route() {
    if (!ETF) return;
    const m = location.hash.match(/^#(\w+)(?:\/(\d{6}))?/);
    const t = m && TABS.includes(m[1]) ? m[1] : "rank";
    if (m && m[2] && ETF.etfs[m[2]] && m[2] !== cur.code) { cur.code = m[2]; cur.from = cur.to = null; }
    renderTab(t);
  }
  window.addEventListener("hashchange", route);

  // ---------------------------------------------------------------- status
  const staleTag = e => e.stale === true ? '<span class="tag amber">陈旧</span>' : e.stale == null ? '<span class="tag amber">新鲜度未知</span>' : "";
  function renderStatus() {
    const fr = ETF.freshness || {};
    const st = (STATUS && STATUS.stages) || ETF.stages || {};
    const bad = Object.entries(st).filter(([, v]) => v && v.ok === false).map(([k]) => k);
    let h = `数据生成 ${esc(ETF.generated_at.replace("T", " ").slice(0, 16))} · 应有最新交易日 <b>${esc(ETF.expected_latest || "无法确认")}</b>`;
    h += ` · 排名日 <b class="${fr.rank_stale ? "bad" : ""}">${esc(ETF.rank_day || "无")}</b> · `;
    h += fr.all_shares_fresh ? `<span class="ok">12 只份额均到应有日期</span>` : `<span class="bad">份额未全部到最新</span>`;
    if (bad.length) h += ` · <span class="bad">本次阶段失败/不完整（沿用缓存）：${bad.join("、")}</span>`;
    const flags = (fr.flags || []).concat(STATUS && STATUS.stages && STATUS.stages.reports && STATUS.stages.reports.ok === false ? ["定期报告阶段有问题，见“汇金披露”页"] : []);
    if (flags.length) h += `<div class="bad small">${flags.map(esc).join("；")}</div>`;
    h += ` <button id="btn-reload" class="mini">重新加载数据</button><span id="new-data"></span>`;
    $("#status").innerHTML = h;
    $("#btn-reload").onclick = reloadData;
    $("#gen").textContent = ETF.generated_at;
  }

  // ---------------------------------------------------------------- 排名
  function renderRank() {
    $("#rank-day").textContent = ETF.rank_day || "—";
    let h = `<tr><th class="l">ETF</th><th>成交额(亿元)</th><th>成交额/前20日均</th><th>场内份额(亿份)</th><th>1日Δ份额(亿份)</th><th>5日Δ</th><th>20日Δ</th><th>净申赎近似(亿元)</th><th>样本内份额分位</th></tr>`;
    for (const r of ETF.ranking) {
      const e = ETF.etfs[r.code];
      const ratio = D.isNum(r.amount_ratio20) ? r.amount_ratio20.toFixed(2) + "×" : "—";
      const hot = D.isNum(r.amount_ratio20) && r.amount_ratio20 >= 2 ? ' <span class="tag red">放量</span>' : "";
      h += `<tr class="click" data-code="${r.code}"><td class="l">${esc(e.name)} <span class="mut">${r.code}</span>${staleTag(e)}</td>
        <td>${D.yi(r.amount)}</td><td>${ratio}${hot}</td><td>${D.yi(r.share)}</td>
        <td class="${cls(r.chg1)}">${D.signedYi(r.chg1)}</td><td class="${cls(r.chg5)}">${D.signedYi(r.chg5)}</td>
        <td class="${cls(r.chg20)}">${D.signedYi(r.chg20)}</td><td class="${cls(r.net_sub_est)}">${D.signedYi(r.net_sub_est)}</td>
        <td>${D.pct(r.pct_rank, 0)}${r.pct_rank_from && r.pct_rank_from > ETF.start ? `<div class="mut small">自${r.pct_rank_from}折算后</div>` : ""}</td></tr>`;
    }
    $("#rank-table").innerHTML = h;
    $("#rank-table").querySelectorAll("tr.click").forEach(tr => tr.addEventListener("click", () => { cur.code = tr.dataset.code; cur.from = cur.to = null; showTab("detail"); }));
  }

  // ---------------------------------------------------------------- 单只
  let detailBound = false;
  function setupDetail() {
    const sel = $("#sel-etf");
    sel.innerHTML = ETF.ranking.map(r => `<option value="${r.code}">${esc(ETF.etfs[r.code].name)} ${r.code}</option>`).join("");
    if (detailBound) return;
    detailBound = true;
    sel.addEventListener("change", () => { cur.code = sel.value; cur.from = cur.to = null; history.replaceState(null, "", tabHash("detail")); renderDetail(); });
    $("#d-from").addEventListener("change", e => { cur.from = e.target.value; renderDetail(); });
    $("#d-to").addEventListener("change", e => { cur.to = e.target.value; renderDetail(); });
    $("#scale-basis").addEventListener("change", e => { cur.basis = e.target.value; renderDetail(); });
    document.querySelectorAll("#tab-detail .presets button").forEach(b => b.addEventListener("click", () => { // 只绑单只走势页，不误绑合成观察的 #c-presets
      const rows = ETF.etfs[cur.code].rows;
      [cur.from, cur.to] = D.presetRange(rows, b.dataset.p);
      renderDetail();
    }));
    $("#btn-csv").addEventListener("click", () => {
      const e = ETF.etfs[cur.code];
      const rows = D.sliceRange(e.rows, cur.from, cur.to);
      const blob = new Blob([D.toCSV(rows, e)], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${e.code}_${cur.from}_${cur.to}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  }

  function card(k, v, s, c) { return `<div class="card"><div class="k">${k}</div><div class="v ${c || ""}">${v}</div><div class="s">${s || ""}</div></div>`; }

  function renderDetail() {
    if (!ETF) return;
    cur.code = cur.code || ETF.ranking[0].code;
    const e = ETF.etfs[cur.code];
    if (!cur.from || !cur.to) [cur.from, cur.to] = D.presetRange(e.rows, "250");
    $("#sel-etf").value = cur.code; $("#d-from").value = cur.from; $("#d-to").value = cur.to;
    $("#scale-basis").value = cur.basis;
    const rows = D.sliceRange(e.rows, cur.from, cur.to);
    const st = D.rangeStats(rows), sm = e.summary, L = sm.latest || {};
    let c = "";
    c += card("最新场内份额", D.yi(L.share) + " 亿份", (L.d || "—") + " " + staleTag(e));
    c += card("规模（份额×净值）", D.yi(L.scale_nav) + " 亿元", "净值 " + (D.isNum(L.nav) ? L.nav.toFixed(4) : "—"));
    c += card("1 日份额变化", D.signedYi(L.chg1) + " 亿份", "净申赎近似 " + D.signedYi(L.net_sub_est) + " 亿元", cls(L.chg1));
    c += card("5 日份额变化", D.signedYi(L.chg5) + " 亿份", "", cls(L.chg5));
    c += card("20 日份额变化", D.signedYi(L.chg20) + " 亿份", "", cls(L.chg20));
    if (st.count) {
      const sp = st.splitInRange ? `（区间含份额折算 ${st.splitDays.join("、")}，仅比较 ${st.comparableFrom} 起 ${st.comparableCount} 天）` : "";
      c += card("区间内分位", D.pct(st.pctRank, 0), `区间最高 ${D.yi(st.max.share)}（${st.max.d}）${st.isAtMax ? " · 当前即最高" : ""}${sp}`);
      c += card("区间份额变化", st.splitInRange ? "不可比" : D.signedYi(st.shareChange) + " 亿份",
        st.splitInRange ? `区间跨份额折算日 ${st.splitDays.join("、")}，单位不同，不做末减初` : `${st.first.d} → ${st.last.d}`, cls(st.shareChange));
      c += card("区间净申赎近似合计", D.signedYi(st.netSubSum) + " 亿元", `区间第 2 个交易日起 ${st.netSubDays} 个可算日之和（与末减初同口径；缺口/折算日不计）`, cls(st.netSubSum));
    }
    const cf = sm.comparable_from && sm.comparable_from > sm.first ? `折算后可比区间 ${sm.comparable_from}~${sm.last}` : `样本 ${sm.first}~${sm.last}`;
    c += card("历史位置（样本内）", D.pct(sm.pct_rank, 0), `${cf}，最高 ${D.yi(sm.max && sm.max.share)}（${sm.max && sm.max.d}）`);
    $("#cards").innerHTML = c;
    const miss = sm.missing_days || [];
    $("#coverage").innerHTML = `覆盖：首个可用日 <b>${esc(sm.first)}</b>，最新 <b>${esc(sm.last)}</b>，有份额 ${sm.count} 天 / 期间交易日 ${sm.trading_days} 天` +
      (miss.length ? `，缺 ${miss.length} 天（不插值、不补 0）：${esc(miss.slice(0, 12).join("、"))}${miss.length > 12 ? "…" : ""}` : "，无缺日") +
      (sm.splits && sm.splits.length ? `；份额折算/拆分日：${esc(sm.splits.join("、"))}（该日不计份额变化）` : "") +
      `。交易所简称：${esc(e.exchange_name || "—")}${e.name_check ? "" : ' <span class="tag red">名称未核验</span>'}。样本起点为本工具采集起点 ${esc(ETF.start)}，“历史分位/最高”仅指样本内。`;
    $("#scale-title").textContent = cur.basis === "scale_nav" ? "规模 = 份额 × 同日单位净值（亿元，右轴）" : "规模估算 = 份额 × 收盘价（亿元，估算口径，右轴）";
    drawCharts(rows);
    renderDayTable(rows, e);
  }

  function renderDayTable(rows, e) {
    let h = `<tr><th class="l">日期</th><th>份额(亿份)</th><th>Δ份额(亿份)</th><th>净值</th><th>规模(亿元)</th><th>净申赎近似(亿元)</th><th>收盘</th><th>成交额(亿元)</th><th>放量比</th><th class="l">备注</th></tr>`;
    for (let i = rows.length - 1; i >= 0; i--) {
      const r = rows[i];
      const note = [r.split ? "份额折算" : "", r.event || "", r.share == null ? "无份额数据" : ""].filter(Boolean).join(" ");
      h += `<tr><td class="l">${r.d}</td><td>${D.yi(r.share)}</td><td class="${cls(r.d1)}">${D.signedYi(r.d1)}</td>
        <td>${D.isNum(r.nav) ? r.nav.toFixed(4) : "—"}</td><td>${D.yi(r[cur.basis])}</td>
        <td class="${cls(r.net_sub_est)}">${D.signedYi(r.net_sub_est)}</td><td>${D.isNum(r.close) ? r.close.toFixed(3) : "—"}</td>
        <td>${D.yi(r.amount)}</td><td>${D.isNum(r.amount_ratio20) ? r.amount_ratio20.toFixed(2) + "×" : "—"}</td><td class="l mut">${esc(note)}</td></tr>`;
    }
    $("#day-table").innerHTML = h;
  }

  // ---------------------------------------------------------------- 图表（三张联动 SVG，同一 x 轴）
  // 份额与规模按用户要求合并为一张双轴图：份额=左轴（亿份，橙色面积），规模=右轴（亿元，蓝色折线）
  const PADL = 46, PADR = 46, PADT = 8, PADB = 18;
  // Y 轴/提示的数值格式：默认 份/元 → 亿（0 位小数）；价格图用元、3 位小数（不能除以 1e8）
  const fmtYi = v => D.yi(v, 0);
  const fmtPrice = v => (D.isNum(v) ? v.toFixed(3) : "—");
  // series: [{key, color, mode, fmt}]，第 1 条用左轴并画网格，第 2 条（可选）用右轴
  function drawOne(svg, rows, series) {
    const W = svg.clientWidth || 600, H = svg.clientHeight || 190;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const n = rows.length;
    const x = i => PADL + (n <= 1 ? 0 : (i * (W - PADL - PADR)) / (n - 1));
    const scs = series.map(s => D.scale(rows.map(r => r[s.key]), s.mode === "bar" || s.mode === "area")); // 面积/柱从 0 起，避免夸大
    if (!scs.some(Boolean)) { svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle">区间内无数据</text>`; return { x, n, ys: [] }; }
    const ys = scs.map(sc => sc ? (v => PADT + (1 - (v - sc.lo) / (sc.hi - sc.lo)) * (H - PADT - PADB)) : null);
    let g = "";
    for (let k = 0; k <= 3; k++) {
      const yy = PADT + (1 - k / 3) * (H - PADT - PADB);
      g += `<line x1="${PADL}" x2="${W - PADR}" y1="${yy}" y2="${yy}" stroke="#eef0f3"/>`;
      series.forEach((s, j) => {
        const sc = scs[j]; if (!sc) return;
        const v = sc.lo + ((sc.hi - sc.lo) * k) / 3, f = s.fmt || fmtYi;
        g += j === 0 ? `<text x="${PADL - 4}" y="${yy + 3}" text-anchor="end"${series.length > 1 ? ` style="fill:${s.color}"` : ""}>${f(v)}</text>`
                     : `<text x="${W - PADR + 4}" y="${yy + 3}" text-anchor="start" style="fill:${s.color}">${f(v)}</text>`;
      });
    }
    const ticks = Math.min(W < 500 ? 4 : 6, n); // 窄屏少放日期刻度，避免重叠
    for (let k = 0; k < ticks; k++) {
      const i = Math.round((k * (n - 1)) / Math.max(1, ticks - 1));
      g += `<text x="${x(i)}" y="${H - 4}" text-anchor="${k === 0 ? "start" : k === ticks - 1 ? "end" : "middle"}">${rows[i].d.slice(2)}</text>`;
    }
    series.forEach((s, j) => {
      const sc = scs[j], y = ys[j], key = s.key, color = s.color; if (!sc) return;
      if (s.mode === "bar") {
        const bw = Math.max(1, (W - PADL - PADR) / Math.max(n, 1) - 1);
        rows.forEach((r, i) => { if (D.isNum(r[key])) g += `<rect x="${x(i) - bw / 2}" y="${y(r[key])}" width="${bw}" height="${y(sc.lo) - y(r[key])}" fill="${color}" opacity=".7"/>`; });
      } else {
        // 有缺口就断开折线（不插值）
        let d = "", segs = [], seg = [];
        rows.forEach((r, i) => { if (D.isNum(r[key])) seg.push([x(i), y(r[key])]); else if (seg.length) { segs.push(seg); seg = []; } });
        if (seg.length) segs.push(seg);
        for (const sg of segs) {
          d += "M" + sg.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join("L");
          if (s.mode === "area") g += `<path d="M${sg[0][0]},${y(sc.lo)}L${sg.map(p => p.join(",")).join("L")}L${sg[sg.length - 1][0]},${y(sc.lo)}Z" fill="${color}" opacity=".3"/>`;
        }
        g += `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"/>`;
      }
    });
    g += `<g fill="none" stroke="#555" stroke-dasharray="3,3" pointer-events="none">
      <line class="cross cross-v" x1="0" x2="0" y1="${PADT}" y2="${H - PADB}" visibility="hidden"/>
      ${series.map((s, j) => `<line class="cross cross-h" data-j="${j}" x1="${PADL}" x2="${W - PADR}" y1="0" y2="0" visibility="hidden"${series.length > 1 ? ` stroke="${s.color}"` : ""}/>`).join("")}
    </g>`;
    svg.innerHTML = g;
    return { x, n, ys };
  }

  function drawCharts(rows) {
    // 价格图固定用 rows.close（BaoStock 不复权收盘价，元），不随规模口径切换
    const svgs = [$("#ch-price"), $("#ch-share"), $("#ch-amt")];
    const specs = [
      [{ key: "close", color: "#8250df", mode: "line", fmt: fmtPrice }],
      [{ key: "share", color: "#f08a24", mode: "area" }, { key: cur.basis, color: "#2f6fde", mode: "line" }],
      [{ key: "amount", color: "#9aa3ad", mode: "bar" }]
    ];
    const geos = svgs.map((s, j) => drawOne(s, rows, specs[j]));
    const tip = $("#tip"), box = document.querySelector(".chart-box");
    function move(ev) {
      const svg = ev.currentTarget, rect = svg.getBoundingClientRect();
      const cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
      const W = rect.width, n = rows.length;
      if (!n) return;
      const i = Math.max(0, Math.min(n - 1, Math.round(((cx - PADL) / (W - PADL - PADR)) * (n - 1))));
      const r = rows[i], px = geos[svgs.indexOf(svg)].x(i);
      svgs.forEach((s, j) => {
        const v = s.querySelector(".cross-v");
        if (v) {
          v.setAttribute("x1", geos[j].x(i)); v.setAttribute("x2", geos[j].x(i));
          v.setAttribute("visibility", "visible");
        }
        s.querySelectorAll(".cross-h").forEach(h => {
          const k = +h.dataset.j, val = r[specs[j][k].key], y = geos[j].ys[k];
          if (D.isNum(val) && y) {
            const py = y(val);
            h.setAttribute("y1", py); h.setAttribute("y2", py);
            h.setAttribute("visibility", "visible");
          } else h.setAttribute("visibility", "hidden");
        });
      });
      tip.hidden = false;
      tip.innerHTML = `${r.d}<br>收盘价 ${fmtPrice(r.close)} 元（不复权）<br>份额 ${D.yi(r.share)} 亿份（Δ ${D.signedYi(r.d1)}）<br>规模 ${D.yi(r[cur.basis])} 亿元<br>成交额 ${D.yi(r.amount)} 亿元`;
      const br = box.getBoundingClientRect();
      const left = rect.left - br.left + px;
      tip.style.left = Math.min(left + 10, br.width - 190) + "px";
      tip.style.top = (rect.top - br.top + 10) + "px";
    }
    function leave() { tip.hidden = true; svgs.forEach(s => s.querySelectorAll(".cross").forEach(l => l.setAttribute("visibility", "hidden"))); }
    svgs.forEach(s => { s.onmousemove = move; s.ontouchstart = move; s.ontouchmove = move; s.onmouseleave = leave; s.ontouchend = leave; s.ontouchcancel = leave; });
  }
  window.addEventListener("resize", () => { if ($("#tab-detail").classList.contains("on")) renderDetail(); });

  // ---------------------------------------------------------------- 汇金披露
  const STATUS_TXT = {
    named_top10: "已列示前十名具名持有人",
    no_top10_section: "报告未列示前十名持有人（已核验正文可读、身份与持有人章节；未知，不是 0）",
    parse_failed: "前十名表解析校验未通过（未采用，未知）",
    unreadable: "原文文本层不足/疑似扫描版（未知）",
    unverified: "身份或持有人章节未核验，不能断言未列示（未知）",
    download_or_extract_failed: "下载/提取失败（未知）",
  };
  const NOT_NAMED = `<span class="mut">报告未给具名表</span>`;
  function cellEntity(pt, label) {
    if (pt.status !== "named_top10") return NOT_NAMED;
    const ens = (pt.entities || []).filter(x => x.label === label);
    if (!ens.length) return `<span class="mut">未进前十（≠0）</span>`;
    const tot = ens.reduce((a, x) => a + x.shares, 0);
    const sub = ens.map(x => `${ens.length > 1 ? D.yi(x.shares) + " · " : ""}${x.pct}% · p${x.page}`).join("<br>");
    return `${D.yi(tot)}${ens.length > 1 ? `<div class="mut small">${ens.length} 个产品</div>` : ""}<div class="mut small">${sub}</div>`;
  }
  function cellLB(pt, key) {
    if (pt.status !== "named_top10") return NOT_NAMED;
    if (!pt.narrow_identified && key === "narrow_own_lb") return `<span class="mut">前十名未识别到（≠0）</span>`;
    const v = pt[key];
    return D.isNum(v) ? `≥ ${D.yi(v)}<div class="mut small">前十名已识别下限</div>` : `<span class="mut">未识别（≠0）</span>`;
  }
  function renderHold() {
    if (!HOLD) { $("#hold-list").innerHTML = '<div class="note warn">尚未生成 holdings.json</div>'; return; }
    const reps = HOLD.reports, cov = HOLD.coverage || {}, ln = HOLD.latest_named || {};
    // 动态：各基金最近一期已验收具名报告（M2）
    const lnVals = Object.values(ln).filter(Boolean);
    let note = `<b>最近一期可核验的具名时点</b>（按已下载并通过校验的报告动态推导）：` +
      (lnVals.length ? (cov.latest_named_min === cov.latest_named_max ? `各基金均为 <b>${esc(cov.latest_named_max)}</b>` : `<b>${esc(cov.latest_named_min)}～${esc(cov.latest_named_max)}</b>（各基金见下表）`) : "无") +
      (cov.funds_without_named && cov.funds_without_named.length ? `；无任何具名报告：${esc(cov.funds_without_named.join("、"))}` : "") +
      `。它们是历史时点事实，不是当前持仓。报告状态统计：${esc(Object.entries(cov.status_counts || {}).map(([k, v]) => (STATUS_TXT[k] || k).split("（")[0] + " " + v).join("；"))}。`;
    const iss = HOLD.issues || {};
    if (Object.keys(iss).length) note += `<div class="bad small">本次采集问题（已沿用有效缓存）：${esc(Object.entries(iss).map(([c, xs]) => c + "：" + xs.join("，")).join("；"))}</div>`;
    // 固定历史观察：2026 年中报格式（2026-11-22 实测），与上面的动态覆盖分开
    const p26 = (cov.periods || {})["2026-06-30"];
    if (p26) note += `<div style="margin-top:6px"><b>2026 年中报格式实测</b>（2026-11-22 首次核验，按当前数据计数）：观察池 2026 年中期报告 ${Object.values(p26).reduce((a, b) => a + b, 0)} 份中，“未列示前十名持有人”${p26.no_top10_section || 0} 份、仍列示 ${p26.named_top10 || 0} 份、其它/未知 ${Object.entries(p26).filter(([k]) => !["no_top10_section", "named_top10"].includes(k)).reduce((a, [, v]) => a + v, 0)} 份。因此 2026-06-30 起不能再假设每半年都有具名前十名数据。这一变化对应的规则条文本工具没有取得原文核对，不在此归因；可自行查阅证监会原始发布：<a href="https://www.csrc.gov.cn/csrc/c100028/c7619936/content.shtml" target="_blank" rel="noopener">证监会公告页</a>、<a href="https://neris.csrc.gov.cn/falvfagui/rdqsHeader/mainbody?secFutrsLawId=b8783096f8fa49d2bab977fd46532cf8" target="_blank" rel="noopener">法规库条目</a>。</div>`;
    $("#fmt2026").innerHTML = note;
    const byCode = {};
    reps.forEach(r => (byCode[r.code] = byCode[r.code] || []).push(r));
    let h = "";
    for (const code of ETF.ranking.map(r => r.code)) { // 与成交排名同序（对象数字键会被 JS 自动按数值排序）
      const e = ETF.etfs[code];
      const rs = (byCode[code] || []).slice().sort((a, b) => a.period_end.localeCompare(b.period_end));
      const pts = (HOLD.series[code] || []);
      const mg = (HOLD.managers || {})[code];
      h += `<div class="hcard"><h3>${esc(e.name)} <span class="mut">${code}</span> <span class="tag">最近具名：${esc(ln[code] || "无")}</span></h3>`;
      if (mg) h += `<div class="meta">报告原文基金管理人：${esc((mg.found || []).join("、") || "未识别")}${mg.ok ? "（与观察池一致）" : ' <span class="tag red">与观察池不一致/未识别</span>'}</div>`;
      if (!rs.length) { h += `<div class="mut">未发现定期报告（接口失败或无数据），见状态日志。</div></div>`; continue; }
      h += `<div class="tablebox"><table class="grid"><tr><th class="l">期末</th><th class="l">报告</th><th>汇金投资(亿份)</th><th>汇金资管(亿份)</th><th>汇金资管委托产品(亿份)</th><th>汇金自有：前十名已识别下限</th><th>含委托产品下限</th><th>机构合计上限线索(亿份)</th><th class="l">状态</th></tr>`;
      for (const pt of pts) {
        const r = rs.find(x => x.period_end === pt.period_end) || {};
        const up = D.isNum(pt.inst_upper) ? `≤ ${D.yi(pt.inst_upper)}<div class="mut small">${esc(pt.inst_upper_basis)}；原文机构合计 ${D.yi(pt.inst_shares)}</div>` : "—";
        const reuse = pt.reused_cache ? `<div class="bad small">本次失败（${esc(pt.last_error)}），沿用旧有效记录</div>` : "";
        h += `<tr><td class="l">${pt.period_end}</td><td class="l"><a href="${esc(pt.url)}" target="_blank" rel="noopener">${esc(pt.kind)}</a><div class="mut small">公告 ${esc(pt.announce_date)}</div></td>
          <td>${cellEntity(pt, "汇金投资")}</td><td>${cellEntity(pt, "汇金资管")}</td><td>${cellEntity(pt, "汇金资管委托产品")}</td>
          <td>${cellLB(pt, "narrow_own_lb")}</td><td>${cellLB(pt, "narrow_with_products_lb")}</td><td>${up}</td>
          <td class="l">${esc(STATUS_TXT[pt.status] || pt.status)}${r.top10 && r.top10.ratio_basis ? `<div class="mut small">比例口径：${esc(r.top10.ratio_basis)}</div>` : ""}${reuse}</td></tr>`;
      }
      h += `</table></div><div class="mut small">“下限”= 前十名中已识别汇金主体份额之和；未进前十的主体、场外份额不在内，不是汇金体系完整持仓。“机构合计上限线索”只在原文注明机构含联接基金时扣联接，否则用完整机构合计，含保险/券商等全部机构，不等于汇金。</div>`;
      for (const r of rs) {
        h += `<details><summary>${esc(r.period_end)} ${esc(r.kind)} 原文摘录（${esc(STATUS_TXT[r.status] || r.status)}）</summary>`;
        h += `<div class="meta">原文：<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> · 公告 ${esc(r.announce_date)} · 共 ${r.pages || "?"} 页 · sha256 ${esc((r.sha256 || "").slice(0, 12))}${r.status_reason ? " · 判定依据：" + esc(r.status_reason) : ""}</div>`;
        if (r.top10 && r.top10.rows) {
          h += `<div class="meta">表头：${esc(r.top10.heading)}（第 ${r.top10.head_page} 页）· 比例口径“${esc(r.top10.ratio_basis)}” ${r.top10.note ? "· " + esc(r.top10.note) : ""}</div><table class="grid">`;
          h += `<tr><th>序</th><th class="l">持有人全称（原文）</th><th>份额(份)</th><th>原披露比例</th><th>PDF页</th><th class="l">识别</th></tr>`;
          for (const x of r.top10.rows) h += `<tr><td>${x.rank}</td><td class="l">${esc(x.name)}</td><td>${x.shares.toLocaleString("zh-CN")}</td><td>${x.pct}%</td><td>${x.page}</td><td class="l">${x.scope ? esc(x.label) + (x.scope === "broad" ? "（广义，不与汇金合计）" : x.scope === "info" ? "（国资平台，仅提示）" : "") : ""}</td></tr>`;
          h += `</table>`;
        }
        if (r.big20 && r.big20.rows && r.big20.rows.length) {
          h += `<div class="meta">“单一投资者持有比例≥20%”表（第 ${r.big20.head_page} 页）：</div><ul>`;
          for (const b of r.big20.rows) h += `<li class="small">${esc(b.label || "未标注")} · ${esc(b.period)} · 期末 ${D.isNum(b.end) ? b.end.toLocaleString("zh-CN") + " 份" : "?"}（${b.end_pct}%）${b.exact_share_match ? ` · 与具名表“${esc(b.exact_share_match)}”份额完全相同（推断，非报告明示）` : (b.label === "机构" ? " · 匿名，身份未知" : "")}</li>`;
          h += `</ul>`;
        }
        const s = r.structure;
        if (s && s.valid) h += `<div class="meta">持有人结构（第 ${s.page} 页）：机构 ${D.yi(s.inst_shares)} 亿份（${s.inst_pct}%），个人 ${D.yi(s.indiv_shares)} 亿份（${s.indiv_pct}%）${D.isNum(s.feeder_shares) ? `，表中联接基金 ${D.yi(s.feeder_shares)} 亿份` : "，表中无联接基金列（不代表没有联接基金）"}；${esc(s.inst_upper_basis || "")}。机构合计含保险、券商等全部机构，<b>不等于汇金合计</b>。${s.note ? `<div class="snip">原文注：${esc(s.note)}</div>` : ""}</div>`;
        h += `</details>`;
      }
      h += `</div>`;
    }
    $("#hold-list").innerHTML = h;
  }

  // ---------------------------------------------------------------- 口径
  function renderAbout() {
    const src = (ETF.sources || []).concat((HOLD && HOLD.sources) || []);
    let h = `<h3>这是什么</h3><p>复刻视频中的观察方式：按成交额排名主流宽基 ETF，看单只 ETF 场内份额与规模的历史曲线、逐日明细、近几日增减和历史位置；另从基金定期报告原文提取汇金具名持仓。观察池是“${esc(ETF.pool_name)}”，<b>不是国家队持仓清单</b>。</p>`;
    h += `<h3>口径</h3><ul>
      <li>单位：原始数据为 份 / 元，页面显示 亿份 / 亿元；CSV 保留原始单位。</li>
      <li>规模主口径 = 场内份额 × 同日单位净值；“份额×收盘价”只作估算口径单独提供，两者不混用。交易所公布的是份额，本工具没有拿到官方“规模（元）”原值。</li>
      <li>净申赎近似 =（份额<sub>t</sub> − 前一交易日份额）× 当日净值。是近似值，不是现金净流量事实；前一交易日缺数据则不算（不跨缺口）。</li>
      <li>不同 ETF 每份净值不同，<b>跨 ETF 的份额相加没有意义</b>，本页不做份额合计。</li>
      <li>成交额是买卖成交总额，<b>不是净流入</b>；“放量比”= 当日成交额 / 前 20 个交易日均值。</li>
      <li>“历史分位/最高”只在本工具采集样本（起点 ${esc(ETF.start)}）内计算；样本内有份额折算（如 510310 2024-09-20）时，只在最后一次折算日之后的可比区间计算。跨折算的区间不给“份额末减初”。</li>
      <li>新鲜度：“应有最新交易日”按北京时间 18:00 检查阈值判断，这只是本工具的检查规则，不代表上游 18:00 后一定已发布；交易日历获取失败时显示“无法确认”。</li>
      <li>汇金：狭义汇金体系 = 中央汇金投资 + 中央汇金资管（自有），委托产品单列；社保、养老金、证金等广义口径单列，不与汇金合计；匿名、未进前十、未披露都是“未知”而非 0。</li>
      <li>禁止的推断：当日 ETF 净申购 ≠ 汇金买入；按旧持仓不变推算的“今日比例”不是真实比例，本页不提供。</li>
    </ul><h3>来源</h3><ul>`;
    for (const s of src) h += `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>：${esc(s.method)}</li>`;
    h += `</ul>`;
    if (STATUS) h += `<h3>最近一次更新日志（${STATUS.log_total} 条，显示末尾）</h3><div class="snip">${STATUS.log.map(esc).join("<br>")}</div>`;
    $("#about").innerHTML = h;
  }

  // ---------------------------------------------------------------- 加载 / 重新加载（M2）
  async function loadAll() {
    const etf = await load("data/etf.json");
    let hold = null, status = null;
    try { hold = await load("data/holdings.json"); } catch (e) { hold = null; }
    try { status = await load("data/status.json"); } catch (e) { status = null; }
    ETF = etf; HOLD = hold; STATUS = status;
    renderStatus(); renderRank(); setupDetail(); renderHold(); renderAbout();
    if ($("#tab-detail").classList.contains("on")) renderDetail();
    if (window.DXZC_UI) window.DXZC_UI.load().catch(() => {}); // 19 池产物独立加载，失败不影响本页其它标签
  }
  async function reloadData() {
    const b = $("#btn-reload");
    if (b) { b.disabled = true; b.textContent = "加载中…"; }
    try { await loadAll(); } catch (e) { $("#new-data").innerHTML = ` <span class="bad">重新加载失败：${esc(e.message)}，仍显示旧数据</span>`; if (b) { b.disabled = false; b.textContent = "重新加载数据"; } }
  }
  // 轻量检查：每 5 分钟只取 status.json，updated_at（任一产物最近写入，含仅更新报告）变化就提示，
  // 不自动替换用户正在看的内容。旧产物没有 updated_at 时退回 generated_at。
  const stamp = st => st && (st.updated_at || st.generated_at);
  setInterval(async () => {
    try {
      const st = await load("data/status.json");
      if (ETF && stamp(st) && stamp(st) !== stamp(STATUS))
        $("#new-data").innerHTML = ` <span class="tag red">有新数据（${esc(stamp(st).slice(0, 16).replace("T", " "))}），点“重新加载数据”</span>`;
    } catch (e) { /* 网络失败忽略 */ }
  }, 300000);

  // ---------------------------------------------------------------- 观测台集成：本模块更新服务
  // 由 dashboard_server.py 在 /holdings/ 提供时，同源 ../api/holdings/* 可用；独立 8793 预览时不可用。
  const API = "../api/holdings/";
  const STATE_TXT = { idle: "空闲", running: "正在更新", succeeded: "最近一次成功", partial: "最近一次完成但有问题", failed: "最近一次失败", unavailable: "模块不可用" };
  const KIND_TXT = { update: "份额/行情增量", reports: "定期报告检查", full: "全部（份额/行情+报告）" };
  let svcLast = null, svcTimer = null;
  const fmtT = x => x ? esc(String(x).slice(0, 16).replace("T", " ")) : "—";
  const okT = x => x ? fmtT(x) : "尚无成功记录";
  function renderSvc(st) {
    const box = $("#svc");
    if (!st) {
      box.innerHTML = `<span class="mut">独立预览：本页没有接入后台更新服务（从资金观测台 <code>dashboard_server.py</code> 的“份额与规模 / 汇金披露”入口打开可自动更新与“立即更新”）。</span>`;
      $("#back").hidden = true;
      return;
    }
    $("#back").hidden = false;
    const run = st.state === "running";
    let h = `<b>本模块数据独立更新</b> · 状态：<span class="${st.state === "failed" || st.state === "unavailable" ? "bad" : st.state === "partial" ? "warnc" : st.state === "succeeded" ? "ok" : ""}">${esc(STATE_TXT[st.state] || st.state)}${st.kind ? "（" + esc(KIND_TXT[st.kind] || st.kind) + "）" : ""}</span>`;
    if (run) h += ` · 开始 ${fmtT(st.started_at)}`;
    else if (st.finished_at) h += ` · 结束 ${fmtT(st.finished_at)}`;
    if (st.message) h += `<div class="${st.state === "failed" || st.state === "partial" || st.state === "unavailable" ? "bad" : "mut"} small">${esc(st.message)}</div>`;
    h += `<div class="mut small">自动检查：${st.auto ? "开启" : "关闭"} · 份额/行情最后成功 ${okT(st.last_success && st.last_success.update)}，下次检查 ${fmtT(st.next_check && st.next_check.update)} · 定期报告最后成功 ${okT(st.last_success && st.last_success.reports)}，下次检查 ${fmtT(st.next_check && st.next_check.reports)}</div>`;
    h += ` <button id="btn-update" class="mini" ${run || !st.available ? "disabled" : ""}>${run ? "更新中…" : "立即更新"}</button>`;
    box.innerHTML = h;
    const b = $("#btn-update");
    if (b) b.onclick = triggerUpdate;
  }
  async function pollSvc() {
    clearTimeout(svcTimer);
    let st = null;
    try {
      const r = await fetch(API + "status?t=" + Date.now(), { cache: "no-store" });
      if (r.ok) st = await r.json();
    } catch (e) { st = null; }
    const wasRunning = svcLast && svcLast.state === "running";
    renderSvc(st);
    if (st && wasRunning && st.state !== "running") reloadData(); // 任务刚结束：自动读取新产物（失败也会显示旧数据+状态）
    svcLast = st;
    if (st) svcTimer = setTimeout(pollSvc, st.state === "running" ? 3000 : 60000);
  }
  async function triggerUpdate() {
    const b = $("#btn-update");
    if (b) { b.disabled = true; b.textContent = "提交中…"; }
    try {
      const r = await fetch(API + "refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const j = await r.json().catch(() => ({}));
      if (r.status === 409) $("#new-data").innerHTML = ` <span class="tag amber">已有更新任务在运行</span>`;
      else if (!r.ok) $("#new-data").innerHTML = ` <span class="bad">无法启动更新：${esc(j.error || r.status)}</span>`;
    } catch (e) { $("#new-data").innerHTML = ` <span class="bad">无法连接本地服务：${esc(e.message)}</span>`; }
    pollSvc();
  }

  (async function boot() {
    pollSvc();
    try { await loadAll(); } catch (e) { $("#status").innerHTML = `<span class="bad">无法加载 data/etf.json：${esc(e.message)}。请先运行 run.py update，或在观测台服务里点“立即更新”。</span>`; return; }
    route();
  })();
})();
