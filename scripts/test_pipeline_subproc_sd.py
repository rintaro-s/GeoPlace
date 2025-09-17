"""Test invoking pipeline.run_light_pipeline with subprocess SD fallback.

It will: 
- load a tiny dummy tile image (all zeros)
- call pipeline.run_light_pipeline(tile_bytes)
- print result or error
"""
from backend import pipeline
from pathlib import Path
from PIL import Image

# create a tiny tile
img = Image.new('RGBA', (32,32), (0,0,0,0))
from io import BytesIO
bio = BytesIO()
img.save(bio, format='PNG')
bytes_in = bio.getvalue()

try:
    out_path, meta = pipeline.run_light_pipeline(bytes_in)
    print('pipeline returned:', out_path, meta)
except Exception as e:
    import traceback
    traceback.print_exc()
    print('pipeline error:', e)
