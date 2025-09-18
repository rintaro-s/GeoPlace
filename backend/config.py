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
        # Optional path to a dedicated Python executable for running TripoSR
        self.TRIPOSR_PYTHON = d.get('TRIPOSR_PYTHON', None)
        self.TRIPOSR_BAKE_TEXTURE = d.get('TRIPOSR_BAKE_TEXTURE', True)
        self.TRIPOSR_OUTPUT_FORMAT = d.get('TRIPOSR_OUTPUT_FORMAT', 'glb')
        self.SD_MODEL_ID = d.get('SD_MODEL_ID', 'runwayml/stable-diffusion-v1-5')
        # Path to an external python executable for SD worker (optional)
        self.SD_VENV_PYTHON = d.get('SD_VENV_PYTHON', None)
        # VLM (Gemma3 / LMStudio) settings
        # VLM_URL: if present, the pipeline will POST image bytes (base64 JSON) to this URL
        # and expect a JSON response with fields: category, colors, size, orientation, details
        self.VLM_URL = d.get('VLM_URL', None)
        # Optional auth token to include as Authorization: Bearer <token>
        self.VLM_TOKEN = d.get('VLM_TOKEN', None)
        self.VLM_TIMEOUT = d.get('VLM_TIMEOUT', 10)
        self.VLM_RETRIES = d.get('VLM_RETRIES', 2)
        # VLM mode: 'image_b64' (default), 'openai_chat' (LMStudio chat-like messages), or 'multipart'
        self.VLM_MODE = d.get('VLM_MODE', 'image_b64')

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
