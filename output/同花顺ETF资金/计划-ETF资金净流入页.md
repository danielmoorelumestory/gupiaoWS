# ETF 资金净流入趋势页 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一个部署在服务器、每天收盘后自动更新的静态网页，展示全A与宽基两个口径的 ETF 日度净流入（红绿柱）+ 上证指数叠加，看大周期资金进出趋势。

**Architecture:** cron 每晚跑 Python 采数脚本（份额差×NAV）→ 写入 SQLite → 导出 `data.json`；静态 HTML + ECharts 运行时 `fetch('data.json')` 渲染。nginx 托管静态目录。

**Tech Stack:** Python 3.14 + `requests` + 标准库 `sqlite3`（采数/存储）；`akshare` 仅深市历史回补一次性使用；前端 ECharts 5.4.3（cdnjs），纯静态 HTML。

**Spec:** `output/同花顺ETF资金/设计-ETF资金净流入页.md`

## Global Constraints

- 只用匿名、不登录的公开接口：沪份额 `query.sse.com.cn/commonQuery.do`（`sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L`）、深份额 `fund.szse.cn/api/report/ShowReport`、NAV 东财 `api.fund.eastmoney.com/f10/lsjz`、指数东财。
- 价格口径固定 **NAV（东财 DWJZ）**，不用成交均价。
- 净流入 `flow = (份额_t − 份额_前一交易日) × NAV_t`，单位元；展示换算**亿元**（元/1e8）。
- 沪 `TOT_VOL` 单位万份，×10000 为份。
- 柱颜色 A 股惯例：**红=净流入(正)、绿=净流出(负)**。
- 折算/拆分剔除阈值：**单日份额变动绝对值 / 前值 > 0.5 视为疑似折算，当日该只剔除**。
- 只做全A + 宽基两条；不做盘中预估、单只榜单、行业/黄金/港股、持续校准。
- 代码落位 `output/同花顺ETF资金/app/`。
- 页面必须注明："自建估算（份额差×NAV），非同花顺原口径；无盘中数据，T+1；深市历史约 6 个月。"

## Review Focus

- **份额折算/拆分日**（份额骤变）→ 应剔除、不计入合计，不画假巨柱。测试归 Task 3。
- **NAV 缺失/QDII 晚披露**（某只当日无 NAV）→ 该只当日跳过，不拖累合计。测试归 Task 3。
- **新上市无前一交易日份额**（code 仅出现在 t 日）→ 跳过，不按建仓算。测试归 Task 3。
- **停牌/某只当日缺份额记录**（code 仅在前值）→ 跳过。测试归 Task 3。
- **深市历史仅约 6 个月**导致早期全A偏沪 → `data.json` 带免责 note，页面显示。测试归 Task 5。

---

### Task 1: 宽基白名单 + 份额/NAV 响应解析（纯函数）

**Files:**
- Create: `output/同花顺ETF资金/app/universe.py`
- Create: `output/同花顺ETF资金/app/broad_base.json`
- Create: `output/同花顺ETF资金/app/parse.py`
- Test: `output/同花顺ETF资金/app/tests/test_parse.py`
- Test fixtures: `output/同花顺ETF资金/app/tests/fixtures/sse_shares.json`, `szse_shares.json`, `nav.json`（从真实响应截取少量条目保存）

**Interfaces:**
- Produces:
  - `universe.BROAD_BASE: set[str]`、`universe.is_broad(code: str) -> bool`
  - `parse.parse_sse_shares(raw: dict) -> dict[str, float]`（code→份，已×10000）
  - `parse.parse_szse_shares(raw: dict) -> dict[str, float]`（code→份）
  - `parse.parse_nav(raw: dict) -> float | None`（取 `DWJZ`，无则 None）

- [ ] **Step 1: 保存 fixtures** —— 实跑一次沪/深份额与东财 NAV 接口，各截取 3–5 条真实响应存入 `tests/fixtures/`（Run：见 Global Constraints 的接口；仅留非敏感字段）。

- [ ] **Step 2: 写失败测试** `tests/test_parse.py`：

```python
def test_parse_sse_shares_converts_wan_to_fen():
    raw = json.load(open("tests/fixtures/sse_shares.json"))
    out = parse_sse_shares(raw)
    assert out["510300"] == pytest.approx(4581768.77 * 10000)  # 万份×10000
def test_parse_szse_shares_returns_fen(): ...   # 断言某深市 code 的份额为份
def test_parse_nav_picks_dwjz():
    assert parse_nav(json.load(open("tests/fixtures/nav.json"))) == 4.1203
def test_parse_nav_missing_returns_none():
    assert parse_nav({"Datas": []}) is None
def test_is_broad_true_for_hs300_false_for_sector():
    assert is_broad("510300") and not is_broad("512480")
```

