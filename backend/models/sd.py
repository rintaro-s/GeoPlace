"""Stable Diffusion integration using diffusers. Attempts to load a HF pipeline and generate
an image for a given prompt. Falls back to a simple placeholder renderer if diffusers/torch
is not available or GPU device is not present.
"""
from __future__ import annotations
from typing import Optional
from io import BytesIO
from PIL import Image, ImageDraw
import traceback
import subprocess
import json
from pathlib import Path
from datetime import datetime

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
    # If an external SD venv is configured, prefer subprocess-based generation
    try:
        from ..config import settings as _settings
        sd_python = getattr(_settings, 'SD_VENV_PYTHON', None)
    except Exception:
        sd_python = None

    if sd_python:
        # Skip in-process load to avoid importing diffusers/accelerate/huggingface_hub
        # into the main venv. Subprocess worker will be used instead.
        _PIPELINE = None
        _DEVICE = 'cpu'
        print('[SD] SD_VENV_PYTHON configured; skipping in-process SD model load')
        return None

    try:
        import torch
        from diffusers import StableDiffusionPipeline
        model_id = model_id or 'runwayml/stable-diffusion-v1-5'
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        # Use CPU-friendly defaults when CUDA is not available
        torch_dtype = torch.float16 if device == 'cuda' else None
        # low_cpu_mem_usage can help on constrained systems
        try:
            pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=(device!='cuda'))
        except TypeError:
            # older diffusers may not support low_cpu_mem_usage
            pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch_dtype)
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
        # fallback: print traceback to help debugging and return None
        import traceback
        tb = traceback.format_exc()
        print('[SD] failed to load Stable Diffusion pipeline:', tb)
        _PIPELINE = None
        _DEVICE = 'cpu'
        return None


def generate_image(model, prompt: str, seed: Optional[int]=None) -> bytes:
    """Generate PNG bytes for the prompt. If model is None, use dummy generator."""
    try:
        # If no in-process model is loaded, but an external SD venv is configured,
        # prefer calling the sd_worker subprocess so real SD images can be produced
        # without importing heavy ML packages into the main venv.
        if model is None:
            try:
                from ..config import settings as _settings
                sd_python = getattr(_settings, 'SD_VENV_PYTHON', None)
            except Exception:
                sd_python = None
            if sd_python:
                # call the sd_worker.py in the provided python venv with retries
                worker = Path(__file__).resolve().parent.parent.parent / 'scripts' / 'sd_worker.py'
                out_dir = worker.parent
                out_path = out_dir / 'tmp_sd_out.png'
                log_dir = Path(__file__).resolve().parent.parent.parent / 'backend' / 'cache' / 'sd_logs'
                log_dir.mkdir(parents=True, exist_ok=True)
                max_attempts = 3
                base_prompt = prompt
                for attempt in range(1, max_attempts + 1):
                    # vary seed and slightly vary prompt on retries
                    seed_arg = str( (attempt * 1009) % 2**31 )
                    prompt_variant = base_prompt if attempt == 1 else (base_prompt + f' , detailed, vivid, pass {attempt}')
                    cmd = [sd_python, str(worker), '--prompt', prompt_variant, '--out', str(out_path), '--steps', '20']
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
                    except Exception as e:
                        proc = None
                        proc_stdout = f'Exception when running subprocess: {e}'
                    else:
                        proc_stdout = proc.stdout or ''
                        proc_stderr = proc.stderr or ''

                    # write logs per attempt
                    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
                    logpath = log_dir / f'sd_worker_{ts}_attempt{attempt}.log'
                    try:
                        with open(logpath, 'w', encoding='utf-8') as lf:
                            lf.write('CMD: ' + ' '.join(cmd) + '\n\n')
                            if proc is not None:
                                lf.write('STDOUT:\n' + (proc_stdout or '') + '\n')
                                lf.write('STDERR:\n' + (proc_stderr or '') + '\n')
                            else:
                                lf.write(proc_stdout)
                    except Exception:
                        pass

                    # check output
                    if out_path.exists():
                        try:
                            data = out_path.read_bytes()
                            # sanity check: ensure not single-color
                            try:
                                img = Image.open(out_path).convert('RGBA')
                                px = list(img.getdata())
                                cols = set(px)
                                if len(cols) <= 2:
                                    # too few colors -> likely single-color, retry
                                    if attempt < max_attempts:
                                        continue
                                    else:
                                        return data
                                else:
                                    return data
                            except Exception:
                                return data
                        finally:
                            try:
                                out_path.unlink()
                            except Exception:
                                pass
                    # if not produced, loop to retry
                # All attempts failed -> fall back to dummy
            # No external venv or subprocess failure: return diagnostic image
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
        # Attempt subprocess fallback: if environment variable or settings provide
        try:
            # prefer environment variable `SD_VENV_PYTHON` or settings
            sd_python = None
            try:
                # lazy import settings to avoid circular imports at module load
                from ..config import settings as _settings
                sd_python = getattr(_settings, 'SD_VENV_PYTHON', None)
            except Exception:
                sd_python = None
            if sd_python:
                # call the sd_worker.py in the provided python venv
                worker = Path(__file__).resolve().parent.parent.parent / 'scripts' / 'sd_worker.py'
                cmd = [sd_python, str(worker), '--prompt', prompt, '--out', str(worker.parent / 'tmp_sd_out.png')]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                except Exception as e:
                    print('[SD] subprocess call failed:', e)
                    proc = None
                if proc and proc.stdout:
                    try:
                        outj = json.loads(proc.stdout)
                        if outj.get('status') == 'ok':
                            data = Path(outj['out']).read_bytes()
                            return data
                    except Exception:
                        pass
        except Exception:
            pass
        return _dummy_generate(prompt)
