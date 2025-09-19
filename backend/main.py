"""FastAPI backend with WebSocket for GeoPlace

機能:
- /api/paint : タイル差分受信 (JSON: {tile_x, tile_y, pixels: [[r,g,b,a],...], user_id, tile_size})
- /api/generate : 変更タイルの 3D 生成ジョブを手動トリガー
- /api/status : 現在のジョブ / 変更タイル状況
- WebSocket /ws : objects.json 更新や進捗通知

簡易実装方針: メモリ管理 (本番は Redis などに移行)
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
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
from concurrent.futures import TimeoutError as _TO
try:
    # when run as a package (python -m backend.main) relative imports work
    from .config import settings
    from . import pipeline
except Exception:
    # when executed as a script (python backend/main.py) __package__ may be None
    # add project root to sys.path and import by absolute package name
    from concurrent.futures import TimeoutError as _TO
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


@app.middleware("http")
async def simple_logging_middleware(request: Request, call_next):
    try:
        client = request.client
        cli = f"{client.host}:{client.port}" if client else 'unknown'
        print(f"[HTTP] {cli} -> {request.method} {request.url.path}")
    except Exception:
        print(f"[HTTP] incoming request: {request.method} {request.url.path}")
    try:
        resp = await call_next(request)
        try:
            print(f"[HTTP] {request.method} {request.url.path} -> {resp.status_code}")
        except Exception:
            pass
        return resp
    except Exception as e:
        print(f"[HTTP] error handling {request.method} {request.url.path}: {e}")
        raise

router = APIRouter(prefix="/api")

# include router so /api endpoints are available
app.include_router(router)


@app.middleware("http")
async def glb_placeholder_middleware(request: Request, call_next):
    """Intercept requests to /assets/glb/* to detect placeholder GLB bytes and return 404.

    StaticFiles is mounted at /assets and may serve raw placeholder files directly; this
    middleware checks the file contents first and returns a JSON 404 for known markers
    so frontend fallback logic can run instead of attempting to parse broken GLBs.
    """
    try:
        path = request.url.path
        if path.startswith('/assets/glb/'):
            filename = path.split('/assets/glb/', 1)[1]
            file_path = ASSET_GLB_DIR / filename
            if file_path.exists():
                try:
                    with open(file_path, 'rb') as fh:
                        prefix = fh.read(64)
                    markers = [b'GLB_PLACEHOLDER', b'GLB_FALLBACK', b'DUMMY_GLB']
                    if any(m in prefix for m in markers):
                        return JSONResponse({'error': 'not found (placeholder)'}, status_code=404)
                except Exception:
                    return JSONResponse({'error': 'not found'}, status_code=404)
    except Exception:
        # If anything goes wrong here, fall through to normal handling
        pass
    return await call_next(request)

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

# Main asyncio event loop reference (set on startup) - used to schedule broadcasts from worker threads
MAIN_LOOP = None

def schedule_broadcast(message: dict) -> None:
    """Schedule a broadcast from a non-async/thread context.

    Uses run_coroutine_threadsafe when MAIN_LOOP is available (worker threads).
    If MAIN_LOOP isn't set, attempts to create a local task (best-effort).
    """
    try:
        if MAIN_LOOP is not None:
            import asyncio as _asyncio
            _asyncio.run_coroutine_threadsafe(manager.broadcast(message), MAIN_LOOP)
        else:
            # Best-effort fallback: try to create a task on the current loop
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(message))
            else:
                # last resort: run briefly (will create and close a loop)
                _asyncio.run(manager.broadcast(message))
    except Exception:
        # Swallow exceptions to avoid crashing worker threads; errors will be logged by FastAPI if needed
        pass

# Lock for protecting objects.json read/write across threads
import threading as _threading
OBJECTS_LOCK = _threading.Lock()

# model load state
model_status = {
    'sd_loaded': False,
    'sd_error': None,
}

# ---- Helpers ----

def ensure_canvas():
    CANVAS_W, CANVAS_H = 22400, 21966  # ユーザー指定
    if not CANVAS_PATH.exists():
        CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGBA', (CANVAS_W, CANVAS_H), (255,255,255,0))
        img.save(CANVAS_PATH)


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
    # protect concurrent writes to objects.json
    with OBJECTS_LOCK:
        with open(OBJECTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False, indent=2)


def load_objects() -> list:
    if OBJECTS_JSON.exists():
        with OBJECTS_LOCK:
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
    # Also update disk cache and in-memory cache so that /api/tile serves the latest tile
    try:
        cache_dir = settings.cache_path / 'images'
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / tile_path.name
        tile_bytes = tile_path.read_bytes()
        cache_path.write_bytes(tile_bytes)
        # update in-memory cache if available
        try:
            key = f"{payload.tile_x},{payload.tile_y}"
            if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                tile_memory_cache[key] = tile_bytes
            else:
                # simple LRU-like touch: remove oldest then insert
                try:
                    first_key = next(iter(tile_memory_cache))
                    del tile_memory_cache[first_key]
                except Exception:
                    pass
                tile_memory_cache[key] = tile_bytes
        except NameError:
            # tile_memory_cache not defined yet; ignore
            pass
    except Exception:
        # Do not fail tile save if cache update fails
        pass
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
    objects = load_objects()
    print(f'[JOB {job_id}] started processing {len(tiles)} tiles')
    for idx,(tx,ty) in enumerate(tiles):
        try:
            print(f'[JOB {job_id}] processing tile {tx},{ty} ({idx+1}/{len(tiles)})')
            tile_bytes = _cut_tile_image(tx,ty,settings.tile_px)
            glb_path, meta = pipeline.run_light_pipeline(tile_bytes)
            entry_id = f'tile_{tx}_{ty}'
            entry = {
                'id': entry_id,
                'x': tx * settings.tile_px / 10.0,
                'y': 0,
                'z': ty * settings.tile_px / 10.0,
                'rotation': [0,0,0],
                'scale': 1.0,
                'glb_url': f'/assets/{settings.glb_subdir}/{glb_path.name}',
                'quality': 'light',
                'meta': meta,
            }
            objects = [o for o in objects if o['id'] != entry_id]
            objects.append(entry)
            current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} light generated'
            print(f'[JOB {job_id}] generated {entry_id} -> {glb_path}')
            # use thread-safe scheduling to broadcast from worker thread
            schedule_broadcast({'type':'job_progress','job_id':job_id,'stage':'light','entry':entry})
        except Exception as e:
            # Strict behavior: log error, record in job, and abort remaining work
            import traceback
            tb = traceback.format_exc()
            print(f'[JOB {job_id}] ERROR processing tile {tx},{ty}: {e}\n{tb}')
            current_jobs[job_id]['status'] = 'error'
            current_jobs[job_id]['progress'] = f'error on tile {tx},{ty}: {e}'
            current_jobs[job_id]['error'] = str(e)
            current_jobs[job_id]['error_tb'] = tb
            # broadcast error and stop
            schedule_broadcast({'type':'job_error','job_id':job_id,'message': str(e), 'tile': [tx,ty]})
            save_objects(objects)
            return
    # all tiles processed
    save_objects(objects)
    modified_tiles.difference_update(tiles)
    current_jobs[job_id]['status'] = 'light_ready'
    schedule_broadcast({'type':'job_done','job_id':job_id,'stage':'light'})

    # refine スケジュール
    if refine and settings.enable_refiner:
        current_jobs[job_id]['status'] = 'refining'
        def _refine_job():
            objects_local = load_objects()
            print(f'[JOB {job_id}] starting refine for {len(tiles)} tiles')
            for idx,(tx,ty) in enumerate(tiles):
                try:
                    entry_id = f'tile_{tx}_{ty}'
                    obj = next((o for o in objects_local if o['id']==entry_id), None)
                    if not obj:
                        print(f'[JOB {job_id}] refine: object {entry_id} not found; skipping')
                        continue
                    glb_name = Path(obj['glb_url']).name
                    light_path = settings.glb_dir / glb_name
                    print(f'[JOB {job_id}] refining {entry_id} from {light_path}')
                    # Run refine in the executor with a bounded timeout to avoid long hangs.
                    REFINE_TIMEOUT = getattr(settings, 'REFINE_TIMEOUT_SEC', 60)
                    try:
                        fut = executor.submit(pipeline.run_refine_pipeline, light_path)
                        refined_path, meta = fut.result(timeout=REFINE_TIMEOUT)
                    except _TO:
                        raise RuntimeError(f'refine timed out after {REFINE_TIMEOUT}s')
                    obj['glb_url'] = f'/assets/{settings.glb_subdir}/{refined_path.name}'
                    obj['quality'] = 'refined'
                    obj['meta_refined'] = meta
                    current_jobs[job_id]['progress'] = f'{idx+1}/{len(tiles)} refined'
                    schedule_broadcast({'type':'job_progress','job_id':job_id,'stage':'refine','entry':obj})
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    print(f'[JOB {job_id}] ERROR refining tile {tx},{ty}: {e}\n{tb}')
                    current_jobs[job_id]['status'] = 'error'
                    current_jobs[job_id]['progress'] = f'refine error on tile {tx},{ty}: {e}'
                    current_jobs[job_id]['error'] = str(e)
                    current_jobs[job_id]['error_tb'] = tb
                    schedule_broadcast({'type':'job_error','job_id':job_id,'message': str(e), 'tile': [tx,ty]})
                    save_objects(objects_local)
                    return
            save_objects(objects_local)
            current_jobs[job_id]['status'] = 'refined_ready'
            schedule_broadcast({'type':'job_done','job_id':job_id,'stage':'refine'})
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


@router.get('/objects.json')
async def api_objects():
    """Return objects.json contents for clients"""
    return load_objects()


@app.get('/api/objects.json')
async def api_objects_wr():
    return await api_objects()

import hashlib
import os

# Tile cache directory (configurable via settings.cache_path)
# Per user request: prefer the legacy path E:\files\GeoPLace-tmp\images when it exists.
legacy_paths = [Path(r"E:\files\GeoPLace-tmp\images")]
preferred = settings.cache_path / 'images'
# If the legacy path exists at all, prefer it (even if empty). This matches
# environments where tiles are populated externally into the legacy folder.
if any(p.exists() for p in legacy_paths):
    TILE_CACHE_DIR = next(p for p in legacy_paths if p.exists())
elif preferred.exists() and any(preferred.iterdir()):
    TILE_CACHE_DIR = preferred
else:
    TILE_CACHE_DIR = preferred

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
    import time
    tile_key = f"{tile_x},{tile_y}"
    try:
        # 1. Check memory cache first (fastest)about:blank#blockedE:\files\GeoPLace-tmp\images
        if tile_key in tile_memory_cache:
            tile_data = tile_memory_cache[tile_key]
            return Response(content=tile_data, media_type='image/png', headers={
                'Cache-Control': 'no-store',
                'Content-Length': str(len(tile_data))
            })
        # 2. Prefer per-tile saved PNG in data/tiles. This prevents stale/placeholder
        #    images that were previously written into the disk cache from masking
        #    newly-saved user tiles.
        tile_path = DATA_DIR / 'tiles' / f'tile_{tile_x}_{tile_y}.png'
        if tile_path.exists():
            tile_data = tile_path.read_bytes()
            # Cache to disk and memory for faster subsequent reads
            try:
                cache_path = get_tile_cache_path(tile_x, tile_y)
                cache_path.write_bytes(tile_data)
            except Exception:
                pass
            if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                tile_memory_cache[tile_key] = tile_data
            return Response(content=tile_data, media_type='image/png', headers={
                'Cache-Control': 'no-store',
                'Content-Length': str(len(tile_data))
            })
        # 3. Check disk cache (older placeholder files may exist)
        cache_path = get_tile_cache_path(tile_x, tile_y)
        if cache_path.exists():
            for _ in range(3):
                tile_data = cache_path.read_bytes()
                # PNGヘッダーが壊れていたら再生成
                if tile_data[:8] == b'\x89PNG\r\n\x1a\n':
                    break
                time.sleep(0.05)
            else:
                # 3回リトライしても壊れてたら削除して再生成
                try:
                    cache_path.unlink()
                except Exception:
                    pass
                tile_data = None
            if tile_data:
                if len(tile_memory_cache) < MAX_MEMORY_CACHE:
                    tile_memory_cache[tile_key] = tile_data
                return Response(content=tile_data, media_type='image/png', headers={
                    'Cache-Control': 'no-store',
                    'Content-Length': str(len(tile_data))
                })
        # 4. Return default red tile (do NOT persist this to disk cache)
        tile_img = Image.new('RGBA', (settings.tile_px, settings.tile_px), (255, 0, 0, 255))
        buffer = BytesIO()
        tile_img.save(buffer, format='PNG', optimize=True, compress_level=1)
        tile_data = buffer.getvalue()
        # cache only in-memory to avoid polluting disk cache with placeholders
        if len(tile_memory_cache) < MAX_MEMORY_CACHE:
            tile_memory_cache[tile_key] = tile_data
        return Response(content=tile_data, media_type='image/png', headers={
            'Cache-Control': 'no-store',
            'Content-Length': str(len(tile_data))
        })
    except Exception as e:
        print(f"Error serving tile {tile_x},{tile_y}: {e}")
        tile_img = Image.new('RGBA', (settings.tile_px, settings.tile_px), (255, 0, 0, 255))
        buffer = BytesIO()
        tile_img.save(buffer, format='PNG', optimize=True, compress_level=1)
        tile_data = buffer.getvalue()
        return Response(content=tile_data, media_type='image/png', headers={
            'Cache-Control': 'no-store',
            'Content-Length': str(len(tile_data))
        })

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
    if not path.exists():
        return JSONResponse({'error': 'not found'}, status_code=404)
    try:
        # read small prefix to detect placeholder/broken GLB markers
        with open(path, 'rb') as fh:
            prefix = fh.read(64)
        # common markers produced by our fallback writers
        markers = [b'GLB_PLACEHOLDER', b'GLB_FALLBACK', b'DUMMY_GLB']
        if any(m in prefix for m in markers):
            # treat as missing so frontend will attempt OBJ fallback or textured plane
            return JSONResponse({'error': 'not found (placeholder)'}, status_code=404)
        return FileResponse(path)
    except Exception:
        return JSONResponse({'error': 'not found'}, status_code=404)

@app.on_event('startup')
async def startup_load_models():
    """Background load SD model to warm cache. Updates model_status."""
    import threading
    import asyncio as _asyncio
    # expose the running loop to worker threads
    global MAIN_LOOP
    try:
        MAIN_LOOP = _asyncio.get_running_loop()
    except RuntimeError:
        MAIN_LOOP = None

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


@router.get('/public_info')
async def api_public_info():
    """Return configured public URL and basic server info for frontends.

    This endpoint allows local frontends to discover an externally reachable URL
    (for example an ngrok forwarding URL) so that 'open in browser' actions
    can prefer that URL instead of local file:// links.
    """
    try:
        public = getattr(settings, 'PUBLIC_URL', None)
        # host/port not always known here; include uvicorn info if present in environment
        return {'public_url': public, 'notes': 'If null, use local host links (ngrok can set PUBLIC_URL in config)'}
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get('/api/public_info')
async def api_public_info_wr():
    return await api_public_info()


# ---- Search API (semantic search over VLM logs) ----
@router.get('/search')
async def api_search(q: str, top_k: int = 5, target: str | None = None):
    try:
        from .models import search as searchmod
        lm_url = getattr(settings, 'VLM_URL', None)
        lm_token = getattr(settings, 'VLM_TOKEN', None)
        # allow optional 'target' param to tune prompts (e.g. paint, world_new)
        # forward target (may be used to tailor prompts for different frontends)
        results = searchmod.search_similar(q, top_k=top_k, lm_url=lm_url, lm_token=lm_token, target=target)
        return {'query': q, 'results': results}
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get('/api/search')
async def api_search_wr(q: str, top_k: int = 5, target: str | None = None):
    return await api_search(q, top_k, target)


@router.get('/format_prompt')
async def api_format_prompt(q: str):
    """Return a formatted LMStudio payload (system+user messages) enforcing translation and output rules.

    Useful for debugging and for frontends that want to preview the prompt that will be sent to LM.
    """
    try:
        from .models import search as searchmod
        candidates = searchmod._build_candidates_from_logs()
        payload = searchmod.format_for_lmstudio(q, candidates)
        return payload
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get('/api/format_prompt')
async def api_format_prompt_wr(q: str):
    return await api_format_prompt(q)