- [ ] **Step 3: 跑测试确认失败**（`cd output/同花顺ETF资金/app && python3 -m pytest tests/test_parse.py -v`，Expected: FAIL 未定义）。

- [ ] **Step 4: 实现** `broad_base.json`（宽基种子池：50/180、沪深300、中证500、中证1000、中证A500、中证A50、创业板/创50、科创50/100、深证100、双创50、北证50 等及各跨市场份额代码），`universe.py` 从该 JSON 读入 `BROAD_BASE` 并实现 `is_broad`；`parse.py` 按 fixtures 字段实现三个解析函数（深市单位在 fixtures 核对后换算为份）。

- [ ] **Step 5: 跑测试确认通过**（Expected: PASS）。

- [ ] **Step 6: Commit** `research: ETF资金 份额/NAV解析与宽基名单`

---

### Task 2: 采数网络封装（份额合并 + NAV 批量 + 指数）

**Files:**
- Create: `output/同花顺ETF资金/app/fetch.py`
- Test: `output/同花顺ETF资金/app/tests/test_fetch_smoke.py`（live，标 `@pytest.mark.live`）

**Interfaces:**
- Consumes: `parse.parse_sse_shares/parse_szse_shares/parse_nav`
- Produces:
  - `fetch.fetch_shares(date: str) -> dict[str, float]`（沪+深合并，date='YYYY-MM-DD'）
  - `fetch.fetch_navs(codes: Iterable[str], date: str) -> dict[str, float]`（缺失的 code 不入表）
  - `fetch.fetch_sse_index(start: str, end: str) -> list[dict]`（`[{'date','close'}]`）

- [ ] **Step 1: 写 live 冒烟测试**：

```python
@pytest.mark.live
def test_fetch_shares_returns_many():
    out = fetch_shares("2026-11-12")
    assert len(out) > 500 and out["510300"] > 0
@pytest.mark.live
def test_fetch_navs_has_hs300():
    assert fetch_navs(["510300"], "2026-11-12")["510300"] > 0
@pytest.mark.live
def test_fetch_sse_index_has_close():
    s = fetch_sse_index("2026-11-10","2026-11-12"); assert s and "close" in s[-1]
```

- [ ] **Step 2: 实现** `fetch.py`：用 `requests` 调三类接口（沪份额带 `STAT_DATE` 与分页取全量 924+ 条；深份额当日接口；NAV 逐 code 调 lsjz，失败跳过；指数东财日 K 取 `date/close`），分别交给对应 `parse_*`。沪份额分页循环直到取尽。

- [ ] **Step 3: 跑 live 测试确认通过**（Run: `python3 -m pytest tests/test_fetch_smoke.py -v -m live`，Expected: PASS；网络不可用时跳过并说明）。

- [ ] **Step 4: Commit** `research: ETF资金 份额/NAV/指数采数封装`

---

### Task 3: 净流入计算 + 折算过滤 + 聚合（纯函数，核心）

**Files:**
- Create: `output/同花顺ETF资金/app/compute.py`
- Test: `output/同花顺ETF资金/app/tests/test_compute.py`

**Interfaces:**
- Consumes: `universe.is_broad`
- Produces:
  - `compute.compute_daily_flow(shares_t: dict[str,float], shares_prev: dict[str,float], nav: dict[str,float], split_threshold: float = 0.5) -> dict[str, float]`（code→flow_元，已过滤）
  - `compute.aggregate_flow(flows: dict[str,float]) -> tuple[float, float]`（(全A_元, 宽基_元)）
  - `compute.cumulative(values: list[float], n: int) -> float`

- [ ] **Step 1: 写失败测试** `tests/test_compute.py`（覆盖 Review Focus 四类）：

