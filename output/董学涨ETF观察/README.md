# 董学涨ETF观察

复刻抖音视频（ID 7710651018401713307，董学涨）里的观察方式，并补上视频没有的“汇金原始披露”核验：

1. **成交排名**：重点宽基观察池 12 只 ETF 按最近交易日成交额排序，附 20 日放量比、1/5/20 日份额变化、净申赎近似、样本内份额分位。
2. **单只走势**：任选 ETF 和日期区间，场内份额（橙色面积）、规模（蓝线）、成交额三张**联动图**（同一 x 轴，不用双 y 轴），逐日明细表，CSV 下载（原始单位 份/元）。
3. **汇金披露**：自动从交易所公告列表发现年报/中报，下载原文 PDF，用确定性规则抽取“期末上市基金前十名持有人”，识别汇金投资 / 汇金资管 / 汇金资管委托产品，给出 PDF 页码、原披露比例和比例口径；核验 2026 年新准则下的中报格式。

> 观察池名称是“重点宽基观察池”，不是“国家队持仓清单”。所有数据为盘后数据，不是实时行情。

## 日常使用：从资金观测台进入（推荐）

```bash
cd output/同花顺ETF资金/app && .venv/bin/python dashboard_server.py   # http://127.0.0.1:8766/
```

侧栏“份额与规模”“汇金披露”打开本模块（`/holdings/`），页面顶部显示本模块的更新状态，有“立即更新”按钮。服务运行期间会自动检查新数据：份额/行情在北京时间 18:00 检查阈值后做增量，定期报告每天检查一次。不需要另开 8793 服务，也不需要手工运行命令。规则见 `../同花顺ETF资金/app/README.md` 中的“接入模块”一节。

## 手动运行 / 开发

```bash
cd output/董学涨ETF观察
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # 首次
.venv/bin/python run.py update            # 一键采集：份额/净值/行情/定期报告 → web/data/*.json
.venv/bin/python run.py update --no-reports   # 只更新行情类（快）
.venv/bin/python run.py reports           # 只更新定期报告与汇金披露
.venv/bin/python run.py serve --port 8793 # 独立开发预览 http://127.0.0.1:8793/（无后台更新）
.venv/bin/python -m pytest -q && node --test tests/js/core.test.js
```

`run.py update/reports` 的退出码：0 完整成功；2 异常（旧产物保留）；3 另一个任务持有文件锁；4 完成但有阶段失败/报告问题；5 完成但未到应有日期。结果写入 `data/last_run.json`。

首次全量（2024-01-02 起）约 30~40 分钟（上交所份额只能逐日查询，约 700 次请求）；之后增量只取新日期，约 1~2 分钟。

## 数据来源（全部免费、匿名、无需登录）

| 数据 | 来源 | 口径 |
|---|---|---|
| 上交所 ETF 场内份额 | query.sse.com.cn `COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L` | 按 STAT_DATE 单日查询，TOT_VOL 万份×10000=份，行内日期须等于请求日 |
| 深交所 ETF 场内份额 | szse.cn ShowReport `scsj_fund_jjgm` XLSX | 按季度区间（区间过长会返回空），表头“基金规模(份)” |
| 单位净值、分红/折算 | 东方财富 `api.fund.eastmoney.com/f10/lsjz` | 每页最多 20 行，按实际页大小翻页；只取精确日期 |
| 收盘价、成交额 | BaoStock 日线（adjustflag=3 不复权） | 成交额≠净流入 |
| 交易日历 | BaoStock `query_trade_dates` | 判断前一交易日/缺日 |
| 定期报告 | 上交所 `COMMON_SSE_PL_JJXX_ETFGG_L`；深交所 `api/disc/announcement/annList` | 年报/中报原文 PDF |

采集解析规则部分改写自 `output/同花顺ETF资金/app/auto_daily.py`（份额单位/行内日期核验/净值分页），已复制到 `dxz/` 内，本目录独立运行，不依赖也不修改那个目录。

## 口径要点

- 规模主口径 = 份额 × 同日单位净值；“份额 × 收盘价”单列为估算口径。交易所接口只给份额，没有拿到官方“规模（元）”原值。
- 净申赎近似 =（份额ₜ − 前一交易日份额）× 当日净值；前一交易日缺份额则不算；份额折算日不算。
- 不同 ETF 每份净值不同，不做跨 ETF 份额合计。
- 缺数据就是缺：不插值、不补 0；失败沿用缓存并在页面顶部标“陈旧/阶段失败”。
- 汇金：狭义汇金体系（汇金投资+汇金资管自有）与委托产品分列；社保/养老金/证金等广义口径单列，不与汇金合计；匿名、未进前十、未列示都是“未知”。
- 当日 ETF 净申购 ≠ 汇金买入；本工具不提供“假设旧持仓不变推算的今日比例”。

## 目录

```
run.py             一键入口（update / reports / serve）
dxz/common.py      HTTP 重试、原子写、数值规范化
dxz/pool.py        观察池
dxz/shares.py      交易所份额
dxz/nav.py         净值
dxz/quotes.py      BaoStock 行情与交易日历
dxz/series.py      逐日对齐与派生指标（纯函数）
dxz/reports.py     定期报告发现/下载/提取（纯规则）
dxz/build.py       编排、校验、写 web/data
web/               静态页面（index.html / app.js / core.js / style.css）与 data/*.json
data/cache/        已核验的中间缓存（可删除重建）
data/raw/reports/  原始 PDF
tests/             pytest 与 node 测试
```

## 合成观察（视频19只ETF观察池，#composite）

- 页面：`/holdings/#composite`；产物 `web/data/composite.json`；代码 `dxz/pool19.py`、`dxz/composite.py`、`web/composite.js`。
- 公式：观察指数 I(t)=100×Σ19 Q_i(t)/Σ19 Q_i(2025-11-20)；当日份额变化 = Σ19 Q(t) − Σ19 Q(前一交易日)（亿份）。任一成员缺失 → 当日为空（不补 0、不缩池）；份额折算日（510310 2024-09-20）变化置空，折算前水平灰底标注不可比；基期不完整或 ≤0 → “不可计算”。
- 口径：近似观察版，不是作者完整算法、不是全市场、不是任何机构持仓；份额直接相加不代表人民币资金流；不设阈值、无买卖提示。
- 更新：`run.py update` 写完 etf.json 后自动更新（失败只记 `status.json.stages.composite`，不影响 12 只池，旧 composite.json 保留）；单独运行 `.venv/bin/python run.py composite`。
- 历史范围：从 2022-08-01 取数（`pool19.HIST_START`）。19 只中 159629（2022-07-27 成立）、560010（2022-07-28 成立）最晚，上市前交易所无份额，
  因此首个 19 只完整日在 2022-08 上旬；此前各日不计算合计（不补 0、不缩池），页面显示首个完整日与缺失原因。更早无法回溯。
  19 池日历独立保存在 `data/cache19/calendar.json`，主模块 `run.py update` 传入的 2024 起日历只用于最新段，不会把历史裁回 2024。
  2024 以前段由 `tools/backfill19.py` 一次性回补，官方原始响应 gzip 存 `data/seed19/raw_pre2024/`（manifest 记 URL、参数、抓取时间、sha256）。
- 数据：首次运行用 `data/seed19/composite_seed.json`（由 `tools/build_seed19.py` 从研究目录已核验原始数据生成，含来源与 sha256）初始化 `data/cache19/`，之后复用上交所/深交所/净值采集器增量抓取，BaoStock 取沪深300、上证指数；510300 收盘价读主模块行情缓存。运行不依赖研究目录。
