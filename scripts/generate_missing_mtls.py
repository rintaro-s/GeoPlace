#!/usr/bin/env python3
"""Create minimal .mtl files for .obj assets that lack them.

Behavior:
- For each .obj in assets/glb, if .mtl missing, try to find a texture:
  - prefer <base>_fallback.png
  - then prefer <base>.png
  - otherwise generate a simple material with a flat diffuse color
- Write a minimal MTL that references the texture (map_Kd) so A-Frame/three.js displays textured OBJ.
"""
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / 'assets' / 'glb'

def find_texture_for(base: Path):
    # candidates in order
    candidates = [base.with_name(base.stem + '_fallback.png'), base.with_name(base.stem + '.png')]
    for c in candidates:
        if c.exists():
            return c.name
    # try searching subfolder with same basename
    subdir = ASSET_DIR / base.stem
    if subdir.exists() and subdir.is_dir():
        for p in subdir.iterdir():
            if p.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                return str((base.stem + '/' + p.name))
    return None

def generate_mtl_for(obj_path: Path):
    mtl_path = obj_path.with_suffix('.mtl')
    if mtl_path.exists():
        return False
    tex = find_texture_for(obj_path)
    if tex:
        content = textwrap.dedent(f"""
        # generated minimal MTL for {obj_path.name}
        newmtl mat0
        Ka 1.000 1.000 1.000
        Kd 1.000 1.000 1.000
        Ks 0.000 0.000 0.000
        d 1.0
        illum 2
        map_Kd {tex}
        """)
    else:
        # fallback: simple grey material
        content = textwrap.dedent(f"""
        # generated minimal MTL for {obj_path.name}
        newmtl mat0
        Ka 0.200 0.200 0.200
        Kd 0.800 0.800 0.800
        Ks 0.000 0.000 0.000
        d 1.0
        illum 2
        """)
    mtl_path.write_text(content, encoding='utf-8')
    return True

def main():
    created = []
    for obj in ASSET_DIR.rglob('*.obj'):
        try:
            if generate_mtl_for(obj):
                created.append(obj.with_suffix('.mtl').name)
        except Exception as e:
            print('error for', obj.name, e)
    if created:
        print('Created MTL files:')
        for c in created:
            print(' -', c)
    else:
        print('No MTL files needed')

if __name__ == '__main__':
    main()