```python
def test_flow_basic_sign():
    # 份额增→正(流入)，减→负(流出)
    out = compute_daily_flow({"A":110.0}, {"A":100.0}, {"A":2.0})
    assert out["A"] == pytest.approx(20.0)
def test_flow_filters_split():                 # 份额×2 > 0.5 阈值 → 剔除
    assert "A" not in compute_daily_flow({"A":300.0}, {"A":100.0}, {"A":1.0})
def test_flow_skips_missing_nav():             # NAV 缺 → 跳过
    assert compute_daily_flow({"A":110.0}, {"A":100.0}, {}) == {}
def test_flow_skips_new_listing():             # 仅在 t → 跳过
    assert compute_daily_flow({"A":100.0}, {}, {"A":1.0}) == {}
def test_flow_skips_missing_today():           # 仅在前值 → 跳过
    assert compute_daily_flow({}, {"A":100.0}, {"A":1.0}) == {}
def test_aggregate_splits_broad():             # 宽基子集
    allv, broad = aggregate_flow({"510300":10.0, "512480":5.0})
    assert allv == 15.0 and broad == 10.0
def test_cumulative_last_n():
    assert cumulative([1.0,2.0,3.0,4.0], 2) == 7.0
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现** `compute.py`：`compute_daily_flow` 遍历 `shares_t∩shares_prev`，前值为 0 或缺 NAV 或 `abs(Δ)/prev > split_threshold` 则跳过，否则 `Δ×nav`；`aggregate_flow` 按 `is_broad` 分桶求和；`cumulative` 取末 n 项之和。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: Commit** `research: ETF资金 净流入计算与折算过滤`

---

### Task 4: SQLite 存储 + 历史回补

**Files:**
- Create: `output/同花顺ETF资金/app/store.py`
- Create: `output/同花顺ETF资金/app/backfill.py`
- Test: `output/同花顺ETF资金/app/tests/test_store.py`

**Interfaces:**
- Consumes: `fetch.*`, `compute.*`
- Produces:
  - `store.init_db(path: str) -> sqlite3.Connection`（建表 `daily_share(date,code,shares)`、`daily_agg(date,flow_all,flow_broad)`、`daily_index(date,close)`，主键去重）
  - `store.save_shares(conn, date, shares: dict) / save_agg(conn, date, flow_all, flow_broad) / save_index(conn, date, close)`
  - `store.read_shares(conn, date) -> dict[str,float]`
  - `store.latest_date_before(conn, date) -> str | None`
  - `store.read_agg_series(conn) -> list[dict]`（按日升序 `{'date','flow_all','flow_broad'}`）
  - `store.read_index_map(conn) -> dict[str,float]`
  - `backfill.backfill(conn, start: str, end: str) -> None`

- [ ] **Step 1: 写失败测试**（内存/临时库）：

```python
def test_save_read_shares_roundtrip(): ...        # 存后读回相等
def test_save_shares_idempotent():                # 同日重存不翻倍
    # 存两次同一天，read 仍为单份
def test_latest_date_before(): ...                # 返回严格早于给定日的最近有记录日
def test_read_agg_series_sorted(): ...            # 升序
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现** `store.py`（`INSERT OR REPLACE`，建索引）；`backfill.py`：沪用 `STAT_DATE` 逐交易日回补；深市历史用 `akshare.fund_scale_daily_szse`（一次性 `pip install akshare`，约 6 个月，best-effort），对每日 `compute_daily_flow`+`aggregate_flow`+指数一并落 `daily_agg/daily_index`。深市不可得的早期日期只落沪，`data.json` note 说明（Task 5）。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: Commit** `research: ETF资金 SQLite存储与历史回补`

---

### Task 5: data.json 导出（含免责 note）

**Files:**
- Create: `output/同花顺ETF资金/app/export.py`
- Test: `output/同花顺ETF资金/app/tests/test_export.py`

**Interfaces:**
- Consumes: `store.read_agg_series/read_index_map`, `compute.cumulative`
- Produces:
  - `export.build_data_json(conn) -> dict`
  - `export.write_data_json(conn, path: str) -> None`
- data.json 结构：
```json
{"updated":"ISO时间","note":"自建估算（份额差×NAV），非同花顺原口径；无盘中数据，T+1；深市历史约6个月。",
 "series":[{"date":"2026-11-12","flow_all":-24.8,"flow_broad":-10.2,"index":3634.35}],
 "kpi":{"all":{"yesterday":-248.01,"cum60":5936.70},"broad":{"yesterday":0,"cum60":0}}}
```
（flow 单位亿元 = 元/1e8；index 可缺为 null）

- [ ] **Step 1: 写失败测试**：

