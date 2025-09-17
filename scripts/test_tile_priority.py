import tempfile
from pathlib import Path
import sys
proj_root = Path(__file__).resolve().parent.parent
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

from backend.main import get_tile_cache_path, DATA_DIR, get_tile_image
from backend.config import settings
from PIL import Image
from io import BytesIO

# Create a temp tiles dir
tmp = tempfile.TemporaryDirectory()
# point DATA_DIR/tiles to tmp for the duration of this test by creating a file there
tiles_dir = DATA_DIR / 'tiles'
tiles_dir.mkdir(parents=True, exist_ok=True)

# choose tile coords
tx, ty = 99, 99
# ensure cache path has an old placeholder
cache_path = get_tile_cache_path(tx,ty)
cache_path.parent.mkdir(parents=True, exist_ok=True)
Image.new('RGBA',(settings.tile_px, settings.tile_px),(255,0,0,255)).save(cache_path)
# create a real tile in data/tiles that should be preferred
tile_path = tiles_dir / f'tile_{tx}_{ty}.png'
Image.new('RGBA',(settings.tile_px, settings.tile_px),(0,255,0,255)).save(tile_path)

# call get_tile_image (it's async) via its wrapper for testing
import asyncio
async def run_test():
    resp = await get_tile_image(tx,ty)
    # resp is starlette.responses.Response; get body
    body = b''.join([chunk async for chunk in resp.body_iterator]) if hasattr(resp, 'body_iterator') else resp.body
    print('len', len(body))
    print('first8', body[:8])

asyncio.get_event_loop().run_until_complete(run_test())
