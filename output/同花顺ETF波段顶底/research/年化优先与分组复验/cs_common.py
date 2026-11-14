"""在 Codex 冻结引擎（../数据训练优化ETF/engine.py）上只读扩展：卖出信号当天尾盘卖。
T+1：买入当天出卖出信号 → 照原规则次日开盘卖。其余口径全部沿用。"""
import sys, inspect
from pathlib import Path
R = Path(__file__).resolve().parent.parent / "数据训练优化ETF"
sys.path.insert(0, str(R))
import engine
from engine import P, load_panel, summarize
from grid import enumerate_grid, identifier, MACDS

src = inspect.getsource(engine.simulate).replace(
    "def simulate(data,config,window,cost=20,retain=False,liquidate_end=True):",
    "def simulate_cs(data,config,window,cost=20,retain=False,liquidate_end=True,close_sell=True):")
hook = """        sold_at_close=False
        if close_sell and q and i!=end and active["entry_index"]!=i:
            cur=v[i]
            if hi is not None and cur is not None and cur>=hi: seen_high=True
            top=seen_high and cur is not None and cur<hi if hi is not None else False
            if (exit_rule=="X1" and below[i] or exit_rule=="X2" and dead[i]
                or exit_rule=="X3" and dead[i] and (below[i] or top)
                or exit_rule=="X4" and (below[i] or dead[i])):
                close_trade(i,cl[i],i,False);armed=None;seen_high=False;sold_at_close=True
        value=cash+reserve+q*cl[i]
"""
assert src.count("        value=cash+reserve+q*cl[i]\n") == 1
src = src.replace("        value=cash+reserve+q*cl[i]\n", hook, 1).replace(
    "        if i==end:\n            continue\n", "        if i==end or sold_at_close:\n            continue\n", 1)
_ns = dict(vars(engine)); exec(src, _ns); simulate_cs = _ns["simulate_cs"]

grid = dict(enumerate_grid())
blank = {"ma":10,"n":None,"lo":None,"macd":None,"hi":None,"cap":None,"wait":None}
for m in MACDS:
    for x in ("X2", "X4"):
        c = {**blank, "entry":"MACD", "exit":x, "macd":list(m)}; grid[identifier(c)] = c
assert len(grid) == 312
HOLD = {**blank, "entry":"HOLD", "exit":"HOLD"}
MACD_KEY = identifier({**blank, "entry":"MACD", "exit":"X2", "macd":[12,26,9]})

PANEL = None
def init():
    global PANEL; PANEL = load_panel()
def run(job):
    """job=(key, config, close_sell, window名或(起,止)) → (key, close_sell, 窗口, {code: metric})"""
    key, c, cs, win = job
    w = P["windows"][win] if isinstance(win, str) else win
    per = {}
    for code, d in PANEL.items():
        r = (simulate_cs if cs else engine.simulate)(d, c, w, 20)
        if r: per[code] = r["metric"]
    return key, cs, win if isinstance(win, str) else "|".join(win), per

if __name__ == "__main__":
    # 自检：不开尾盘卖时复现 Codex test_summary 的纯 MACD / 买入持有
    import csv
    init()
    ref = {(r["config"], r["group"]): r for r in csv.DictReader(open(R / "results/test_summary.csv")) if r["cost"] == "20" and r["phase"] == "test"}
    for name, c in (("MACD", grid[MACD_KEY]), ("HOLD", HOLD)):
        s = summarize(list(run((name, c, False, "test"))[3].values()))
        assert abs(s["cagr_med"] - float(ref[(name, "full")]["cagr_med"])) < 1e-12, name
    print("自检通过：复现 Codex 纯MACD/买入持有测试期年化中位")
