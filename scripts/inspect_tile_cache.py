import sys
from pathlib import Path

# ensure project root is on sys.path so `import backend` works when run from anywhere
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend import main
from backend.main import TILE_CACHE_DIR, get_tile_cache_path, settings

print('TILE_CACHE_DIR =', TILE_CACHE_DIR)
print('settings.cache_path =', settings.cache_path)

# list some files
files = list(Path(TILE_CACHE_DIR).glob('tile_*.png'))
print('found files count:', len(files))
for i,f in enumerate(files[:10]):
    print(i, f.name, f.stat().st_size)

# check specific tile if provided as arg
if len(sys.argv) > 1:
    tx,ty = map(int, sys.argv[1].split(','))
    p = get_tile_cache_path(tx,ty)
    print('checking', p)
    if p.exists():
        b = p.read_bytes()
        print('size:', len(b))
        print('first8:', b[:8])
    else:
        print('file not found')

print('DATA_DIR tiles count:', len(list(main.DATA_DIR.joinpath('tiles').glob('tile_*.png'))))
