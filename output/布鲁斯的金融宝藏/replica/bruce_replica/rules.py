"""决策规则里他明说过的部分。

1. 资金面与技术面的优先级（第26集 02:10–03:23）：资金面是大势、技术面是小势；
   两者相反就等待，等技术面转到与资金面同向再顺资金面做。只会技术分析的人，
   用大周期代替资金面、小周期代替技术面，规则相同。
2. 阿姆士加红盘率的读法：他没有给出完整阈值，只给了若干带日期的案例和
   「低于 0.7 / 0.6 / 0.5 才算多头主动进攻」这组参考档（第21集 01:24）。
   这里不替他补阈值，而是把当天读数与他讲过的案例做比对，告诉你最像哪一个。
3. 使用边界（第22集 01:38–02:04、04:24）：阿姆士和宽广度只用于短线转折，
   只在趋势中后段看。「中后段」他没有给出可计算的定义，需人工判断后传入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LONG, SHORT, NEUTRAL = "多", "空", "中"


def combine(capital: str, technical: str) -> str:
    """资金面（或大周期）与技术面（或小周期）合成记录表里的「结论」。"""
    for v in (capital, technical):
        if v not in (LONG, SHORT, NEUTRAL):
            raise ValueError(f"方向只能是 多/空/中，收到 {v!r}")
    if capital == NEUTRAL:
        return "观望（资金面无方向）"
    if capital == technical:
        return f"{capital}（资金面与技术面同向，可顺资金面执行）"
    return f"准备{capital}（等待技术面转{capital}）"


@dataclass(frozen=True)
class Case:
    date: str
    up_ratio: float
    trin: float
    reading: str
    source: str


# 他在视频里讲过的读数案例，数值取自画面表格或口述。用回补的个股日线核对过：
# 红盘率基本一致；阿姆士按成交额口径多数一致，9/21、10/23、10/28 偏差较大（见 README）。
CASES: tuple[Case, ...] = (
    Case("2026-09-21", 0.809, 1.69, "量价背离：红盘多但成交集中在下跌股，他解读为权重放量出货、上行接近末端", "第16集 03:05；第22集 02:04"),
    Case("2026-09-22", 0.437, 0.82, "宽广度崩塌：指数仍红但红盘率骤降，他说转折信号来自宽广度和 MCL，不是阿姆士", "第22集 03:00"),
    Case("2026-09-23", 0.335, 0.62, "下行初段的偏低读数：他特意说这里不能按数值大小当成转折点", "第22集 03:17"),
    Case("2026-03-23", 0.05, 0.31, "冰点：极少数上涨股放量，他解读为大资金买权重，称可以满仓", "第21集 01:53"),
    Case("2026-07-21", 0.55, 0.30, "底部特征：上涨股成交爆量，他解读为大资金扫货", "第20集 04:42"),
    Case("2026-10-23", 0.80, 0.90, "量能中性：空头回补，不是多头主动进攻", "第21集 00:54；第20集 03:45"),
    Case("2026-10-27", 0.11, 0.46, "小护盘：红盘股放量，他预期次日小反弹", "第22集 00:13"),
    Case("2026-10-28", 0.74, 0.77, "偏中性的反弹：红盘股没有爆量，不是中线反转", "第22集 05:13"),
    Case("2026-11-05", 0.88, 2.0, "缩量普涨、权重滞涨：宽广度与指数背离，他说是反弹不是反转（阿姆士口述为「2点多」，成交额口径）", "研判第17集"),
    Case("2026-11-09", 0.45, 0.50, "权重护盘、市场普弱：弱反弹。他同时用了「额价差大于15PP」和缩量两个条件，额价差公式未给出", "第27集 00:20"),
)

# 比对用的距离尺度为研究者自选：红盘率差 10 个百分点，约等于阿姆士差 20%。
_BREADTH_SCALE, _TRIN_SCALE, _NEAR = 0.10, 0.20, 1.5


def _distance(up_ratio: float, trin: float, case: Case) -> float:
    return math.hypot((up_ratio - case.up_ratio) / _BREADTH_SCALE,
                      (math.log(trin) - math.log(case.trin)) / _TRIN_SCALE)


def trin_tier(trin: float) -> str:
    """他给的参考档（第21集 01:24）：低于 0.7、0.6、0.5 意味着上涨股放量。"""
    if trin < 0.5:
        return "低于0.5：上涨股明显放量"
    if trin < 0.6:
        return "低于0.6：上涨股放量"
    if trin < 0.7:
        return "低于0.7：上涨股开始放量"
    if trin <= 1.0:
        return "0.7至1：量能中性偏多"
    return "高于1：成交偏向下跌股"


def read_short_term(up_ratio: float, trin: float, stage: str = "未知") -> dict:
    """把当天的红盘率和阿姆士翻译成他的说法。

    stage：趋势所处阶段，取 "初段" / "中后段" / "未知"，由使用者人工判断。
    """
    if not (trin and trin > 0) or math.isnan(trin) or math.isnan(up_ratio):
        return {"tier": None, "nearest": None, "similar": False, "note": "读数无效"}
    ranked = sorted(CASES, key=lambda c: _distance(up_ratio, trin, c))
    best = ranked[0]
    dist = _distance(up_ratio, trin, best)
    if stage == "中后段":
        note = "处于趋势中后段：按他的规则，可以关注阿姆士是否突然变小来找短线转折。"
    elif stage == "初段":
        note = "处于趋势初段：按他的规则，此时不看阿姆士和宽广度找转折。"
    else:
        note = "趋势阶段未指定：他要求只在趋势中后段使用，而「中后段」没有可计算的定义，需自行判断。"
    return {
        "tier": trin_tier(trin),
        "nearest": best,
        "distance": round(dist, 2),
        "similar": dist <= _NEAR,
        "note": note,
    }


def shrinking_rally(up_ratio: float, trin: float) -> bool:
    """缩量普涨：约八成以上个股上涨，但阿姆士高于 1。

    他在 10/13、10/19、10/23、11/02、11/04（阿姆士 1.6）、11/05（红盘 88%、阿姆士 2 点多）
    都用这个组合判定「反弹不是反转」（研判第13、16、17集）。0.8 取自他说的「八成」。
    注意：第21集画面里 10/23 的阿姆士是 0.90，与他 11/02 说的「在 1 以上」不一致，口径可能不同。
    """
    return up_ratio >= 0.8 and trin > 1.0
