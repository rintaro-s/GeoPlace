import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend import pipeline
from backend.config import settings
from backend.models import vlm, sd, three_d
from PIL import Image

# Monkeypatch VLM/SD/three_d for a deterministic run
orig_vlm_extract = vlm.extract_attributes
orig_sd_generate = sd.generate_image
orig_three_generate = three_d.generate_glb_from_image

def fake_extract(model, image_bytes):
    class A:
        def __init__(self):
            self.category='test'
            self.colors=['red']
            self.size='small'
            self.orientation='front'
            self.details=['d']
        def __dict__(self):
            return self.__dict__
    return A()

def fake_sd_generate(model, prompt):
    img = Image.new('RGBA', (512,512), (123,222,111,255))
    from io import BytesIO
    bio = BytesIO()
    img.save(bio, format='PNG')
    return bio.getvalue()

def fake_three(img_bytes, out_path, quality='light'):
    # create an obj (or glb depending on requested suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == '.obj':
        p = out_path
        with open(p, 'w', encoding='utf-8') as f:
            f.write('o fake\nv 0 0 0\n')
        return p
    else:
        with open(out_path, 'wb') as f:
            f.write(b'GLB_FAKE')
        return out_path

vlm.extract_attributes = fake_extract
sd.generate_image = fake_sd_generate
three_d.generate_glb_from_image = fake_three

# run pipeline
img = b'fakebytes'
path, meta = pipeline.run_light_pipeline(img)
print('PIPELINE RESULT:', path, meta)

# cleanup / restore
vlm.extract_attributes = orig_vlm_extract
sd.generate_image = orig_sd_generate
three_d.generate_glb_from_image = orig_three_generate
