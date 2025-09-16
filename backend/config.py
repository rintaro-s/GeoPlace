"""Configuration loader for GeoPlace"""
from __future__ import annotations
from pathlib import Path
import yaml
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / 'backend' / 'config.yaml'

@lru_cache()
def get_config() -> dict:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class Settings:
    def __init__(self, d: dict):
        self.tile_px = d.get('TILE_PX', 32)
        self.embed_top_k = d.get('EMBED_TOP_K', 8)
        self.sd_resolution = d.get('SD_RESOLUTION', 512)
        self.sd_steps_light = d.get('SD_STEPS_LIGHT', 20)
        self.sd_steps_high = d.get('SD_STEPS_HIGH', 50)
        self.max_workers = d.get('MAX_CONCURRENT_WORKERS', 4)
        self.per_tile_cooldown = d.get('PER_TILE_COOLDOWN', 5)
        self.canvas_width = d.get('CANVAS_WIDTH', 20000)
        self.canvas_height = d.get('CANVAS_HEIGHT', 20000)
        self.assets_dir = d.get('ASSETS_DIR', 'assets')
        self.glb_subdir = d.get('GLB_SUBDIR', 'glb')
        self.cache_dir = d.get('CACHE_DIR', 'backend/cache')
        self.objects_json_name = d.get('OBJECTS_JSON', 'objects.json')
        self.enable_refiner = d.get('ENABLE_REFINER', True)
        self.refine_delay_sec = d.get('REFINE_DELAY_SEC', 5)
        # TripoSR / SD settings
        self.TRIPOSR_DIR = d.get('TRIPOSR_DIR', None)
        self.TRIPOSR_PY = d.get('TRIPOSR_PY', 'run.py')
        self.TRIPOSR_BAKE_TEXTURE = d.get('TRIPOSR_BAKE_TEXTURE', True)
        self.SD_MODEL_ID = d.get('SD_MODEL_ID', 'runwayml/stable-diffusion-v1-5')

    @property
    def glb_dir(self) -> Path:
        return ROOT / self.assets_dir / self.glb_subdir

    @property
    def objects_json_path(self) -> Path:
        return self.glb_dir / self.objects_json_name

    @property
    def cache_path(self) -> Path:
        return ROOT / self.cache_dir


def load_settings() -> Settings:
    return Settings(get_config())

settings = load_settings()
