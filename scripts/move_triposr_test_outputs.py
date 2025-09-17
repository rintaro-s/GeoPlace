"""Move TripoSR test outputs (input.png, mesh.obj, texture.png) into the project's assets/glb folder

Usage:
    python scripts/move_triposr_test_outputs.py <source_dir> [--hash <hexhash>] [--keep-source]

Behavior:
- Looks for input.png, mesh.obj, texture.png (or variations) inside <source_dir>.
- Creates a destination folder under `assets/glb/` named either `<hash>_light` (if --hash provided) or `manual_import_<timestamp>`.
- Moves/renames files so that the project can reference `<dest>/<name>_light.obj` and `<dest>/<name>_light.png`.
- Optionally keeps the source files if --keep-source is passed.
"""
from pathlib import Path
import shutil
import sys
import argparse
from datetime import datetime

ROOT = Path.cwd()
ASSETS_GLB = ROOT / 'assets' / 'glb'

parser = argparse.ArgumentParser()
parser.add_argument('source', help='Source directory where TripoSR wrote files')
parser.add_argument('--hash', help='Optional hash name to use for destination folder')
parser.add_argument('--keep-source', action='store_true', help='Do not remove source files after moving')
args = parser.parse_args()

src = Path(args.source)
if not src.exists():
    print('Source not found:', src)
    sys.exit(2)

# find candidates
candidates = {p.name.lower(): p for p in src.iterdir() if p.is_file()}
input_img = None
mesh_obj = None
tex = None
for name, p in candidates.items():
    if name in ('input.png', 'input.jpg', 'input.jpeg'):
        input_img = p
    if name in ('mesh.obj', 'model.obj') or p.suffix.lower() == '.obj':
        mesh_obj = p
    if name in ('texture.png', 'texture.jpg', 'texture.jpeg') or p.suffix.lower() in ('.png', '.jpg', '.jpeg'):
        # prefer texture.png name
        if 'texture' in name or 'albedo' in name or 'diffuse' in name:
            tex = p
        elif tex is None:
            tex = p

if not mesh_obj and not input_img:
    print('No mesh.obj or input.png found in', src)
    sys.exit(1)

# dest folder
if args.hash:
    h = args.hash
else:
    h = f"manual_import_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"

dest_dir = ASSETS_GLB / h
dest_dir.mkdir(parents=True, exist_ok=True)

# We want to place files as <h>_light.obj and <h>_light.png (texture)
base_name = h + '_light'

if mesh_obj:
    dest_obj = dest_dir / (base_name + '.obj')
    print('Moving OBJ:', mesh_obj, '->', dest_obj)
    shutil.copy(str(mesh_obj), str(dest_obj))

if tex:
    dest_tex = dest_dir / (base_name + Path(tex).suffix)
    print('Moving texture:', tex, '->', dest_tex)
    shutil.copy(str(tex), str(dest_tex))

if input_img and not tex:
    # also copy input as texture fallback
    dest_tex = dest_dir / (base_name + Path(input_img).suffix)
    print('Copying input image as texture:', input_img, '->', dest_tex)
    shutil.copy(str(input_img), str(dest_tex))

print('Imported to', dest_dir)

if not args.keep_source:
    try:
        for p in (mesh_obj, tex, input_img):
            if p and p.exists():
                p.unlink()
        # remove the directory if empty
        if not any(src.iterdir()):
            src.rmdir()
            print('Removed empty source dir', src)
    except Exception as e:
        print('Warning while cleaning source:', e)

print('Done')
