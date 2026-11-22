"""重点宽基观察池（不是“国家队持仓清单”：成员是主流宽基 ETF，是否被汇金等持有以原始报告为准）。

expect 为人工核对的简称关键字；运行时用交易所份额数据中的官方简称核验，不符写入告警。
"""
POOL = [
    {"code": "510050", "manager": "华夏", "name": "华夏上证50ETF", "index": "上证50", "expect": "50"},
    {"code": "510300", "manager": "华泰柏瑞", "name": "华泰柏瑞沪深300ETF", "index": "沪深300", "expect": "300"},
    {"code": "510310", "manager": "易方达", "name": "易方达沪深300ETF", "index": "沪深300", "expect": "300"},
    {"code": "510330", "manager": "华夏", "name": "华夏沪深300ETF", "index": "沪深300", "expect": "300"},
    {"code": "159919", "manager": "嘉实", "name": "嘉实沪深300ETF", "index": "沪深300", "expect": "300"},
    {"code": "159915", "manager": "易方达", "name": "易方达创业板ETF", "index": "创业板指", "expect": "创业板"},
    {"code": "588000", "manager": "华夏", "name": "华夏科创50ETF", "index": "科创50", "expect": "科创"},
    {"code": "588080", "manager": "易方达", "name": "易方达科创50ETF", "index": "科创50", "expect": "科创"},
    {"code": "510500", "manager": "南方", "name": "南方中证500ETF", "index": "中证500", "expect": "500"},
    {"code": "512100", "manager": "南方", "name": "南方中证1000ETF", "index": "中证1000", "expect": "1000"},
    {"code": "159845", "manager": "华夏", "name": "华夏中证1000ETF", "index": "中证1000", "expect": "1000"},
    {"code": "560010", "manager": "广发", "name": "广发中证1000ETF", "index": "中证1000", "expect": "1000"},
]
POOL_NAME = "重点宽基观察池"
CODES = [p["code"] for p in POOL]


def market(code: str) -> str:
    """5xxxxx 上交所；1xxxxx 深交所。"""
    return "sh" if code[0] in "56" else "sz"
