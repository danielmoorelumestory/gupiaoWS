import importlib.util, sys
sys.argv = ["x"]
sp = importlib.util.spec_from_file_location("Z", "B组双熊破线卖对照.py"); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
C, W = Z.C, Z.W
C.init()
for code in ("515980", "159819"):
    d = W.data_of(code)
    d["reg"]["BOTH"] = [not (h is False and r is False) for h, r in zip(d["reg"]["H1"], d["reg"]["R2-20"])]
    gold, dead = d["macds"][(12, 26, 9)]
    runs = {"现行": C.K.simulate_kd(d, {**C.T.BASE, "N": "H1"}, C.FULL, 20, retain=True),
            "双熊破线卖": Z.simx(d, {**Z.BASE, "anyx": True, "XN": "BOTH"}, C.FULL, 20, retain=True)}
    print(f"\n######## {code}")
    for k, r in runs.items():
        nav = [(x["date"], x["nav"]) for x in r["nav"]]
        pk = nav[0]; best = (0, None, None)
        for t, v in nav:
            if v > pk[1]: pk = (t, v)
            if v / pk[1] - 1 < best[0]: best = (v / pk[1] - 1, pk[0], t)
        print(f"## {k} 最大回撤 {best[0]*100:.1f}%  {best[1]} → {best[2]}")
        a, b = best[1], best[2]
        for t in r["trades"]:
            ed, xd = d["dates"][t["entry_index"]], d["dates"][t["exit_index"]]
            if xd < a or ed > b: continue
            xs = t["exit_signal_index"]
            why = "死叉" if dead[xs] else "双熊破线"
            print(f"   买 {ed}  卖 {xd}（{why}{'·期末未卖' if t.get('forced_end') else ''}）  本笔 {t['net_return']*100:+.1f}%")
