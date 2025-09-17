"""Fix invalid placeholder GLB/OBJ files under assets/glb and update objects.json accordingly.

This script will:
- Detect GLB files that are actually placeholders (contain 'GLB_FALLBACK') and mark them invalid.
- Detect OBJ files that contain the text 'DUMMY_OBJ' or lack vertex definitions and replace them with a simple textured quad OBJ/MTL/PNG.
- If a GLB is invalid but a corresponding .obj exists, remove the invalid GLB so frontend will load the OBJ instead.
- Update assets/glb/objects.json entries so that glb_url points to an existing file (.obj preferred if present).

Run from repo root: python scripts/fix_asset_placeholders.py
"""
from pathlib import Path
from PIL import Image, ImageDraw
import json
import shutil

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / 'assets' / 'glb'
OBJ_PREFIX = ''

if not ASSET_DIR.exists():
    print('assets/glb not found; nothing to do')
    raise SystemExit(1)

# helpers

def read_head(p: Path, n=256):
    try:
        return p.read_bytes()[:n]
    except Exception:
        return b''


def is_invalid_glb(p: Path) -> bool:
    data = read_head(p, 64)
    # valid GLB should start with b'glTF' (0x67 0x6c 0x54 0x46)
    if data.startswith(b'glTF'):
        return False
    # If file contains our placeholder marker, mark invalid
    if b'GLB_FALLBACK' in data or b'GLB_FALLBACK_PLACEHOLDER' in data or b'GLB_FALLBACK_NO_PYTHON' in data:
        return True
    # otherwise, if not starting with glTF -> suspicious
    return True


def obj_needs_fix(p: Path) -> bool:
    try:
        s = p.read_text(errors='ignore')
    except Exception:
        return True
    # trivial invalid content marker
    if 'DUMMY_OBJ' in s:
        return True
    # if no vertex lines, not a valid obj
    for line in s.splitlines():
        if line.strip().startswith('v '):
            return False
    return True


def write_fallback_obj(stem: str, out_dir: Path, texture_source: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj_name = stem + '_fallback.obj'
    mtl_name = stem + '_fallback.mtl'
    tex_name = stem + '_fallback.png'
    obj_path = out_dir / obj_name
    mtl_path = out_dir / mtl_name
    tex_path = out_dir / tex_name
    # create texture: copy texture_source if provided else create gradient
    if texture_source and texture_source.exists():
        shutil.copy(str(texture_source), str(tex_path))
    else:
        # create a simple gradient image
        img = Image.new('RGBA', (512,512))
        d = ImageDraw.Draw(img)
        for y in range(512):
            r = int(80 + (y/511.0) * 120)
            g = int(80 + (y/511.0) * 80)
            b = int(120 + (y/511.0) * 60)
            d.line([(0,y),(511,y)], fill=(r,g,b,255))
        img.save(tex_path)
    # write mtl
    with open(mtl_path, 'w', encoding='utf-8') as mf:
        mf.write(f"newmtl fallback\nmap_Kd {tex_name}\n")
    # write obj quad
    with open(obj_path, 'w', encoding='utf-8') as of:
        of.write(f"mtllib {mtl_name}\n")
        of.write("o fallback_quad\n")
        of.write("v -0.5 -0.5 0.0\n")
        of.write("v 0.5 -0.5 0.0\n")
        of.write("v 0.5 0.5 0.0\n")
        of.write("v -0.5 0.5 0.0\n")
        of.write("vt 0 0\n")
        of.write("vt 1 0\n")
        of.write("vt 1 1\n")
        of.write("vt 0 1\n")
        of.write("usemtl fallback\n")
        of.write("s off\n")
        of.write("f 1/1 2/2 3/3 4/4\n")
    return obj_path


# Scan files
glb_files = list(ASSET_DIR.glob('*.glb'))
obj_files = list(ASSET_DIR.glob('*.obj'))
invalid_glbs = [p for p in glb_files if is_invalid_glb(p)]
bad_objs = [p for p in obj_files if obj_needs_fix(p)]

print(f'Found {len(glb_files)} .glb, {len(obj_files)} .obj, {len(invalid_glbs)} invalid glb, {len(bad_objs)} bad obj')

# Fix bad objs
for p in bad_objs:
    stem = p.stem
    print('Fixing OBJ:', p.name)
    # try to find SD image in cache (backend/cache/pipe/<hash>_sd.png)
    possible = list((ROOT / 'backend' / 'cache' / 'pipe').glob(stem + '*_sd.png'))
    tex_src = possible[0] if possible else None
    fixed = write_fallback_obj(stem, ASSET_DIR, tex_src)
    # move fixed files to replace original (overwrite)
    # ensure names match expected naming convention (stem + '_fallback.obj' vs original)
    # if original file is clearly dummy, remove it
    try:
        p.unlink()
    except Exception:
        pass
    # leave fallback files in place

# For invalid glb with corresponding obj present, remove the glb so .obj will be used instead
for g in invalid_glbs:
    stem = g.stem
    obj_equiv = ASSET_DIR / (stem + '.obj')
    if obj_equiv.exists():
        print('Removing invalid GLB in favor of OBJ:', g.name)
        try:
            g.unlink()
        except Exception as e:
            print('failed to delete', g, e)

# Update objects.json
obj_json = ASSET_DIR / 'objects.json'
if obj_json.exists():
    objs = json.loads(obj_json.read_text(encoding='utf-8'))
    changed = 0
    for entry in objs:
        url = entry.get('glb_url','')
        name = Path(url).name
        p = ASSET_DIR / name
        if p.exists():
            # exists -> good
            continue
        # try .obj
        stem = Path(name).stem
        candidate_obj = ASSET_DIR / (stem + '.obj')
        candidate_glb = ASSET_DIR / (stem + '.glb')
        if candidate_obj.exists():
            entry['glb_url'] = f'/assets/glb/{candidate_obj.name}'
            changed += 1
            print('Updated objects.json entry', entry.get('id'), '->', candidate_obj.name)
        elif candidate_glb.exists():
            entry['glb_url'] = f'/assets/glb/{candidate_glb.name}'
            changed += 1
            print('Updated objects.json entry', entry.get('id'), '->', candidate_glb.name)
        else:
            # try to find any file starting with stem
            any_match = None
            for f in ASSET_DIR.iterdir():
                if f.name.startswith(stem):
                    any_match = f
                    break
            if any_match:
                entry['glb_url'] = f'/assets/glb/{any_match.name}'
                changed += 1
                print('Updated objects.json entry', entry.get('id'), '->', any_match.name)
            else:
                print('No asset found for', name, 'entry', entry.get('id'))
    if changed:
        print('Writing updated objects.json (changes:', changed, ')')
        obj_json.write_text(json.dumps(objs, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        print('objects.json ok, no changes')
else:
    print('objects.json not found; nothing to update')

print('Done')
