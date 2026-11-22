import json, glob, math, collections
LAT0, LON0 = 12.9716, 77.5946
KX = 111320*math.cos(math.radians(LAT0)); KY = 110574
n=0; src=collections.Counter(); rows=[]
for f in glob.glob('web/data/c_*.json'):
    for rec in json.load(open(f)):
        h, xy, s = rec[0], rec[1], rec[2]
        n+=1; src[s]+=1
        if h>=100:
            xs=xy[0::2]; ys=xy[1::2]
            rows.append((round(h,1), s, round(LAT0+sum(ys)/len(ys)/KY,5), round(LON0+sum(xs)/len(xs)/KX,5)))
print('total', n); print('by source', dict(sorted(src.items())))
print('>=100 m:', len(rows), '  >165 m:', sum(1 for r in rows if r[0]>165))
for r in sorted(rows, reverse=True)[:15]: print(r)
