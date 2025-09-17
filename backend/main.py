"""FastAPI backend with WebSocket for GeoPlace

機能:
- /api/paint : タイル差分受信 (JSON: {tile_x, tile_y, pixels: [[r,g,b,a],...], user_id, tile_size})
- /api/generate : 変更タイルの 3D 生成ジョブを手動トリガー
- /api/status : 現在のジョブ / 変更タイル状況
- WebSocket /ws : objects.json 更新や進捗通知

簡易実装方針: メモリ管理 (本番は Redis などに移行)
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import APIRouter
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Set, Tuple
import uvicorn
from pathlib import Path
import json
import time
from PIL import Image
# allow very large canvas images (disable decompression bomb check)
try:
    # set to a high value instead of None to avoid issues on some Pillow builds
    Image.MAX_IMAGE_PIXELS = 1000000000  # 1 billion pixels
except Exception:
    pass
import threading
from fastapi.staticfiles import StaticFiles
from concurrent.futures import ThreadPoolExecutor
try:
    # when run as a package (python -m backend.main) relative imports work
    from .config import settings
    from . import pipeline
except Exception:
    # when executed as a script (python backend/main.py) __package__ may be None
    # add project root to sys.path and import by absolute package name
    import sys
    proj_root = Path(__file__).resolve().parent.parent
    if str(proj_root) not in sys.path:
        sys.path.insert(0, str(proj_root))
    # now import using absolute names
    from backend.config import settings
    import backend.pipeline as pipeline
import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
ASSET_GLB_DIR = ROOT / 'assets' / 'glb'
STATE_DIR = ROOT / 'backend' / 'cache'
CANVAS_PATH = DATA_DIR / 'canvas.png'
OBJECTS_JSON = ASSET_GLB_DIR / 'objects.json'
TILE_PX = settings.tile_px

app = FastAPI(title="GeoPlace API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api")

# include router so /api endpoints are available
app.include_router(router)

# ---- Data Structures ----
class PaintPayload(BaseModel):
    tile_x: int
    tile_y: int
    pixels: List[List[int]]  # flat RGBA* (tile_size*tile_size * 4) ではなく 1pixel=[r,g,b,a]
    tile_size: int = TILE_PX
    user_id: str

class GeneratePayload(BaseModel):
    # 対象タイル (省略時: 全変更タイル)
    tiles: List[Tuple[int,int]] | None = None

# 変更追跡
modified_tiles: Set[Tuple[int,int]] = set()
# ジョブ詳細格納
# job_id -> dict(status, tiles, progress, quality_stage, results)
current_jobs: Dict[str, Dict] = {}
# WebSocket 接続プール
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# executor 定義位置修正
executor = ThreadPoolExecutor(max_workers=settings.max_workers)

# model load state
model_status = {
    'sd_loaded': False,
    'sd_error': None,
}

# ---- Helpers ----

def ensure_canvas():
    CANVAS_W, CANVAS_H = settings.canvas_width, settings.canvas_height
    if not CANVAS_PATH.exists():
        CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Create a completely transparent canvas
        img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (0,0,0,0))
        img.save(CANVAS_PATH)
        print(f"Created new transparent canvas: {CANVAS_PATH}")


def load_canvas() -> Image.Image:
    ensure_canvas()
    # ensure Pillow will allow opening very large images (defensive set)
    try:
        Image.MAX_IMAGE_PIXELS = 2000000000
    except Exception:
        pass
    return Image.open(CANVAS_PATH).convert('RGBA')


def save_canvas(img: Image.Image):
    img.save(CANVAS_PATH)


def save_objects(objects: list):
    ASSET_GLB_DIR.mkdir(parents=True, exist_ok=True)
    with open(OBJECTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(objects, f, ensure_ascii=False, indent=2)


def load_objects() -> list:
    if OBJECTS_JSON.exists():
        return json.loads(OBJECTS_JSON.read_text(encoding='utf-8'))
    return []


def tile_bbox(tile_x: int, tile_y: int, tile_size: int) -> Tuple[int,int,int,int]:
    x0 = tile_x * tile_size
    y0 = tile_y * tile_size
    return x0, y0, x0 + tile_size, y0 + tile_size


def write_tile_to_canvas(payload: PaintPayload):
    # Save per-tile PNG under data/tiles to avoid reopening the huge canvas
    tiles_dir = DATA_DIR / 'tiles'
    tiles_dir.mkdir(parents=True, exist_ok=True)
    if len(payload.pixels) != payload.tile_size * payload.tile_size:
        raise ValueError('pixel length mismatch')
    tile_img = Image.new('RGBA', (payload.tile_size, payload.tile_size))
    tile_img.putdata([tuple(p) for p in payload.pixels])
    tile_path = tiles_dir / f'tile_{payload.tile_x}_{payload.tile_y}.png'
    tile_img.save(tile_path)
    # mark modified
    modified_tiles.add((payload.tile_x, payload.tile_y))

# ---- 3D Generation Placeholder ----

def generate_glb_for_tile(tile_x: int, tile_y: int, tile_size: int) -> Path:
    """差分タイルから簡易 GLB (ダミー) を生成しファイルパスを返す"""
    # 実際は: 切り出し→VLM→SD→TripoSR→Open3D 後 GLB
    glb_name = f"tile_{tile_x}_{tile_y}.glb"
    out_path = ASSET_GLB_DIR / glb_name
    if not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    if not out_path.exists():
        with open(out_path, 'wb') as f:
            f.write(b'GLB_PLACEHOLDER')
    return out_path


def job_thread(job_id: str, tiles: List[Tuple[int,int]], tile_size: int):
    current_jobs[job_id]['status'] = 'processing'
    objects = load_objects()
    for (tx,ty) in tiles:
        glb_path = generate_glb_for_tile(tx,ty,tile_size)
        # 3D配置座標: タイル座標をそのまま平面へ (Z=0)
        entry = {
            'id': f'tile_{tx}_{ty}',
            'x': tx * tile_size / 10.0,  # スケール調整
            'y': 0,
            'z': ty * tile_size / 10.0,
            'rotation': [0,0,0],
            'scale': 1.0,
            'glb_url': f'/assets/glb/{glb_path.name}',
            'quality': 'light'
        }
        # 既存置換
        objects = [o for o in objects if o['id'] != entry['id']]
        objects.append(entry)
        current_jobs[job_id]['progress'] = f"generated {entry['id']}"
    save_objects(objects)
    current_jobs[job_id]['status'] = 'done'
    modified_tiles.difference_update(tiles)
    current_jobs[job_id]['progress'] = 'completed'

# ---- 更新: 生成処理 (light) ----

def _cut_tile_image(tile_x: int, tile_y: int, tile_size: int) -> bytes:
    # prefer per-tile saved PNG if present
    tiles_dir = DATA_DIR / 'tiles'
    tile_path = tiles_dir / f'tile_{tile_x}_{tile_y}.png'
    if tile_path.exists():
        return tile_path.read_bytes()
    # fallback: return an empty transparent tile
    from io import BytesIO
    tile = Image.new('RGBA', (tile_size, tile_size), (0,0,0,0))
    bio = BytesIO()
    tile.save(bio, format='PNG')
    return bio.getvalue()


def _run_light_job(job_id: str, tiles: List[Tuple[int,int]], refine: bool):
    current_jobs[job_id]['status'] = 'processing'
    
    # Import the new workflow
    from .workflows.generate_3d import run_complete_3d_workflow, register_3d_object
    
    for idx, (tx, ty) in enumerate(tiles):
        try:
            current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} - VLM分析中...'
            asyncio.run(manager.broadcast({'type':'job_progress','job_id':job_id,'stage':'vlm','progress':current_jobs[job_id]['progress']}))
            
            # Get tile image
            tile_bytes = _cut_tile_image(tx, ty, settings.tile_px)
            
            # Run complete workflow: VLM → SD → TripoSR
            current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} - 3D生成中...'
            asyncio.run(manager.broadcast({'type':'job_progress','job_id':job_id,'stage':'3d_generation','progress':current_jobs[job_id]['progress']}))
            
            glb_path, metadata = run_complete_3d_workflow(tile_bytes, tx, ty)
            
            # Register in objects.json
            register_3d_object(glb_path, metadata, tx, ty)
            
            # Create entry for broadcast
            entry = {
                'id': f'tile_{tx}_{ty}',
                'x': tx * settings.tile_px / 10.0,
                'y': 0,
                'z': ty * settings.tile_px / 10.0,
                'rotation': [0, 0, 0],
                'scale': 1.0,
                'glb_url': f'/assets/{settings.glb_subdir}/{glb_path.name}',
                'quality': metadata.get('quality', 'light'),
                'metadata': metadata,
            }
            
            current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} 完了'
            asyncio.run(manager.broadcast({'type':'job_progress','job_id':job_id,'stage':'complete','entry':entry}))
            
        except Exception as e:
            error_msg = f'タイル {tx},{ty} エラー: {str(e)}'
            current_jobs[job_id]['progress'] = error_msg
            print(f"3D generation error for tile {tx},{ty}: {e}")
            asyncio.run(manager.broadcast({'type':'job_error','job_id':job_id,'error':error_msg}))
    
    # Mark tiles as processed
    modified_tiles.difference_update(tiles)
    current_jobs[job_id]['status'] = 'completed'
    asyncio.run(manager.broadcast({'type':'job_done','job_id':job_id,'stage':'all_complete'}))

    # refine スケジュール
    if refine and settings.enable_refiner:
        current_jobs[job_id]['status'] = 'refining'
        def _refine_job():
            objects_local = load_objects()
            for idx,(tx,ty) in enumerate(tiles):
                entry_id = f'tile_{tx}_{ty}'
                obj = next((o for o in objects_local if o['id']==entry_id), None)
                if not obj: continue
                glb_name = Path(obj['glb_url']).name
                light_path = settings.glb_dir / glb_name
                refined_path, meta = pipeline.run_refine_pipeline(light_path)
                obj['glb_url'] = f'/assets/{settings.glb_subdir}/{refined_path.name}'
                obj['quality'] = 'refined'
                obj['meta_refined'] = meta
                current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} refined'
                asyncio.run(manager.broadcast({'type':'job_progress','job_id':job_id,'stage':'refine','entry':obj}))
            save_objects(objects_local)
            current_jobs[job_id]['status'] = 'refined_ready'
            asyncio.run(manager.broadcast({'type':'job_done','job_id':job_id,'stage':'refine'}))
        threading.Thread(target=_refine_job, daemon=True).start()


# ---- Admin / model management ----
@router.get('/admin/models')
async def admin_models():
    return model_status


@app.get('/api/admin/models')
async def admin_models_wr():
    return await admin_models()


@router.post('/admin/clear_cache')
async def admin_clear_cache():
    # clear pipeline cache directory
    p = settings.cache_path / 'pipe'
    if p.exists():
        import shutil
        shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
    return {'ok': True}


@app.post('/api/admin/clear_cache')
async def admin_clear_cache_wr():
    return await admin_clear_cache()

@router.get('/tiles')
async def list_tiles():
    """List all available tiles"""
    tiles = []
    tile_dir = DATA_DIR / 'tiles'
    if tile_dir.exists():
        for tile_file in tile_dir.glob('tile_*.png'):
            parts = tile_file.stem.split('_')
            if len(parts) == 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    tiles.append({'x': x, 'y': y, 'url': f'/data/tiles/{tile_file.name}'})
                except ValueError:
                    continue
    return tiles

import hashlib
import os

# Tile cache directory
TILE_CACHE_DIR = Path("E:/files/GeoPLace-tmp/images")
TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory cache for recently accessed tiles
tile_memory_cache = {}
MAX_MEMORY_CACHE = 500

def get_tile_cache_path(tile_x: int, tile_y: int) -> Path:
    """Get cache file path for a tile"""
    return TILE_CACHE_DIR / f"tile_{tile_x}_{tile_y}.png"

@router.get('/tile/{tile_x}/{tile_y}')
async def get_tile_image(tile_x: int, tile_y: int):
    """Extract and serve a specific tile from the main canvas with aggressive caching"""
    from fastapi.responses import Response
    from io import BytesIO
    
    tile_key = f"{tile_x},{tile_y}"
    
    try:
        # 1. Check memory cache first (fastest)
        if tile_key in tile_memory_cache:
            return Response(content=tile_memory_cache[tile_key], media_type='image/png')
        
        # 2. Check disk cache
        cache_path = get_tile_cache_path(tile_x, tile_y)
        if cache_path.exists():
            tile_data = cache_path.read_bytes()
            # Store in memory cache
            if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                tile_memory_cache[tile_key] = tile_data
            return Response(content=tile_data, media_type='image/png')
        
        # 3. Check individual tile file
        tile_path = DATA_DIR / 'tiles' / f'tile_{tile_x}_{tile_y}.png'
        if tile_path.exists():
            tile_data = tile_path.read_bytes()
            # Cache to disk and memory
            cache_path.write_bytes(tile_data)
            if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                tile_memory_cache[tile_key] = tile_data
            return Response(content=tile_data, media_type='image/png')
        
        # 4. Extract from main canvas (slowest path)
        canvas_img = load_canvas()
        
        # Calculate tile boundaries using settings
        start_x = tile_x * settings.tile_px
        start_y = tile_y * settings.tile_px
        end_x = min(start_x + settings.tile_px, canvas_img.width)
        end_y = min(start_y + settings.tile_px, canvas_img.height)
        
        # Check if tile is within canvas bounds
        if start_x >= canvas_img.width or start_y >= canvas_img.height:
            # Create and cache transparent tile
            transparent_tile = Image.new('RGBA', (settings.tile_px, settings.tile_px), (0, 0, 0, 0))
            buffer = BytesIO()
            transparent_tile.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)  # Reset buffer position
            tile_data = buffer.getvalue()
            
            # Verify data is not empty
            if len(tile_data) == 0:
                print(f"Warning: Empty tile data for transparent tile {tile_x},{tile_y}")
                # Create minimal PNG manually
                transparent_tile = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
                buffer = BytesIO()
                transparent_tile.save(buffer, format='PNG')
                buffer.seek(0)
                tile_data = buffer.getvalue()
            
            # Cache transparent tile
            try:
                cache_path.write_bytes(tile_data)
            except Exception as e:
                print(f"Failed to cache tile {tile_x},{tile_y}: {e}")
            
            if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                tile_memory_cache[tile_key] = tile_data
            
            return Response(content=tile_data, media_type='image/png')
        
        # Extract tile from canvas
        tile_img = canvas_img.crop((start_x, start_y, end_x, end_y))
        
        # If tile is smaller than tile_px (edge tiles), pad with transparency
        if tile_img.width < settings.tile_px or tile_img.height < settings.tile_px:
            padded_tile = Image.new('RGBA', (settings.tile_px, settings.tile_px), (0, 0, 0, 0))
            padded_tile.paste(tile_img, (0, 0))
            tile_img = padded_tile
        
        # Save to buffer with optimization
        buffer = BytesIO()
        tile_img.save(buffer, format='PNG', optimize=True, compress_level=1)
        buffer.seek(0)  # Reset buffer position
        tile_data = buffer.getvalue()
        
        # Verify data is not empty
        if len(tile_data) == 0:
            print(f"Warning: Empty tile data for tile {tile_x},{tile_y}")
            # Fallback: create simple colored tile
            fallback_tile = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
            buffer = BytesIO()
            fallback_tile.save(buffer, format='PNG')
            buffer.seek(0)
            tile_data = buffer.getvalue()
        
        # Cache to disk and memory
        try:
            cache_path.write_bytes(tile_data)
        except Exception as e:
            print(f"Failed to cache tile {tile_x},{tile_y}: {e}")
            
        if len(tile_memory_cache) < MAX_MEMORY_CACHE:
            tile_memory_cache[tile_key] = tile_data
        
        return Response(content=tile_data, media_type='image/png')
        
    except Exception as e:
        print(f"Error serving tile {tile_x},{tile_y}: {e}")
        # Return cached transparent tile or create new one
        transparent_tile = Image.new('RGBA', (settings.tile_px, settings.tile_px), (0, 0, 0, 0))
        buffer = BytesIO()
        transparent_tile.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        tile_data = buffer.getvalue()
        
        # Final check for empty data
        if len(tile_data) == 0:
            print(f"Critical: Still empty tile data in exception handler for {tile_x},{tile_y}")
            # Last resort: create minimal valid PNG
            fallback_tile = Image.new('RGBA', (32, 32), (255, 0, 0, 128))  # Semi-transparent red
            buffer = BytesIO()
            fallback_tile.save(buffer, format='PNG')
            buffer.seek(0)
            tile_data = buffer.getvalue()
        
        return Response(content=tile_data, media_type='image/png')

@app.get('/api/tile/{tile_x}/{tile_y}')
async def get_tile_image_wr(tile_x: int, tile_y: int):
    return await get_tile_image(tile_x, tile_y)

@app.get('/api/tiles')
async def get_tiles_wr():
    return await list_tiles()

# ---- API Routes ----
@router.post('/paint')
async def paint(payload: PaintPayload):
    try:
        write_tile_to_canvas(payload)
        modified_tiles.add((payload.tile_x, payload.tile_y))
        
        # Broadcast tile change to all connected clients for collaborative editing
        tile_data = {
            'type': 'tile_updated',
            'tile_x': payload.tile_x,
            'tile_y': payload.tile_y,
            'pixels': payload.pixels
        }
        await manager.broadcast(tile_data)
        
        return {'ok': True, 'modified_count': len(modified_tiles)}
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=400)


# wrapper to ensure app-level routes are always reachable
@app.post('/api/paint')
async def paint_wr(payload: PaintPayload):
    try:
        return await paint(payload)
    except Exception as e:
        import traceback, os
        os.makedirs(ROOT / 'backend' / 'logs', exist_ok=True)
        with open(ROOT / 'backend' / 'logs' / 'error.log', 'a', encoding='utf-8') as fh:
            fh.write(time.strftime('[%Y-%m-%d %H:%M:%S] ')+ '\n')
            traceback.print_exc(file=fh)
            fh.write('\n')
        raise

@router.get('/status/{job_id}')
async def status_job(job_id: str):
    job = current_jobs.get(job_id)
    if not job:
        return JSONResponse({'error':'not found'}, status_code=404)
    return job


@app.get('/api/status/{job_id}')
async def status_job_wr(job_id: str):
    return await status_job(job_id)

@router.post('/generate')
async def generate(payload: GeneratePayload):  # override
    tiles = payload.tiles or list(modified_tiles)
    if not tiles:
        return {'ok': False, 'message': 'no modified tiles'}
    job_id = f"job_{int(time.time()*1000)}"
    current_jobs[job_id] = {'status': 'queued', 'tiles': tiles, 'progress': '', 'quality_stage':'light'}
    loop = asyncio.get_running_loop()
    loop.run_in_executor(executor, _run_light_job, job_id, tiles, True)
    return {'job_id': job_id, 'tiles': tiles}


@app.post('/api/generate')
async def generate_wr(payload: GeneratePayload):
    return await generate(payload)

# 静的配信マウント
app.mount('/frontend', StaticFiles(directory=ROOT / 'frontend'), name='frontend')
app.mount('/assets', StaticFiles(directory=ROOT / 'assets'), name='assets')
app.mount('/data', StaticFiles(directory=ROOT / 'data'), name='data')

# WebSocket 強化: サーバから進捗 push のみ、クライアントメッセージは ping として扱う
@app.websocket('/ws')  # override
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json({'type':'hello','objects':load_objects(),'modified':list(modified_tiles)})
        while True:
            try:
                _ = await ws.receive_text()
                await ws.send_json({'type':'ping_ack'})
            except WebSocketDisconnect:
                break
    finally:
        manager.disconnect(ws)

@app.get('/assets/glb/{filename}')
async def get_glb(filename: str):
    path = ASSET_GLB_DIR / filename
    if path.exists():
        return FileResponse(path)
    return JSONResponse({'error': 'not found'}, status_code=404)

# Admin API endpoints
@app.get('/api/models')
async def list_models():
    """List all generated 3D models"""
    models = []
    if ASSET_GLB_DIR.exists():
        for file_path in ASSET_GLB_DIR.iterdir():
            if file_path.suffix.lower() in ['.glb', '.obj']:
                models.append({
                    'name': file_path.name,
                    'url': f'/assets/glb/{file_path.name}',
                    'type': file_path.suffix.upper()[1:],
                    'size': file_path.stat().st_size,
                    'modified': file_path.stat().st_mtime
                })
    return models

@app.post('/api/admin/delete_models')
async def delete_all_models():
    """Delete all generated 3D models"""
    deleted_count = 0
    if ASSET_GLB_DIR.exists():
        for file_path in ASSET_GLB_DIR.iterdir():
            if file_path.suffix.lower() in ['.glb', '.obj', '.png', '.jpg', '.jpeg']:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")
    
    # Also clear objects.json
    objects_file = ROOT / 'assets' / 'objects.json'
    if objects_file.exists():
        with open(objects_file, 'w') as f:
            json.dump([], f)
    
    return {'deleted_count': deleted_count, 'message': f'Deleted {deleted_count} model files'}

@app.post('/api/admin/delete_images')
async def delete_all_images():
    """Delete all tile images"""
    deleted_count = 0
    tiles_dir = DATA_DIR / 'tiles'
    if tiles_dir.exists():
        for file_path in tiles_dir.iterdir():
            if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")
    
    # Clear modified tiles tracking
    modified_tiles.clear()
    
    return {'deleted_count': deleted_count, 'message': f'Deleted {deleted_count} tile images'}

@app.get('/api/admin/models')
async def admin_model_status():
    """Get detailed model status for admin"""
    return {
        'sd_loaded': model_status.get('sd_loaded', False),
        'sd_error': model_status.get('sd_error'),
        'triposr_available': True,  # Assume available since we have the script
        'current_jobs': len(current_jobs),
        'modified_tiles': len(modified_tiles),
        'timestamp': time.time()
    }

@app.on_event('startup')
async def startup_load_models():
    """Background load SD model to warm cache. Updates model_status."""
    import threading
    def _load():
        try:
            from .models import sd as sdmod
            # read model id from config
            try:
                cfg = __import__('..config', fromlist=['get_config'])
                model_id = cfg.get_config().get('SD_MODEL_ID')
            except Exception:
                model_id = None
            sd = sdmod.load_sd_model(model_id)
            model_status['sd_loaded'] = sd is not None
            model_status['sd_error'] = None if sd is not None else 'diffusers/torch unavailable or failed'
        except Exception as e:
            model_status['sd_loaded'] = False
            model_status['sd_error'] = str(e)
    threading.Thread(target=_load, daemon=True).start()

if __name__ == '__main__':
    # start uvicorn
    uvicorn.run('backend.main:app', host='0.0.0.0', port=8001, reload=False)
