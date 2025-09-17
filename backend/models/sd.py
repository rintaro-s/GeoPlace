"""Stable Diffusion integration using diffusers. Attempts to load a HF pipeline and generate
an image for a given prompt. Falls back to a simple placeholder renderer if diffusers/torch
is not available or GPU device is not present.
"""
from __future__ import annotations
from typing import Optional
from io import BytesIO
from PIL import Image, ImageDraw
import traceback

_PIPELINE = None
_DEVICE = None


def _dummy_generate(prompt: str) -> bytes:
    # Create a diagnostic image (not a single solid color) so failures are easier to spot.
    img = Image.new('RGBA', (512,512))
    d = ImageDraw.Draw(img)
    # background: subtle gradient
    for y in range(512):
        r = int(40 + (y/511.0) * 80)
        g = int(80 + (y/511.0) * 140)
        b = int(60 + (y/511.0) * 50)
        d.line([(0,y),(511,y)], fill=(r,g,b,255))
    # overlay prompt text at top-left for debugging
    try:
        d.text((8,8), prompt[:200], fill=(255,255,255,255))
    except Exception:
        # drawing may fail on some headless PIL builds; ignore
        pass
    bio = BytesIO()
    img.save(bio, format='PNG')
    return bio.getvalue()


def load_sd_model(model_id: Optional[str] = None):
    """Load a Stable Diffusion pipeline if diffusers is available; otherwise return None."""
    global _PIPELINE, _DEVICE
    if _PIPELINE is not None:
        return _PIPELINE
    try:
        import torch
        from diffusers import StableDiffusionPipeline
        model_id = model_id or 'runwayml/stable-diffusion-v1-5'
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16 if device=='cuda' else None)
        # enable optimizations
        try:
            pipe.enable_attention_slicing()
        except Exception:
            pass
        if device == 'cuda':
            pipe = pipe.to('cuda')
        _DEVICE = device
        _PIPELINE = pipe
        return _PIPELINE
    except Exception:
        # fallback
        _PIPELINE = None
        _DEVICE = 'cpu'
        return None


def generate_image(model, prompt: str, seed: Optional[int]=None) -> bytes:
    """Generate PNG bytes for the prompt. If model is None, use dummy generator."""
    try:
        if model is None:
            return _dummy_generate(prompt)
        # model is a diffusers pipeline
        import torch
        generator = None
        if seed is not None:
            generator = torch.Generator('cuda' if torch.cuda.is_available() else 'cpu').manual_seed(seed)
        out = model(prompt, num_inference_steps=20, guidance_scale=7.5, generator=generator, height=512, width=512)
        image = out.images[0]
        bio = BytesIO()
        image.save(bio, format='PNG')
        return bio.getvalue()
    except Exception:
        # on any error, return dummy image
        traceback.print_exc()
        return _dummy_generate(prompt)
