import shutil
from pathlib import Path
from backend.config import settings
proj = Path(__file__).resolve().parent.parent
print('Project root:', proj)
# find tmp_triposr_* in cache
for p in (settings.cache_path).glob('tmp_triposr_*'):
    print('Removing', p)
    shutil.rmtree(p, ignore_errors=True)
# remove output files we created
for name in ['tmp_test_output_light.obj','tmp_test_output_light_fallback.mtl','tmp_test_output_light_fallback.png']:
    f = proj / 'assets' / 'glb' / name
    if f.exists():
        print('Removing', f)
        f.unlink()
print('Cleanup done')
