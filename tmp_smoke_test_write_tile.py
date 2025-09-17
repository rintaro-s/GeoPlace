from backend.main import write_tile_to_canvas, DATA_DIR, settings
from backend.main import tile_memory_cache, TILE_PX
from backend.main import modified_tiles
from backend.main import get_tile_cache_path
from backend.main import load_objects
from backend.main import load_canvas

from backend.main import Image
from pydantic import BaseModel

class DummyPayload(BaseModel):
    tile_x: int
    tile_y: int
    pixels: list
    tile_size: int
    user_id: str

# create a simple red tile
pixels = [[255,0,0,255] for _ in range(TILE_PX*TILE_PX)]
pl = DummyPayload(tile_x=2, tile_y=3, pixels=pixels, tile_size=TILE_PX, user_id='test')

write_tile_to_canvas(pl)

print('Tile saved to', DATA_DIR / 'tiles' / f'tile_{pl.tile_x}_{pl.tile_y}.png')
cache_path = settings.cache_path / 'images' / f'tile_{pl.tile_x}_{pl.tile_y}.png'
print('Cache path exists:', cache_path.exists())
key = f"{pl.tile_x},{pl.tile_y}"
print('In-memory cache contains key:', key in tile_memory_cache)
print('Modified tiles contains:', (pl.tile_x,pl.tile_y) in modified_tiles)
