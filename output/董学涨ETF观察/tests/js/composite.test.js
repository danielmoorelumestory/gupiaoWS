const test = require("node:test");
const assert = require("node:assert");
const C = require("../../web/composite.js");
const M = Array.from({ length: 19 }, (_, k) => ({ code: "c" + k, name: "n" + k }));
const q = v => Array(19).fill(v);
const rows = [
  { d: "2025-11-19", n: 19, sum: 19e8, idx: 95, chg: null, split: [], q: q(1e8) },
  { d: "2025-11-20", n: 19, sum: 20e8, idx: 100, chg: 1e8, split: [], q: [2e8].concat(q(1e8).slice(1)) },
  { d: "2025-11-21", n: 18, sum: null, idx: null, chg: null, split: [], q: [null].concat(q(1e8).slice(1)) },
  { d: "2025-11-24", n: 19, sum: 21e8, idx: 105, chg: null, split: ["c1"], q: [3e8].concat(q(1e8).slice(1)) },
];
test("区间预设：从基期 / 全部", () => {
  assert.deepStrictEqual(C.rangeFor(rows, "base", "2025-11-20"), ["2025-11-20", "2025-11-24"]);
  assert.deepStrictEqual(C.rangeFor(rows, "all"), ["2025-11-19", "2025-11-24"]);
});
test("区间汇总：跨折算不可比，不完整日列出", () => {
  const s = C.rangeSummary(rows);
  assert.strictEqual(s.splitIn, true); assert.strictEqual(s.idxChange, null);
  assert.deepStrictEqual(s.incomplete, ["2025-11-21"]);
  const s2 = C.rangeSummary(rows.slice(0, 2));
  assert.strictEqual(s2.idxChange, 5); assert.strictEqual(s2.chgSum, 1e8);
});
test("成员贡献：缺失端/折算日为 null，不当 0", () => {
  const a = C.contrib(rows, 1, M);
  assert.strictEqual(a[0].dlt, 1e8); assert.strictEqual(a[0].shareOfChg, 1);
  const b = C.contrib(rows, 2, M);
  assert.strictEqual(b[0].dlt, null);
  const c = C.contrib(rows, 3, M);
  assert.strictEqual(c[0].dlt, null);               // 前一日缺
  assert.strictEqual(c[1].split, true); assert.strictEqual(c[1].dlt, null);
});
test("价格涨跌：缺失为 null", () => {
  const r = [{ hs300: 100 }, { hs300: 110 }, { hs300: null }];
  assert.ok(Math.abs(C.pctChange(r, 1, "hs300") - 0.1) < 1e-12);
  assert.strictEqual(C.pctChange(r, 2, "hs300"), null);
});
test("区间预设：近3年按交易日数截取，不足时从首日", () => {
  assert.deepStrictEqual(C.rangeFor(rows, "750"), ["2025-11-19", "2025-11-24"]);
  assert.deepStrictEqual(C.rangeFor(rows, "2"), ["2025-11-21", "2025-11-24"]);
});
test("区间汇总：首日不完整时从首个完整日算起", () => {
  const r2 = [{ d: "a", n: 17, sum: null, idx: null, chg: null, split: [], q: [] }].concat(rows.slice(0, 2));
  const s = C.rangeSummary(r2);
  assert.strictEqual(s.first.d, "2025-11-19"); assert.strictEqual(s.idxChange, 5);
});
