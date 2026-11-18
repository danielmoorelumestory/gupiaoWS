"""腾讯后复权日线（分页向前取全历史），缓存到 data/raw/<sym>-tencent-hfq.json.gz。"""
import json, gzip, urllib.request, urllib.error, datetime, time
from pathlib import Path
RAW = Path(__file__).resolve().parent / "data/raw"
def load(sym, end="2026-11-10"):
    p = RAW / f"{sym}-tencent-hfq.json.gz"
    if not p.exists():
        rows, z = {}, "2026-11-14"
        for _ in range(20):
            q = f"appstock/app/fqkline/get?param={sym},day,2005-01-01,{z},640,hfq"
            try: d = json.load(urllib.request.urlopen("https://web.ifzq.gtimg.cn/" + q, timeout=30))["data"][sym]
            except urllib.error.HTTPError: time.sleep(1); d = json.load(urllib.request.urlopen("https://proxy.finance.qq.com/ifzqgtimg/" + q, timeout=30))["data"][sym]  # 501 限流时走备用域名
            b = d.get("hfqday") or d.get("day") or []
            new = [x for x in b if x[0] not in rows]
            for x in b: rows[x[0]] = x
            if len(b) < 640 or not new: break
            z = (datetime.date.fromisoformat(b[0][0]) - datetime.timedelta(days=1)).isoformat()
        p.write_bytes(gzip.compress(json.dumps(sorted(rows.values())).encode(), mtime=0))
    return {x[0]: float(x[2]) for x in json.loads(gzip.decompress(p.read_bytes())) if x[0] <= end}
if __name__ == "__main__":
    for s in ("sh510880", "sh515080", "sh515180", "sz159905", "sh512890", "sh515100", "sh515450", "sh563020", "sz159915"):
        v = load(s); ds = sorted(v); print(s, len(v), ds[0], ds[-1])
