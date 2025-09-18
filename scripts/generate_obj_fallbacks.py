#!/usr/bin/env python3
"""Generate simple textured-quad OBJ/MTL/_fallback.png for objects.json entries
when the corresponding .obj is missing. This prevents many 404s when the frontend
attempts .glb -> .obj fallbacks.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json
import textwrap

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / 'assets' / 'glb'
OBJ_SIZE = 1.0

def make_png(p: Path, label: str = ''):
    # Create a simple 256x256 preview PNG with the label
    sz = (256,256)
    img = Image.new('RGBA', sz, (200,200,200,255))
    draw = ImageDraw.Draw(img)
    try:
        f = ImageFont.load_default()
        draw.text((8,8), label, fill=(30,30,30), font=f)
    except Exception:
        pass
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)

def make_obj(obj_path: Path, mtl_name: str):
    # Simple quad centered at origin, lying on XZ plane (Y up)
    content = textwrap.dedent(f"""
    mtllib {mtl_name}
    v -0.5 0 0.5
    v 0.5 0 0.5
    v 0.5 0 -0.5
    v -0.5 0 -0.5
    vt 0 0
    vt 1 0
    vt 1 1
    vt 0 1
    usemtl mat0
    f 1/1 2/2 3/3 4/4
    """)
    obj_path.write_text(content, encoding='utf-8')

def make_mtl(mtl_path: Path, tex_name: str):
    content = textwrap.dedent(f"""
    # generated minimal MTL
    newmtl mat0
    Ka 1.000 1.000 1.000
    Kd 1.000 1.000 1.000
    Ks 0.000 0.000 0.000
    d 1.0
    illum 2
    map_Kd {tex_name}
    """)
    mtl_path.write_text(content, encoding='utf-8')

def main():
    oj = ASSET_DIR / 'objects.json'
    if not oj.exists():
        print('objects.json not found; abort')
        return
    data = json.loads(oj.read_text(encoding='utf-8'))
    created = []
    for entry in data:
        url = entry.get('glb_url','')
        if not url or not url.lower().endswith('.glb'):
            continue
        # strip leading /assets/glb/ if present
        name = Path(url).name
        obj_name = name[:-4] + '.obj'  # replace .glb
        obj_path = ASSET_DIR / obj_name
        if obj_path.exists():
            continue
        # create fallback png and mtl and obj
        png_name = obj_name[:-4] + '_fallback.png'
        png_path = ASSET_DIR / png_name
        if not png_path.exists():
            make_png(png_path, label=obj_name[:-4])
        mtl_name = obj_name[:-4] + '.mtl'
        mtl_path = ASSET_DIR / mtl_name
        if not mtl_path.exists():
            # reference the png by file name
            make_mtl(mtl_path, png_name)
        # write the obj that uses the mtl
        make_obj(obj_path, mtl_name)
        created.append(obj_path.name)
    if created:
        print('Created fallback OBJs:')
        for c in created:
            print(' -', c)
    else:
        print('No fallback OBJ created (all present)')

if __name__ == '__main__':
    main()
