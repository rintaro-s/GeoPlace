from backend.config import settings
print('TRIPOSR_DIR=', getattr(settings,'TRIPOSR_DIR', None))
print('SD_MODEL_ID=', getattr(settings,'SD_MODEL_ID', None))
from PIL import Image
from io import BytesIO
img = Image.new('RGBA',(32,32),(255,0,0,255))
bio = BytesIO(); img.save(bio,'PNG')
bs = bio.getvalue()
try:
    from backend import pipeline
    p = pipeline.run_light_pipeline(bs)
    print('pipeline returned:', p)
except Exception as e:
    print('pipeline raised:', type(e), e)
