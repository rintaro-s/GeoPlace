from PIL import Image, ImageStat
p = 'c:/Users/s-rin/Documents/GitHub/GeoPlace/backend/cache/pipe/sd_worker_out.png'
im = Image.open(p).convert('RGBA')
print('size', im.size)
stat = ImageStat.Stat(im)
print('means', stat.mean)
print('extrema', stat.extrema)
print('unique R count', len(set([px[0] for px in im.getdata()])))
