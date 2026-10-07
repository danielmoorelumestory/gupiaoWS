import json,sys,urllib.request,csv,time
def chunk(mk,code,a,b):
    url=f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={mk}{code},day,{a},{b},800,qfq"
    d=json.load(urllib.request.urlopen(url,timeout=30))["data"]
    if isinstance(d,list): return []
    d=d[mk+code]; k=d.get("qfqday") or d.get("day") or []
    return [(r[0],float(r[2])) for r in k]
def fetch(code):
    mk="sh" if code.startswith(("5","6","9")) else "sz"
    rows={}
    for y in range(2010,2027):
        for d,c in chunk(mk,code,f"{y}-01-01",f"{y}-12-31"): rows[d]=c
        time.sleep(0.2)
    return sorted(rows.items())
if __name__=="__main__":
    for code in sys.argv[1:]:
        rows=fetch(code)
        with open(f"{code}.csv","w",newline="") as f:
            w=csv.writer(f); w.writerow(["date","close_qfq"]); w.writerows(rows)
        print(code,len(rows),rows[0][0] if rows else "-",rows[-1][0] if rows else "-")
