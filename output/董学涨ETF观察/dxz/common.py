"""通用工具：数值/日期规范化、带超时重试的 HTTP、原子写 JSON。导入无网络副作用。

部分规范化函数改写自 output/同花顺ETF资金/app/auto_daily.py（_num/_norm_code/_norm_date），
复制到本目录以保证本模块可独立运行。
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from datetime import date as _date, datetime, timedelta, timezone

SH_TZ = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
TIMEOUT = 20
TRIES = 3
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^\d{6}$")
_TAG = re.compile(r"<[^>]+>")


class SourceError(Exception):
    """可识别的来源错误（网络/格式/单位/日期）。"""


def now_sh() -> datetime:
    return datetime.now(SH_TZ)


def now_iso() -> str:
    return now_sh().isoformat(timespec="seconds")


def valid_date(s) -> bool:
    if not isinstance(s, str) or not _DATE_RE.match(s):
        return False
    try:
        _date.fromisoformat(s)
    except ValueError:
        return False
    return True


def norm_date(v) -> str | None:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, _date):
        return v.isoformat()
    s = str(v or "").strip()[:10]
    return s if valid_date(s) else None


def norm_code(v) -> str | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not v.is_integer():
            return None
        v = str(int(v)).zfill(6)
    s = _TAG.sub("", str(v)).strip()
    if re.fullmatch(r"\d{1,6}", s):
        s = s.zfill(6)
    return s if _CODE_RE.match(s) else None


def num(v) -> float | None:
    """'1,234.50' / 1234.5 → float；空、'-'、非数、非有限 → None（绝不当 0）。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    else:
        s = _TAG.sub("", str(v)).replace(",", "").strip()
        if not s or s in ("-", "--"):
            return None
        try:
            f = float(s)
        except ValueError:
            return None
    return f if math.isfinite(f) else None


def session():
    import requests  # 延迟导入
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def http(sess, method: str, url: str, *, pause: float = 1.0, **kw):
    """GET/POST，timeout<=20s，最多 TRIES 次指数退避；非 200 视为失败。失败抛 SourceError。"""
    kw.setdefault("timeout", TIMEOUT)
    last = None
    for i in range(TRIES):
        try:
            r = sess.request(method, url, **kw)
            if r.status_code != 200:
                raise SourceError(f"HTTP {r.status_code} {url}")
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if i < TRIES - 1:
                time.sleep(pause * (2 ** i))
    if isinstance(last, SourceError):
        raise last
    raise SourceError(f"{type(last).__name__}: {last}")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, obj) -> None:
    """先写同目录临时文件再 os.replace；allow_nan=False 拒绝 NaN/Inf 混入。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_bytes_atomic(path, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
