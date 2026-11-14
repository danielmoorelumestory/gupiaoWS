"""牛/熊分段规则的模拟器（重建自前几轮的脚本）：行情定义 + 牛/熊各自的进出规则，卖出一律尾盘卖（T+1 时次日开盘）。"""
import inspect
from collections import defaultdict
from datetime import date
import cs_common as C
engine = C.engine
src = inspect.getsource(engine.simulate).replace("def simulate(data,config,window,cost=20,retain=False,liquidate_end=True):",
      "def simulate_rg(data,config,window,cost=20,retain=False,liquidate_end=True):")
helper = """    reg=data["reg"][config["N"]]
    ma20b=data["below20"]
    def exit_sig(i):
        if reg[i]:
            return config["bullx"]=="D20" and dead[i] and ma20b[i] or config["bullx"]=="X2" and dead[i]
        bx=config["bearx"]
        return bx=="ALL" or (bx=="X2" and dead[i]) or (bx=="X4" and (dead[i] or below[i]))
    def entry_sig(i):
        if reg[i]:
            return config["bullin"]=="ANY" or gold[i]
        bi=config["bearin"]
        return bi=="GOLD" and gold[i] or bi=="E3" and gold[i] and above[i]
"""
src = src.replace("    def close_trade(", helper + "    def close_trade(", 1)
src = src.replace("        value=cash+reserve+q*cl[i]\n", """        sold_at_close=False
        if q and i!=end and active["entry_index"]!=i and exit_sig(i):
            close_trade(i,cl[i],i,False);sold_at_close=True
        value=cash+reserve+q*cl[i]
""", 1).replace("        if i==end:\n            continue\n", "        if i==end or sold_at_close:\n            continue\n", 1)
a = src.index("        action=None\n"); b = src.index("        if action:\n")
src = src[:a] + """        action=None
        if q:
            if exit_sig(i): action="sell"
        elif entry_sig(i):
            action="buy"
""" + src[b:]
_ns = dict(vars(engine)); exec(src, _ns); simulate_rg = _ns["simulate_rg"]

def _ma_flag(c, n, above=True):
    out = [False]*len(c); s = 0.0
    for i, x in enumerate(c):
        s += x
        if i >= n: s -= c[i-n]
        if i >= n-1: out[i] = (x > s/n) if above else (x < s/n)
    return out

def add_reg(panel, breadth_from=None):
    """breadth_from：用另一个面板（原主池）计算宽度，只套用到 panel 上。"""
    br = {n: defaultdict(lambda: [0, 0]) for n in (20,)}
    for d in panel.values():
        c = [float(r["adjusted_close"]) for r in d["rows"]]; n_ = len(c)
        d["below20"] = _ma_flag(c, 20, False)
        reg = {"N250": _ma_flag(c, 250)}
        # 周 DIF>0，进行中周（当天收盘暂作周收盘）
        wk = [date.fromisoformat(x).isocalendar()[:2] for x in d["dates"]]
        e12 = e26 = None; wz = [False]*n_
        for i in range(n_):
            if i and wk[i] != wk[i-1]:
                x = c[i-1]
                if e12 is None: e12 = e26 = x
                else: e12 = 2/13*x + 11/13*e12; e26 = 2/27*x + 25/27*e26
            x = c[i]
            if e12 is not None: wz[i] = (2/13*x + 11/13*e12) - (2/27*x + 25/27*e26) > 0
        reg["WZ-live"] = wz
        d["reg"] = reg
        a20 = _ma_flag(c, 20)
        for i in range(19, n_):
            cell = br[20][d["dates"][i]]; cell[0] += a20[i]; cell[1] += 1
    if breadth_from is not None:
        br = {20: defaultdict(lambda: [0, 0])}
        for d in breadth_from.values():
            c = [float(r["adjusted_close"]) for r in d["rows"]]; a20 = _ma_flag(c, 20)
            for i in range(19, len(c)):
                cell = br[20][d["dates"][i]]; cell[0] += a20[i]; cell[1] += 1
    for d in panel.values():
        d["reg"]["B20-60"] = [br[20][t][1] < 10 or br[20][t][0]/br[20][t][1] >= 0.6 for t in d["dates"]]
    return panel
