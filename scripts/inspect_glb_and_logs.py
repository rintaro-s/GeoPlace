from pathlib import Path
import sys
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))
from backend.config import settings
from datetime import datetime

root = Path(__file__).resolve().parent.parent
# glb path from recent job (example file name)
glb_dir = root / 'assets' / 'glb'
# find latest output (prefer obj if configured)
fmt = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', 'glb')
patterns = []
if fmt == 'obj':
    patterns = ['*_light.obj', '*_light.glb']
else:
    patterns = ['*_light.glb', '*_light.obj']

found = []
for pat in patterns:
    found.extend(list(glb_dir.glob(pat)))
if not found:
    print('no generated outputs found')
    raise SystemExit(1)
latest = sorted(found, key=lambda p: p.stat().st_mtime)[-1]
print('latest output:', latest)
print('size:', latest.stat().st_size)
head = latest.read_bytes()[:256]
print('first 64 bytes:', head[:64])
print('starts with GLB_FALLBACK text?', head.startswith(b'GLB_FALLBACK'))
print('starts with glb magic?', head[:4] == b'glTF')
print('magic (first 4):', head[:4])

# Inspect triposr logs
logdir = settings.cache_path / 'triposr_logs'
print('logdir:', logdir)
if not logdir.exists():
    print('no triposr_logs dir')
    raise SystemExit(0)
logs = sorted([p for p in logdir.glob('*.log')], key=lambda p: p.stat().st_mtime)
if not logs:
    print('no logs')
    raise SystemExit(0)
latest_log = logs[-1]
print('latest_log:', latest_log)
print('--- head of log ---')
print('\n'.join(latest_log.read_text(encoding='utf-8').splitlines()[:200]))
