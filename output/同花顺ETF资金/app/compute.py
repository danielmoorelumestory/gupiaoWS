"""净流入计算：份额差×NAV，折算过滤，全A/宽基聚合。单位：份额=份，NAV=元，flow=元。"""
from universe import is_broad


def compute_daily_flow(
    shares_t: dict[str, float],
    shares_prev: dict[str, float],
    nav: dict[str, float],
    split_threshold: float = 0.5,
) -> dict[str, float]:
    """逐只 flow = (份额_t − 份额_prev) × NAV_t（元）。

    跳过：无前值(新上市)/当日缺份额(停牌)/前值为0/缺NAV；
    |Δ|/prev > split_threshold 视为疑似折算拆分，剔除。
    """
    out: dict[str, float] = {}
    for code, sh_t in shares_t.items():
        sh_prev = shares_prev.get(code)
        px = nav.get(code)
        if sh_prev is None or sh_prev == 0 or px is None:
            continue
        delta = sh_t - sh_prev
        if abs(delta) / sh_prev > split_threshold:
            continue
        out[code] = delta * px
    return out


def aggregate_flow(flows: dict[str, float]) -> tuple[float, float]:
    """→ (全A合计, 宽基合计)（元）。"""
    total_all = 0.0
    total_broad = 0.0
    for code, f in flows.items():
        total_all += f
        if is_broad(code):
            total_broad += f
    return total_all, total_broad


def cumulative(values: list[float], n: int) -> float:
    """末 n 项之和（n 超长度则全和）。"""
    return sum(values[-n:])
