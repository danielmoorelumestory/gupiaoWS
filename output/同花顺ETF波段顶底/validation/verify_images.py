"""调用已归档的 Claude 独立方法复验两张图，需要 Pillow，不联网。"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "claude-scripts"))
import fit
import long as long_check


def main():
    short = []
    long = []
    tolerance = 1.5 * 40 / (long_check.Y30 - long_check.Y70)
    for period in (13, 12, 14):
        series = fit.cutler(period)
        rmse, max_abs, _ = fit.score(series)
        short.append({"period": period, "segments": 64,
                      "image_rmse_points": rmse, "image_max_abs_points": max_abs})
        covered = total = 0
        for x, (_, top, bottom) in long_check.OBSX.items():
            predicted = long_check.interp(series, 12, 3.6, x)
            if predicted is not None:
                total += 1
                covered += bottom-tolerance <= predicted <= top+tolerance
        long.append({"period": period, "covered_columns": covered,
                     "total_columns": total, "coverage": covered / total})
    if short[0]["image_rmse_points"] >= 0.1 or long[0]["coverage"] <= 0.99:
        raise SystemExit("图像复验未达到既有参考结果，请检查输入或计算变化")
    result = {"status": "passed", "method": "Claude 段中点及同列暗像素范围，路径已改为项目相对路径",
              "long_tolerance_pixels": 1.5,
              "short": short, "long": long,
              "note": "图像吻合度，不是App逐日精确数值误差。"}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (ROOT / "validation/results/image-verification.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
