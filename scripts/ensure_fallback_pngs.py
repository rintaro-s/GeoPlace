"""Ensure fallback PNGs exist next to each asset; create a simple preview if missing.

This helps the frontend's textured-plane fallback to have something to show even when MTL/texture files are absent.
"""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / 'assets' / 'glb'

for p in ASSET_DIR.iterdir():
    if p.suffix.lower() in ('.glb', '.obj'):
        png = p.with_name(p.stem + '_fallback.png')
        if not png.exists():
            print('Creating fallback png for', p.name)
            img = Image.new('RGBA', (512,512), (200,200,200,255))
            d = ImageDraw.Draw(img)
            d.rectangle([32,32,480,480], outline=(120,120,120), width=6)
            d.text((40,40), p.name, fill=(10,10,10))
            img.save(png)
print('done')
