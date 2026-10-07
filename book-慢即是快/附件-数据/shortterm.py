import csv, statistics as st, math
def load(c): return [(a,float(b)) for a,b in list(csv.reader(open(c+".csv")))[1:]]
for code,name in (("sh000300","沪深300"),("sz399006","创业板指")):
    r=load(code); r=[x for x in r if x[0]>="2013-01-01"]
    ret=[r[i][1]/r[i-1][1]-1 for i in range(1,len(r))]
    up=sum(x>0 for x in ret)/len(ret)
    mu=st.mean(ret); sd=st.pstdev(ret)
    big=sum(abs(x)>0.03 for x in ret)/len(ret)
    print(name,"交易日",len(ret),"上涨日占比%.1f%%"%(100*up),"日均收益%.3f%%"%(100*mu),"日波动%.2f%%"%(100*sd),"|日涨跌|>3%%的天数占比%.1f%% (%d天)"%(100*big,sum(abs(x)>0.03 for x in ret)))
    # 完美择日：每天只做对的方向（不可得）仅示意略
    # 每日全进全出的成本拖累
for c in (0.0003,0.0005,0.001):
    print("单边成本%.2f%%: 每日全进全出一年(243日)成本拖累 %.1f%%"%(100*c,100*(1-(1-2*c)**243)))
# 连续亏损：50%胜率下 连续5次亏损概率
print("胜率50%%时，100次交易中至少出现一次连续6连亏的概率约 %.0f%%"%(100*(1-(1-0.5**6)**95)))
