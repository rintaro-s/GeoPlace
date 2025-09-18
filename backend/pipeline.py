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

import dataclasses


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


def _safe_serialize(obj):
    """Recursively convert an object to JSON-serializable types.

    - dataclasses -> asdict
    - dict/list/tuple -> recurse
    - objects with __dict__ -> dict of non-callable attrs
    - others -> return as-is (str if not serializable)
    """
    try:
        # dataclass
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
    except Exception:
        pass
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    if hasattr(obj, '__dict__'):
        try:
            d = {}
            for k, v in obj.__dict__.items():
                if callable(v):
                    continue
                d[k] = _safe_serialize(v)
            return d
        except Exception:
            pass
    # fallback: primitive or convert to str
    try:
        import json
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def run_light_pipeline(tile_image_bytes: bytes) -> Tuple[Path, Dict[str, Any]]:
    _ensure_models()
    h = _hash_bytes(tile_image_bytes)
    cache_dir = _cache_dir()
    meta_path = cache_dir / f"{h}.json"

    # determine desired output format (obj or glb)
    fmt = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', 'glb')
    out_name = f"{h}_light.{fmt}"
    out_path = settings.glb_dir / out_name

    # if cached meta + output exists, return (unless cached meta records an error)
    if meta_path.exists() and out_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if not meta.get('error'):
            print(f'[PIPELINE] cache hit for {h}, returning {out_path}')
            return out_path, meta
        else:
            print(f'[PIPELINE] cache contains error for {h}, will attempt regeneration')

    try:
        # 1. VLM attr
        print(f'[PIPELINE] extracting VLM attributes for {h}')
        attrs = vlm.extract_attributes(_vlm_model, tile_image_bytes)
        # persist VLM meta for debugging
        try:
            vlm_cache = settings.cache_path / 'vlm_logs'
            vlm_cache.mkdir(parents=True, exist_ok=True)
            vlm_cache_file = vlm_cache / f"{h}_vlm.json"
            # If attrs.details contains a raw text fallback, also store it
            raw_fallback = None
            try:
                if attrs and getattr(attrs, 'details', None):
                    if len(attrs.details) > 0 and isinstance(attrs.details[0], str) and not attrs.details[0].strip().startswith('{'):
                        # treat as raw textual fallback
                        raw_fallback = attrs.details[0]
            except Exception:
                raw_fallback = None
            vlm_cache_file.write_text(json.dumps({'attrs': dataclasses.asdict(attrs), 'prompt': vlm.to_prompt(attrs), 'raw_fallback': raw_fallback}, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

        # If VLM returned a raw textual fallback (details[0]), only use it
        # when it appears substantive and not just noise. Otherwise, use the
        # structured prompt built from reliable fields. This prevents noisy
        # free-text (e.g. 'blue abstract car?') from being sent to SD.
        prompt = None
        try:
            raw_text_candidate = None
            if attrs and getattr(attrs, 'details', None) and len(attrs.details) > 0 and isinstance(attrs.details[0], str):
                raw_text_candidate = attrs.details[0].strip()

            def _looks_substantive_text(s: str) -> bool:
                if not s:
                    return False
                # too short to be useful
                if len(s) < 40:
                    return False
                # reject if it looks like JSON or bracketed data
                if s.startswith('{') and s.endswith('}'):
                    return False
                # common noisy tokens
                low = s.lower()
                for bad in ('abstract', 'unknown', 'maybe', 'not sure', 'idk', 'unsure'):
                    if bad in low:
                        return False
                return True

            if raw_text_candidate and _looks_substantive_text(raw_text_candidate):
                prompt = raw_text_candidate
            else:
                # build prompt from structured attributes, filtering placeholders
                prompt = vlm.to_prompt(attrs)
                # If vlm.to_prompt returned only the minimal fallback, log that
                if prompt.startswith('low-poly'):
                    print(f'[PIPELINE] VLM attributes insufficient; using minimal fallback prompt')
        except Exception:
            prompt = vlm.to_prompt(attrs)

        # 2. Optional: CLIP template search (placeholder)
        # In full impl this would search templates via CLIP; here we log intent
        print(f'[PIPELINE] prompt generated: {prompt[:200]}')

        # 3. SD image generation
        print(f'[PIPELINE] generating SD image for {h}')
        sd_img_bytes = sd.generate_image(_sd_model, prompt)
        # save SD image to cache for inspection
        sd_img_path = cache_dir / f"{h}_sd.png"
        sd_img_path.parent.mkdir(parents=True, exist_ok=True)
        sd_img_path.write_bytes(sd_img_bytes)
        print(f'[PIPELINE] SD image saved to {sd_img_path}')
        # Quick sanity check: ensure SD output is not a single solid color (common fallback)
        try:
            from PIL import Image
            im = Image.open(sd_img_path).convert('RGBA')
            # check if each channel has only one unique value
            pixels = list(im.getdata())
            rs = set(p[0] for p in pixels)
            gs = set(p[1] for p in pixels)
            bs = set(p[2] for p in pixels)
            if len(rs) == 1 and len(gs) == 1 and len(bs) == 1:
                raise RuntimeError(f'SD output appears to be single-color: R={next(iter(rs))},G={next(iter(gs))},B={next(iter(bs))}')
        except Exception as e:
            # Log and raise to make the failure visible to the caller
            print(f'[PIPELINE] SD output sanity check failed: {e}')
            raise

        # 4. 3D generation (TripoSR or fallback)
        print(f'[PIPELINE] invoking 3D generator (TripoSR) for {h} -> {out_path}')
        settings.glb_dir.mkdir(parents=True, exist_ok=True)
        result_path = three_d.generate_glb_from_image(sd_img_bytes, out_path, quality='light')

        # 5. Post-process: if result is obj, also try to save a PNG preview (already have SD PNG)
        out_suffix = result_path.suffix.lower()
        meta = {
            'hash': h,
            'attrs': _safe_serialize(attrs),
            'prompt': prompt,
            'quality': 'light',
            'output': result_path.name,
            'output_type': out_suffix.lstrip('.')
        }
        # write meta
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[PIPELINE] generated output at {result_path} (type={out_suffix})')
        return result_path, meta
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f'[PIPELINE] ERROR during run_light_pipeline: {e}\n{tb}')
        # write an error meta for debugging
        err_meta = {'hash': h, 'error': str(e), 'trace': tb}
        try:
            meta_path.write_text(json.dumps(err_meta, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
        raise


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
