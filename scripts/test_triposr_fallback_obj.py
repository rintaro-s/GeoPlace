import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend.models import three_d
from backend.config import settings

# Temporarily set TRIPOSR_DIR to a non-existent path to force fallback
orig_dir = settings.TRIPOSR_DIR
settings.TRIPOSR_DIR = 'Z:/nonexistent/triposr'

# prepare fake png bytes
png = b'\x89PNG\r\n\x1a\n' + b'\x00'*100
out_path = Path(__file__).resolve().parent.parent / 'assets' / 'glb' / 'testfallback_light.obj'
if out_path.exists():
    out_path.unlink()

result = three_d.generate_glb_from_image(png, out_path, quality='light')
print('result:', result)
print('exists:', result.exists())
print('siblings:', list(result.parent.glob(result.stem + '*')))

# restore
settings.TRIPOSR_DIR = orig_dir
