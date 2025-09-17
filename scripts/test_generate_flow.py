import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend import main
from backend import pipeline
from backend.config import settings
from pathlib import Path
from PIL import Image
import json

# Prepare a dummy tile in data/tiles
tx, ty = 7, 8
tiles_dir = main.DATA_DIR / 'tiles'
tiles_dir.mkdir(parents=True, exist_ok=True)
img_path = tiles_dir / f'tile_{tx}_{ty}.png'
Image.new('RGBA', (settings.tile_px, settings.tile_px), (10,20,30,255)).save(img_path)

# Monkeypatch pipeline.run_light_pipeline to avoid heavy external deps
orig_run_light = pipeline.run_light_pipeline

def fake_run_light(tile_bytes):
    # create a dummy glb file in glb_dir
    h = 'fakehash'
    glb_dir = settings.glb_dir
    glb_dir.mkdir(parents=True, exist_ok=True)
    glb_path = glb_dir / f"{h}_light.glb"
    with open(glb_path, 'wb') as f:
        f.write(b'DUMMY_GLB')
    meta = {'hash': h, 'quality': 'light', 'attrs': {}}
    return glb_path, meta

pipeline.run_light_pipeline = fake_run_light

# Create job and run _run_light_job synchronously
job_id = 'job_test_1'
main.current_jobs[job_id] = {'status': 'queued', 'tiles': [(tx,ty)], 'progress': '', 'quality_stage': 'light'}

print('Before run, job status:', main.current_jobs[job_id]['status'])

# Run the job
main._run_light_job(job_id, [(tx,ty)], refine=False)

print('After run, job status:', main.current_jobs[job_id]['status'])
print('Job progress:', main.current_jobs[job_id].get('progress'))

# Inspect objects.json
objs = main.load_objects()
print('Objects count:', len(objs))
if objs:
    print('Last object id:', objs[-1].get('id'))

# Cleanup: restore pipeline function
pipeline.run_light_pipeline = orig_run_light

# remove created dummy files
try:
    img_path.unlink()
except Exception:
    pass
