"""Pipeline orchestration for VLM -> SD -> 3D (placeholder implementations)

Provides two main functions:
- run_light_pipeline(tile_image_bytes) -> (glb_path, meta)
- run_refine_pipeline(existing_glb_path) -> (refined_glb_path, meta)

Caching strategy (simplified):
- Hash of tile_image_bytes used to determine cached attribute & glb
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
from typing import Tuple, Dict, Any
from .config import settings
from .models import vlm, sd, three_d

# Lazy singletons
_vlm_model = None
_sd_model = None

def _ensure_models():
    global _vlm_model, _sd_model
    if _vlm_model is None:
        _vlm_model = vlm.load_vlm_model()
    if _sd_model is None:
        # try to load model id from YAML
        model_id = None
        try:
            cfg = __import__('..config', fromlist=['get_config'])
            config_dict = cfg.get_config()
            model_id = config_dict.get('SD_MODEL_ID')
        except Exception:
            model_id = None
        _sd_model = sd.load_sd_model(model_id)


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _cache_dir() -> Path:
    p = settings.cache_path / 'pipe'
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_light_pipeline(tile_image_bytes: bytes) -> Tuple[Path, Dict[str, Any]]:
    _ensure_models()
    h = _hash_bytes(tile_image_bytes)
    cache_dir = _cache_dir()
    meta_path = cache_dir / f"{h}.json"
    glb_path = settings.glb_dir / f"{h}_light.glb"

    if meta_path.exists() and glb_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        return glb_path, meta

    # 1. VLM attr
    attrs = vlm.extract_attributes(_vlm_model, tile_image_bytes)
    prompt = vlm.to_prompt(attrs)
    # 2. SD image
    sd_img_bytes = sd.generate_image(_sd_model, prompt)
    # (本来はここで SD 画像を 3D 生成器へ)
    three_d.generate_glb_from_image(sd_img_bytes, glb_path, quality='light')

    meta = {
        'hash': h,
        'attrs': attrs.__dict__,
        'prompt': prompt,
        'quality': 'light'
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return glb_path, meta


def run_refine_pipeline(existing_glb_path: Path) -> Tuple[Path, Dict[str, Any]]:
    # ここでは既存 GLB をコピーして refined ラベルに変更するだけ
    refined_path = existing_glb_path.with_name(existing_glb_path.stem.replace('_light','') + '_refined.glb')
    if not refined_path.exists():
        data = existing_glb_path.read_bytes()
        with open(refined_path, 'wb') as f:
            f.write(data + b'_REFINED')
    meta = {
        'base': existing_glb_path.name,
        'refined': refined_path.name,
        'quality': 'refined'
    }
    return refined_path, meta
