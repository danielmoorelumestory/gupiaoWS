// node --test tests/js
const test = require("node:test");
const assert = require("node:assert");
const D = require("../../web/core.js");

const rows = [
  { d: "2026-11-17", share: 100e8, net_sub_est: 1e8 },
  { d: "2026-11-18", share: null, net_sub_est: null },
  { d: "2026-11-19", share: 300e8, net_sub_est: null },
  { d: "2026-11-20", share: 200e8, net_sub_est: -2e8 },
];

test("单位与未知值显示", () => {
  assert.strictEqual(D.yi(55184887700), "551.85");
  assert.strictEqual(D.yi(null), "—");
  assert.strictEqual(D.yi(0), "0.00");
  assert.strictEqual(D.signedYi(1e8), "+1.00");
});

test("区间统计：缺日不计、分位与最高", () => {
  const s = D.rangeStats(D.sliceRange(rows, "2026-11-17", "2026-11-20"));
  assert.strictEqual(s.count, 3);
  assert.deepStrictEqual(s.missing, ["2026-11-18"]);
  assert.strictEqual(s.max.d, "2026-11-19");
  assert.ok(Math.abs(s.pctRank - 2 / 3) < 1e-9);
  assert.strictEqual(s.netSubSum, -2e8);   // 区间首日（相对区间外前值）不计，与末减初一致
  assert.strictEqual(s.netSubDays, 1);
  assert.strictEqual(s.isAtMax, false);
});

test("CSV 保留原始单位且空值不写 0", () => {
  const csv = D.toCSV(rows, { code: "510300" });
  const lines = csv.trim().split("\n");
  assert.ok(lines[0].includes("场内份额(份)"));
  assert.strictEqual(lines[2].split(",")[2], "");
  assert.strictEqual(lines[1].split(",")[2], String(100e8));
});

test("预设区间", () => {
  assert.deepStrictEqual(D.presetRange(rows, "2"), ["2026-11-19", "2026-11-20"]);
  assert.deepStrictEqual(D.presetRange(rows, "all"), ["2026-11-17", "2026-11-20"]);
  assert.deepStrictEqual(D.presetRange(rows, "ytd"), ["2026-01-01", "2026-11-20"]);
});

test("跨折算区间：不给末减初，最高/分位只在折算后可比段", () => {
  const rs = [
    { d: "2024-09-18", share: 100e8, net_sub_est: 1e8 },
    { d: "2024-09-19", share: 120e8, net_sub_est: 2e8 },
    { d: "2024-09-20", share: 60e8, net_sub_est: null, split: true },
    { d: "2024-09-23", share: 55e8, net_sub_est: -1e8 },
  ];
  const s = D.rangeStats(rs);
  assert.strictEqual(s.splitInRange, true);
  assert.strictEqual(s.shareChange, null);
  assert.strictEqual(s.comparableFrom, "2024-09-20");
  assert.strictEqual(s.max.share, 60e8);
  assert.strictEqual(s.pctRank, 0.5);
  // 折算日恰为区间首日：区间内单位一致，可以算变化
  const s2 = D.rangeStats(rs.slice(2));
  assert.strictEqual(s2.splitInRange, false);
  assert.strictEqual(s2.shareChange, -5e8);
});
