import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend.config import settings
from backend.models import three_d
from datetime import datetime
import tempfile

print('Using project root:', proj_root)
print('Using settings.TRIPOSR_DIR (before):', settings.TRIPOSR_DIR)

# create temp triposr dir under cache
tmpdir = settings.cache_path / f'tmp_triposr_{int(datetime.utcnow().timestamp())}'
tmpdir.mkdir(parents=True, exist_ok=True)
# write a run.py that fails (exit non-zero) to simulate TripoSR runtime failure
runpy = tmpdir / 'run.py'
runpy.write_text('import sys\nprint("dummy triposr invoked")\nsys.exit(2)')
print('WROTE dummy run.py at', runpy)

# point settings to this tmpdir
orig_triposr = settings.TRIPOSR_DIR
orig_format = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', None)
settings.TRIPOSR_DIR = str(tmpdir)
settings.TRIPOSR_OUTPUT_FORMAT = 'obj'
print('Temporarily set TRIPOSR_DIR to', settings.TRIPOSR_DIR)
print('Temporarily set TRIPOSR_OUTPUT_FORMAT to', settings.TRIPOSR_OUTPUT_FORMAT)

# prepare fake png bytes (valid small PNG header + IHDR)
png = b'\x89PNG\r\n\x1a\n' + b'\x00'*200
out_path = proj_root / 'assets' / 'glb' / 'tmp_test_output_light.obj'
print('Out path will be', out_path)

try:
    result = three_d.generate_glb_from_image(png, out_path, quality='light')
    print('generate_glb_from_image returned:', result)
    print('exists:', result.exists())
    print('siblings:', [p.name for p in result.parent.glob(result.stem + '*')])
except Exception as e:
    print('Exception from generate_glb_from_image:', e)

# show triposr_logs
logdir = settings.cache_path / 'triposr_logs'
print('logdir:', logdir)
if logdir.exists():
    logs = sorted(logdir.glob('*.log'), key=lambda p: p.stat().st_mtime)
    print('logs count:', len(logs))
    if logs:
        latest = logs[-1]
        print('LATEST LOG:', latest)
        print('--- LOG HEAD ---')
        print('\n'.join(latest.read_text(encoding='utf-8').splitlines()[:200]))

# cleanup: restore settings
settings.TRIPOSR_DIR = orig_triposr
if orig_format is not None:
    settings.TRIPOSR_OUTPUT_FORMAT = orig_format
print('Restored TRIPOSR_DIR to', settings.TRIPOSR_DIR)
