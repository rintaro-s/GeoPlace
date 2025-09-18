#!/usr/bin/env python3
"""Ensure frontend-expected .obj files exist for entries in assets/glb/objects.json.

For each entry's glb_url, frontend will try <name>.obj. This script ensures that
<name>.obj exists by copying similar existing .obj, converting .glb->.obj if
possible, or generating a simple textured-quad OBJ/MTL/_fallback.png.
"""
from pathlib import Path
import shutil
import json
import textwrap
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / 'assets' / 'glb'

def find_similar_obj(stem):
    # Look for files that contain the stem or startwith stem
    for p in ASSET_DIR.rglob('*.obj'):
        s = p.stem
        if s == stem:
            return p
    for p in ASSET_DIR.rglob('*.obj'):
        s = p.stem
        if stem in s or s.startswith(stem):
            return p
    return None

def convert_glb_to_obj(glb_path: Path, out_obj: Path) -> bool:
    try:
        import trimesh
        scene = trimesh.load(glb_path, force='scene')
        # export as OBJ into string
        obj_data = scene.export(file_type='obj')
        out_obj.write_text(obj_data, encoding='utf-8')
        return True
    except Exception as e:
        return False

def make_png(p: Path, label: str = ''):
    sz = (256,256)
    img = Image.new('RGBA', sz, (220,220,220,255))
    draw = ImageDraw.Draw(img)
    try:
        f = ImageFont.load_default()
        draw.text((8,8), label, fill=(30,30,30), font=f)
    except Exception:
        pass
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)

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

def make_quad_obj(obj_path: Path, mtl_name: str):
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

def ensure_obj_for_entry(glb_url: str, results: dict):
    name = Path(glb_url).name
    stem = name[:-4]
    expected_obj = ASSET_DIR / (stem + '.obj')
    if expected_obj.exists():
        results['ok'].append(str(expected_obj.name))
        return

    # 1) try to find similar existing obj
    sim = find_similar_obj(stem)
    if sim:
        expected_obj.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sim, expected_obj)
        results['copied'].append((str(sim.name), str(expected_obj.name)))
        return

    # 2) try convert glb -> obj if glb exists and not placeholder
    glb_path = ASSET_DIR / name
    if glb_path.exists():
        # quick check for placeholder markers
        try:
            prefix = glb_path.read_bytes()[:128]
            if not any(m in prefix for m in [b'GLB_PLACEHOLDER', b'GLB_FALLBACK', b'DUMMY_GLB']):
                if convert_glb_to_obj(glb_path, expected_obj):
                    results['converted'].append((str(glb_path.name), str(expected_obj.name)))
                    return
        except Exception:
            pass

    # 3) create textured quad fallback (png + mtl + obj)
    png_name = stem + '_fallback.png'
    png_path = ASSET_DIR / png_name
    if not png_path.exists():
        make_png(png_path, label=stem)
    mtl_name = stem + '.mtl'
    mtl_path = ASSET_DIR / mtl_name
    if not mtl_path.exists():
        make_mtl(mtl_path, png_name)
    make_quad_obj(expected_obj, mtl_name)
    results['generated'].append(str(expected_obj.name))

def main():
    oj = ASSET_DIR / 'objects.json'
    if not oj.exists():
        print('objects.json not found; abort')
        return
    data = json.loads(oj.read_text(encoding='utf-8'))
    results = {'ok':[], 'copied':[], 'converted':[], 'generated':[]}
    for entry in data:
        url = entry.get('glb_url','')
        if not url:
            continue
        # only handle assets under assets/glb
        ensure_obj_for_entry(url, results)

    print('Summary:')
    for k,v in results.items():
        print(f"{k}: {len(v)}")
        for item in v[:50]:
            print('  ', item)

if __name__ == '__main__':
    main()
