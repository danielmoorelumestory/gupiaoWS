"""离线核验归档完整性、全部历史计算结果及截图检查点；只用标准库。"""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "布鲁斯的金融宝藏/replica"))
from bruce_replica.etf_band import calculate_rows, load_prices


def check(condition, message):
    if not condition:
        raise SystemExit("核验失败：" + message)


def main():
    manifest = json.loads((ROOT / "evidence-sha256.json").read_text())
    for name, expected in manifest.items():
        path = ROOT / name
        check(path.is_file(), f"证据缺失：{name}")
        check(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"SHA-256 不同：{name}")
    rows, source = load_prices(ROOT / "evidence/tencent-588060.json", "sh588060")
    check(len(rows) == 451 and source["source_series"] == "day", "行情数量或来源字段变化")
    calculated = calculate_rows(rows)
    closes = [Fraction(r["close"]) for r in rows]
    checked = 0
    # 独立逐窗有理数法，对照模块的 Decimal 滚动状态实现。
    for i, reading in enumerate(calculated):
        if i < 13:
            check(reading["value"] is None, "初始窗口未满却产生读数")
            continue
        changes = [closes[j] - closes[j-1] for j in range(i-12, i+1)]
        denominator = sum(abs(x) for x in changes)
        expected = 100 * sum(max(x, 0) for x in changes) / denominator if denominator else None
        actual = reading["value"]
        check((actual is None and expected is None) or
              (actual is not None and expected is not None and abs(actual-float(expected)) < 1e-12),
              f"{reading['date']} 与独立 Fraction 计算不同")
        checked += 1
    by_date = {r["date"]: r for r in calculated}
    checkpoints = {"2026-08-18": "71.661", "2026-10-19": "3.478", "2026-11-13": "53.115"}
    for day, expected in checkpoints.items():
        check(by_date[day]["display_value"] == expected, f"检查点 {day}")
    long_results = json.loads((ROOT / "validation/results/long-range-comparison.json").read_text())
    check(len(long_results["points"]) == 327, "长图区间数量变化")
    for point in long_results["points"]:
        check(abs(by_date[point["date"]]["value"] - point["formula"]) < 1e-12,
              f"{point['date']} 与既有长图核验结果不同")
    print(json.dumps({"status": "passed", "evidence_files_sha256": len(manifest),
                      "input_bars": len(rows), "full_windows_verified": checked,
                      "archived_long_chart_points": len(long_results["points"]),
                      "checkpoints": checkpoints, "latest": calculated[-1],
                      "note": "两个历史检查点由用户在Claude会话中回读App数值，出处存于evidence/user-app-readback.json。"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
