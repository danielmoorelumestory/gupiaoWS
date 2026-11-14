# ETF 资金净流入趋势页

部署在服务器、每天收盘后自动更新的静态网页，展示 **全A / 宽基** 两个口径的 ETF 日度净流入（红绿柱）+ 上证指数叠加，用于看资金进出的大周期趋势。

数据为**自建估算**（份额差 × NAV），**非同花顺原口径**，T+1 日频；顶部盘中预估曲线、单只资金榜不在范围（匿名不可得）。

## 口径

```
日净流入 flow = (份额_t − 份额_前一交易日) × NAV_t   （元；展示换算亿元）
全A = 所有在列 ETF 的 flow 之和
宽基 = broad_base.json 白名单子集之和
```

- 份额：上交所 `commonQuery.do`（万份×10000）、深交所 `ShowReport CATALOGID=1105`（当前规模万份×10000）。
- NAV：东财 `f10/lsjz` 的 `DWJZ`（单位净值）。
- 折算/拆分：单日份额变动 `|Δ|/前值 > 0.5` 视为疑似折算，当日该只剔除，不计入合计。
- 跳过：新上市（无前值）、停牌（当日缺份额）、前值为 0、缺 NAV。

## 结构

```
app/
  parse.py      接口响应解析（纯函数）
  fetch.py      采数：沪/深份额、NAV、上证指数
  compute.py    净流入计算、折算过滤、全A/宽基聚合
  store.py      SQLite 存储（daily_share/daily_agg/daily_index）
  export.py     导出前端 data.json（元→亿元、KPI、免责 note）
  backfill.py   历史回补（沪 STAT_DATE 逐日；深需 akshare）
  pipeline.py   日度编排（采→算→落库→导出）
  universe.py   宽基白名单加载
  broad_base.json  宽基 ETF 白名单（近似，人工维护，新发需补）
  index.html    前端页（ECharts，fetch data.json）
  etf_flow.db   SQLite（git 忽略）
  data.json     前端数据（pipeline 生成）
```

## 安装

```bash
cd app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # requests + pytest
```

## 每日更新（cron）

净值当晚约 19:00–21:00 到齐（QDII/港股更晚），因此收盘后要等数据到齐，建议 **22:30** 跑：

```cron
30 22 * * 1-5  cd /path/to/app && .venv/bin/python pipeline.py >> pipeline.log 2>&1
```

`pipeline.py [YYYY-MM-DD]`（默认今天）：取当日份额 → 结合库中前一交易日算净流入 → 落库 → 重写 `data.json`。对网络调用有 3 次重试。

**前向日更正确性**：深交所接口只返回「最新份额」，每天收盘后跑即当天份额，正确；库中前一交易日是昨天跑时存的，故前向日更不受影响。

## 托管

nginx 静态托管 `app/` 目录（页面只读 `data.json`，不直连任何接口）：

```nginx
location /etf-flow/ {
    alias /path/to/app/;
    index index.html;
}
```

## 历史回补

- 沪市：`backfill.py` 用 `STAT_DATE` 逐交易日回补，可取任意历史日。
- 深市：当日接口只给最新，历史需 `pip install akshare` 后用 `fund_scale_daily_szse`（约 6 个月，best-effort）。**单次历史回补中深市会低估**（早期无历史份额），`data.json` 的 note 已声明「深市历史约 6 个月」。建议直接让前向日更向前累积，深市数据从上线日起完整。

## 局限

- 与同花顺 App 数字**不逐位对齐**；单日样本误差约 0.8–1.8%，累计有漂移。如需收紧，可加每日对同花顺 7×24 快讯「昨日全市场合计」的校准（本期未做）。
- 分类只做全A + 宽基；宽基白名单为近似人工维护。
- 无盘中、无单只榜单。

## 抽查记录（2026-11-14）

端到端实跑 `pipeline.py`（2026-11-12 建底 → 2026-11-13 算净流入），exit 0：

- 2026-11-13：全A = **−170.58 亿**、宽基 = **−102.25 亿**、上证指数 3634.35；`data.json` 正常生成（无 sample 标记）。
- NAV 全量采集约 11 分钟（~900+ 只逐只请求），夜间 cron 可接受。

**量级核对**：数值落在同花顺「昨日 ETF 申购净流入」历史常见区间（数十～数百亿，参见截图 74.JPG 昨日 −248.01 亿），方向与量级合理。

**未逐位校准，原因**：此为单次历史回补，深交所接口两天都返回「最新份额」，深市 Δ≈0 被抵消，故该全A 实为**沪市主导、低估深市**；要做匹配日的逐位校准，需前向日更积累真实两日深市份额后，再对当日同花顺快讯核对。本期按设计不做持续校准。
