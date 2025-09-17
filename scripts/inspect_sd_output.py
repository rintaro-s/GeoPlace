from pathlib import Path
from PIL import Image, ImageStat
import sys
proj = Path(__file__).resolve().parent.parent
p = proj / 'backend' / 'cache' / 'pipe' / '8bd978424243f6744a1b3753e826e648baccdf312544d630f9db39cce9605bea_sd.png'
print('checking', p)
if not p.exists():
    print('file missing')
    sys.exit(2)
im = Image.open(p).convert('RGBA')
print('size', im.size, 'mode', im.mode)
px = im.load()
# sample some pixels
top_left = px[0,0]
center = px[im.size[0]//2, im.size[1]//2]
print('top-left pixel', top_left)
print('center pixel', center)
stat = ImageStat.Stat(im)
print('means', stat.mean)
print('extrema', stat.extrema)
# histogram
hist = im.histogram()
# RGBA histograms are in chunks of 256
r = hist[0:256]
g = hist[256:512]
b = hist[512:768]
a = hist[768:1024]
print('R non-zero bins:', sum(1 for v in r if v>0))
print('G non-zero bins:', sum(1 for v in g if v>0))
print('B non-zero bins:', sum(1 for v in b if v>0))
print('A non-zero bins:', sum(1 for v in a if v>0))
print('R max bin index', max(range(256), key=lambda i: r[i]))
print('G max bin index', max(range(256), key=lambda i: g[i]))
print('B max bin index', max(range(256), key=lambda i: b[i]))
