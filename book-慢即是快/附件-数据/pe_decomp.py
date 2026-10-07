# 价格 = 每股收益 × 市盈率 的拆解（2022年末 → 2025年末，未复权收盘价；每股收益取公开财务指标的基本每股收益）
import csv
EPS={"美的集团":("sz000333",4.34,5.80),"招商银行":("sh600036",5.26,5.70),"贵州茅台":("sh600519",49.93,65.66)}
def px(code,prefix):
    f={"sz000333":"sz000333_raw.csv","sh600036":"sh600036_raw.csv","sh600519":"sh600519_raw.csv"}[code]
    D=dict((a,float(b)) for a,b in list(csv.reader(open(f)))[1:])
    last=lambda y:D[max(d for d in D if d.startswith(str(y)))]
    return last(2022),last(2025)
print("| 股票 | 2022年末价 | 2025年末价 | 价格 | 每股收益 | 市盈率 |")
for n,(c,e0,e1) in EPS.items():
    p0,p1=px(c,"")
    print("| %s | %.2f | %.2f | %+.1f%% | %.2f→%.2f (%+.1f%%) | %.1f→%.1f |"%(n,p0,p1,100*(p1/p0-1),e0,e1,100*(e1/e0-1),p0/e0,p1/e1))
