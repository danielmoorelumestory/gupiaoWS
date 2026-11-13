from pathlib import Path
from PIL import Image
im=Image.open(str(Path(__file__).resolve().parents[1]/'evidence/screenshots'/'588060-short-20261113.png')).convert('RGB'); px=im.load()
Y70=(1987*1+1988*1)/2+0.0; Y30=2204.0  # centres from row scan (1987-1989 / 2203-2205)
def y2v(y): return 30+(Y30-y)*40/(Y30-Y70)
def v2y(v): return Y30-(v-30)*(Y30-Y70)/40
def dark(p): return max(p)<90
def darkrows(x,y0=1935,y1=2330):
    return [y for y in range(y0,y1) if dark(px[x,y])]
XC=[19+18*i for i in range(65)]
