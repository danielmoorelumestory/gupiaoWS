from pathlib import Path
from decimal import Decimal
from PIL import Image
import json, math
ROOT=Path(__file__).resolve().parents[1]
raw=json.loads((ROOT/'evidence/tencent-588060.json').read_text())['data']['sh588060']
bars=raw.get('qfqday',raw.get('day',[]))
vis=[(i,b) for i,b in enumerate(bars) if b[0]>='2025-07-10']
image=Image.open(ROOT/'evidence/screenshots/588060-long-20261113.png').convert('RGB')
closes=[Decimal(b[2]) for b in bars]
# Calibrate from the two horizontal threshold lines, independent of candidate values.
y70,y30=2088.5,2244.5
scale=(y30-y70)/40
xfirst,xlast=12.0,1186.0
mask={}
for x in range(10,1190):
    mask[x]=[y for y in range(1970,2350) if max(image.getpixel((x,y)))<85]
points=[]
for k,(j,b) in enumerate(vis):
    ds=[closes[i]-closes[i-1] for i in range(j-12,j+1)]
    numerator=sum(max(v,Decimal(0)) for v in ds)
    denominator=sum(abs(v) for v in ds)
    value=float(100*numerator/denominator) if denominator else 50.0
    x=xfirst+k*(xlast-xfirst)/(len(vis)-1)
    ys=mask.get(round(x),[])
    yobs=sorted(ys)[len(ys)//2] if ys else None
    observed=70+(y70-yobs)/scale if yobs is not None else None
    ypred=y70+(70-value)*scale
    nearby=[math.hypot(xx-x,yy-ypred) for xx in range(max(10,round(x)-5),min(1189,round(x)+5)+1) for yy in mask.get(xx,[]) if abs(yy-ypred)<35]
    distance=min(nearby) if nearby else None
    points.append({'date':b[0],'close':b[2],'x':x,'formula':value,'image_estimate':observed,'image_error':None if observed is None else value-observed,'nearest_trace_distance_px':distance})
errors=[r['image_error'] for r in points if r['image_error'] is not None]
distances=[r['nearest_trace_distance_px'] for r in points if r['nearest_trace_distance_px'] is not None]
summary={'bars':len(points),'start':points[0]['date'],'end':points[-1]['date'],'latest_formula':points[-1]['formula'],'image_sample_count':len(errors),'image_rmse_points':math.sqrt(sum(v*v for v in errors)/len(errors)),'image_mae_points':sum(abs(v) for v in errors)/len(errors),'image_max_abs_points':max(abs(v) for v in errors),'nearest_trace_mean_px':sum(distances)/len(distances),'nearest_trace_max_px':max(distances),'within_2px':sum(v<=2 for v in distances),'within_3px':sum(v<=3 for v in distances),'missing_trace':len(points)-len(distances),'image_calibration':{'xfirst':xfirst,'xlast':xlast,'y70':y70,'y30':y30,'pixels_per_point':scale}}
rank=[]
for n in range(2,101):
    es=[]
    for (j,b),point in zip(vis,points):
        ds=[closes[i]-closes[i-1] for i in range(j-n+1,j+1)]
        u=sum(max(v,Decimal(0)) for v in ds);a=sum(abs(v) for v in ds)
        v=float(100*u/a) if a else 50
        if point['image_estimate'] is not None:es.append(v-point['image_estimate'])
    rank.append({'period':n,'image_rmse_points':math.sqrt(sum(v*v for v in es)/len(es))})
rank.sort(key=lambda r:r['image_rmse_points'])
summary['top_periods']=rank[:5]
# N=13 was fixed using the earlier screenshot; this is a new validation interval.
summary['note']='Image estimates have rasterization and x-coordinate uncertainty; they are not exact App numeric readings. N=13 was fixed before this long screenshot arrived.'
(ROOT/'validation/results/long-range-comparison.json').write_text(json.dumps({'summary':summary,'points':points,'period_ranking':rank},ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
print('max_error_points',json.dumps(sorted(points,key=lambda r:abs(r['image_error'] or 0),reverse=True)[:5],ensure_ascii=False))