```python
def test_build_series_in_yi(): ...                # 元→亿元换算正确
def test_build_kpi_yesterday_and_cum60(): ...     # 昨日=末日, cum60=末60日和
def test_data_json_has_disclaimer():              # Review Focus #5
    assert "非同花顺原口径" in build_data_json(conn)["note"]
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现** `export.py`：读 `read_agg_series`，join 指数，换算亿元，算 KPI（昨日=末条，cum60=`cumulative(...,60)`，全A/宽基各一组），写入固定 note，`write_data_json` 落盘。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: Commit** `research: ETF资金 data.json导出`

---

### Task 6: 前端静态页 index.html

**Files:**
- Create: `output/同花顺ETF资金/app/index.html`
- Create: `output/同花顺ETF资金/app/data.json`（Task 7 跑一次后生成；此处先放一份小样例供本地验证）

**Interfaces:**
- Consumes: 运行时 `fetch('data.json')`（Task 5 结构）

- [ ] **Step 1: 实现** `index.html`：沿用 `output/同花顺ETF波段顶底/research/*/page_template.html` 的 CSS 设计令牌与明暗主题、Noto Sans SC；ECharts 5.4.3（cdnjs）；两个 tab「全A / 宽基」切换 `series` 数据源；主图 = 净流入柱（`flow_all/flow_broad`，红正绿负，`itemStyle` 按值着色）+ 上证指数折线（双 Y 轴）+ `dataZoom` 时间轴；顶部两张 KPI 卡（昨日净流入、近60日累计，取 `kpi`）；页面顶部固定展示 `note` 免责与「长按截图上方盘中曲线不可得」说明。
- [ ] **Step 2: 本地验证**（Run: `cd output/同花顺ETF资金/app && python3 -m http.server 8000`，浏览器开 `http://localhost:8000/`）—— 用 claude-in-chrome 打开并截图：确认两 tab 切换、红绿柱 + 指数线 + 拖动、KPI 数值、note 可见；Expected: 图渲染无报错（查 console）。
- [ ] **Step 3: Commit** `research: ETF资金 前端趋势页`

---

### Task 7: 日度编排 pipeline + cron + 部署

**Files:**
- Create: `output/同花顺ETF资金/app/pipeline.py`
- Create: `output/同花顺ETF资金/app/README.md`（部署说明）

**Interfaces:**
- Consumes: `fetch.*`, `compute.*`, `store.*`, `export.*`
- Produces: `pipeline.run_daily(conn, date: str) -> None`

- [ ] **Step 1: 写失败测试** `tests/test_pipeline.py`（用 monkeypatch 把 `fetch.*` 换成假数据，端到端）：

```python
def test_run_daily_updates_agg_and_json(tmp_path, monkeypatch):
    # 预置前一交易日份额入库 → run_daily → daily_agg 多一行、data.json 存在且 series 非空
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现** `pipeline.py`：`run_daily` = 取 `latest_date_before` 作前值 → `fetch_shares(date)` → `fetch_navs(该日 code 集, date)` → `compute_daily_flow`+`aggregate_flow` → `save_shares/save_agg` + 取指数 `save_index` → `export.write_data_json`；带 `logging` 与对网络调用的简单重试（如 3 次）。`__main__` 支持 `python3 pipeline.py [YYYY-MM-DD]`（默认今天）。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: 端到端实跑一次**（Run: `python3 pipeline.py 2026-11-12`，Expected: `data.json` 的 `updated` 刷新、`series` 增长、无异常）。
- [ ] **Step 6: 写 README.md**：crontab 示例（每日 22:30 跑 `pipeline.py`）、nginx 静态托管 `app/` 目录、`akshare` 一次性回补说明、口径与局限。
- [ ] **Step 7: 抽查验收**（Review Focus/验收）：取近期某日对同花顺快讯「昨日全A合计」比量级，记录误差到 README（一次性，非持续校准）。
- [ ] **Step 8: Commit** `research: ETF资金 日度编排与部署说明`

---

## 自检记录

- **Spec 覆盖**：盘中曲线/榜单/分类=非目标（不建任务，符合）；历史柱(Task3/5/6)、全A+宽基(Task1/3)、KPI(Task5/6)、NAV口径(Task1/2)、折算防污染(Task3)、每日更新(Task7)、静态部署(Task6/7)、免责标注(Task5/6)均有归属。
- **类型一致**：`fetch_shares/fetch_navs/fetch_sse_index`、`compute_daily_flow/aggregate_flow/cumulative`、`store.*`、`build_data_json/write_data_json`、`run_daily` 跨任务签名一致，flow 一律元（导出层换亿元）。
- **Review Focus**：折算/缺NAV/新上市/停牌 四类均在 Task 3 测；深市历史缺口在 Task 5 测 note。
- **比例**：代码块仅签名/测试断言，无完整函数体，计划未替代实现。
