"""Canonical finite grid: parameters occur only when used by entry/exit logic."""
from itertools import product
import hashlib
import json

MACDS = ((8,17,9), (12,26,9), (16,35,9))
PERIODS = (9,13,21)
LOWS = (20,30,40)
HIGHS = (70,80)


def identifier(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",", ":")).encode()).hexdigest()[:12]


def enumerate_grid():
    configs = {}
    for entry, exit_ in product(("E1", "E2", "E3"), ("X1", "X2", "X3", "X4")):
        ns = PERIODS if entry != "E3" or exit_ == "X3" else (None,)
        # E3 without cap has no band period unless X3 uses a high threshold.
        cap_cases = (None,60) if entry == "E3" else (None,)
        for cap in cap_cases:
            use_ns = PERIODS if entry != "E3" or exit_ == "X3" or cap else (None,)
            for n,lo,macd,hi in product(use_ns, LOWS if entry != "E3" else (None,),
                                      MACDS if entry == "E3" or exit_ != "X1" else (None,),
                                      HIGHS if exit_ == "X3" else (None,)):
                c = {"entry":entry,"exit":exit_,"ma":10,"n":n,"lo":lo,"macd":list(macd) if macd else None,
                     "hi":hi,"cap":cap,"wait":5 if entry == "E2" else None}
                configs[identifier(c)] = c
    assert len(configs) == 306, len(configs)
    return dict(sorted(configs.items()))


def controls():
    blank = {"ma":10,"n":None,"lo":None,"macd":None,"hi":None,"cap":None,"wait":None}
    return {"HOLD":{**blank,"entry":"HOLD","exit":"HOLD"},
            "MA10":{**blank,"entry":"MA","exit":"X1"},
            "MACD":{**blank,"entry":"MACD","exit":"X2","macd":[12,26,9]},
            "USER":{**blank,"entry":"E1","exit":"X3","n":13,"lo":30,"hi":70,"macd":[12,26,9]}}


def neighbors(config, grid):
    numeric = {"n":PERIODS,"lo":LOWS,"hi":HIGHS,"macd":[list(m) for m in MACDS]}
    output = []
    for name, choices in numeric.items():
        value = config[name]
        if value is None:
            continue
        index = choices.index(value)
        for j in (index-1,index+1):
            if 0 <= j < len(choices):
                changed = {**config,name:choices[j]}
                key = identifier(changed)
                if key in grid:
                    output.append(key)
    return output


if __name__ == "__main__":
    print(json.dumps({"canonical_configurations":len(enumerate_grid())}))
